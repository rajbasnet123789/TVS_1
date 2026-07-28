"""
XMEye / DVRIP TCP client.

Handles:
  - Sofia password hashing (MD5-based, 8-char base62)
  - DVRIP login (command 1000) to validate credentials
  - RTSP URL construction for all known XMEye firmware formats
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import socket
import struct
from urllib.parse import quote

logger = logging.getLogger(__name__)

DVRIP_PORT = 34567

# ─────────────────────────────────────────────────────────────────────────────
# Sofia/MD5 password hash
# ─────────────────────────────────────────────────────────────────────────────
_SOFIA_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def sofia_hash(password: str) -> str:
    """
    Produce the 8-character 'Sofia hash' used by XMEye DVRIP login.

    Algorithm:
      1. MD5(password) → 16 raw bytes
      2. Process bytes in pairs; for each pair: sum the two bytes mod 62
      3. Map result index into a base-62 alphabet
    """
    md5 = hashlib.md5(password.encode("utf-8")).digest()
    return "".join(
        _SOFIA_CHARS[(md5[i] + md5[i + 1]) % 62]
        for i in range(0, 16, 2)
    )


# ─────────────────────────────────────────────────────────────────────────────
# DVRIP packet builder / parser
#
# DVRIP header is exactly 20 bytes, little-endian, no alignment padding:
#   Offset  Size  Field
#   0       1     start marker (0xFF)
#   1       1     version (0x00)
#   2       2     reserved
#   4       2     reserved
#   6       4     session_id (uint32 LE)
#   10      4     sequence   (uint32 LE)
#   14      1     total_packets
#   15      1     cur_packet
#   16      2     command code (uint16 LE)
#   18      2     (reserved / padding to reach 20 bytes)
#   ... wait — real DVRIP is:                              
#   0       1     0xFF                                     
#   1       1     version                                  
#   2       2     reserved16                               
#   4       4     session_id                               
#   8       4     sequence                                 
#   12      1     total_pkts                               
#   13      1     cur_pkt                                  
#   14      2     command  (uint16 LE)                     
#   16      4     payload_length (uint32 LE)   ← offset 16 
# ─────────────────────────────────────────────────────────────────────────────
_HEADER_FMT = "<BB2sIIBBHI"   # 20 bytes exact, no padding
_HEADER_SIZE = 20


def _build_packet(cmd: int, payload: bytes, session_id: int = 0, seq: int = 0) -> bytes:
    """
    Build a 20-byte DVRIP header + payload.

    Header layout (all little-endian):
      [0]    start  = 0xFF
      [1]    ver    = 0x00
      [2-3]  reserved
      [4-7]  session_id
      [8-11] sequence
      [12]   total_pkts
      [13]   cur_pkt
      [14-15] command
      [16-19] payload_length
    """
    header = (
        struct.pack("<BB", 0xFF, 0x00)          # start + version
        + b"\x00\x00"                           # reserved 2 bytes
        + struct.pack("<II", session_id, seq)   # session_id + sequence
        + struct.pack("<BB", 0x00, 0x00)        # total_pkts + cur_pkt
        + struct.pack("<H", cmd)                # command (uint16 LE)
        + struct.pack("<I", len(payload))       # payload_length at offset 16
    )
    assert len(header) == _HEADER_SIZE, f"Header must be {_HEADER_SIZE} bytes, got {len(header)}"
    return header + payload


def _parse_response(data: bytes) -> tuple[int, dict]:
    """Returns (command_code, parsed_json_dict) from a raw DVRIP response."""
    if len(data) < _HEADER_SIZE:
        raise ValueError(f"Response too short: {len(data)} bytes")

    # Parse fixed-offset fields manually (avoids struct alignment surprises)
    cmd = struct.unpack_from("<H", data, 14)[0]          # command at offset 14
    payload_len = struct.unpack_from("<I", data, 16)[0]  # payload_length at offset 16

    payload_bytes = data[_HEADER_SIZE: _HEADER_SIZE + payload_len]
    text = payload_bytes.rstrip(b"\x00").decode("utf-8", errors="replace")

    try:
        return cmd, json.loads(text)
    except json.JSONDecodeError:
        return cmd, {"_raw": text}


# ─────────────────────────────────────────────────────────────────────────────
# DVRIP login (async, non-blocking via executor)
# ─────────────────────────────────────────────────────────────────────────────

class DVRIPAuthError(Exception):
    """Raised when DVRIP login fails."""
    def __init__(self, ret_code: int, message: str = ""):
        self.ret_code = ret_code
        super().__init__(f"DVRIP login failed (Ret={ret_code}): {message}")


# Map of known DVRIP return codes
_RET_MESSAGES = {
    100: "OK",
    101: "Unknown error",
    102: "Unsupported version",
    103: "Request not permitted",
    104: "User already logged in",
    105: "User is not logged in",
    106: "Username or password incorrect",
    107: "User does not have permission",
    108: "Password incorrect",
    109: "Password is the same",
    110: "Password is too long",
    111: "User already exists",
    112: "User does not exist",
    113: "User group already exists",
    114: "User group does not exist",
    203: "Password is too short",
}


def _dvrip_login_blocking(
    ip: str,
    port: int,
    username: str,
    password: str,
    timeout: float = 5.0,
) -> dict:
    """
    Synchronous DVRIP login — runs in a thread via run_in_executor.

    Returns the full response dict on success.
    Raises DVRIPAuthError on auth failure, OSError on network failure.
    """
    login_payload = json.dumps(
        {
            "EncryptType": "MD5",
            "LoginType": "DVRIP-Web",
            "PassWord": sofia_hash(password) if password else "",
            "UserName": username,
        },
        separators=(",", ":"),
    ).encode("utf-8") + b"\x0a"  # DVRIP JSON payloads are NUL or LF-terminated

    packet = _build_packet(cmd=1000, payload=login_payload)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        sock.sendall(packet)

        # Read response — first 20-byte header, then payload
        header_bytes = _recv_exact(sock, _HEADER_SIZE)
        payload_len = struct.unpack_from("<I", header_bytes, 16)[0]

        payload_bytes = _recv_exact(sock, payload_len) if payload_len else b""
        _, resp = _parse_response(header_bytes + payload_bytes)

        ret = resp.get("Ret", -1)
        if ret != 100:
            msg = _RET_MESSAGES.get(ret, "Unknown error")
            raise DVRIPAuthError(ret, msg)

        return resp
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed before receiving expected bytes")
        buf += chunk
    return buf


async def dvrip_login(
    ip: str,
    port: int = DVRIP_PORT,
    username: str = "admin",
    password: str = "",
    timeout: float = 5.0,
) -> dict:
    """
    Async DVRIP login. Returns response dict containing ChannelNum, SessionID, etc.
    Raises DVRIPAuthError on invalid credentials, OSError on network failure.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _dvrip_login_blocking, ip, port, username, password, timeout
    )


# ─────────────────────────────────────────────────────────────────────────────
# RTSP URL builder
# ─────────────────────────────────────────────────────────────────────────────
# XMEye uses one of two RTSP URL formats depending on firmware version:
#
#   Format A (older / "XMEye" format):
#     rtsp://user:pass@host:554/user=user&password=pass&channel=N&stream=S.sdp
#
#   Format B (newer / "channel path" format):
#     rtsp://user:pass@host:554/chNN/S
#       where NN = zero-padded channel (01, 02, ...), S = 0 (main) or 1 (sub)
#
# We generate both; cv-engine FFmpeg will try Format A first (more compatible).

def build_xmeye_rtsp_url(
    host: str,
    username: str,
    password: str,
    channel: int = 1,
    substream: bool = False,
    rtsp_port: int = 554,
    *,
    format: str = "A",  # "A" = XMEye legacy, "B" = channel path
) -> str:
    """
    Build an XMEye RTSP URL.

    Args:
        host: Camera/NVR IP address
        username: Login username
        password: Login password (plaintext — embedded in URL for RTSP auth)
        channel: 1-based channel number
        substream: False = main stream (HD), True = sub stream (SD)
        rtsp_port: RTSP port (default 554)
        format: "A" for legacy XMEye format, "B" for newer channel path format

    Returns:
        RTSP URL string
    """
    user_enc = quote(username, safe="")
    pass_enc = quote(password, safe="")
    stream = 1 if substream else 0

    if format == "B":
        ch_str = f"ch{channel:02d}"
        path = f"/{ch_str}/{stream}"
    else:
        # Format A: query-string style path
        path = f"/user={username}&password={password}&channel={channel}&stream={stream}.sdp"

    return f"rtsp://{user_enc}:{pass_enc}@{host}:{rtsp_port}{path}"


def build_all_rtsp_urls(
    host: str,
    username: str,
    password: str,
    channel: int = 1,
    rtsp_port: int = 554,
) -> dict[str, str]:
    """
    Return a dict of all RTSP URL variants for a given channel.
    Frontend lets user pick the format that works for their device.
    """
    return {
        "main_stream_format_a": build_xmeye_rtsp_url(host, username, password, channel, False, rtsp_port, format="A"),
        "sub_stream_format_a": build_xmeye_rtsp_url(host, username, password, channel, True, rtsp_port, format="A"),
        "main_stream_format_b": build_xmeye_rtsp_url(host, username, password, channel, False, rtsp_port, format="B"),
        "sub_stream_format_b": build_xmeye_rtsp_url(host, username, password, channel, True, rtsp_port, format="B"),
    }
