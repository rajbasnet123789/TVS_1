"""
xmeye_scan.py — async wrapper for XMEye UDP LAN discovery.

This module runs inside cv-engine which uses network_mode:host, giving it
direct access to the host's network interfaces. This is required because:
  - UDP broadcast (255.255.255.255:34568) does not cross Docker bridge NAT.
  - The backend (Docker bridge) cannot reach the physical LAN via broadcast.
  - cv-engine (host network) sends the broadcast on the actual NIC.

Called by cv_engine.server:POST /xmeye-scan, which the backend proxies.
"""
import asyncio
import json
import logging
import socket
import struct
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# XMEye DVRIP discovery port
_DISCOVERY_PORT = 34568
_BROADCAST_ADDR = "255.255.255.255"
_TIMEOUT = 5.0

# DVRIP 20-byte discovery packet (little-endian, cmd=0x1500 = "search")
# Matches the format in backend/app/xmeye/discovery.py
_SEARCH_CMD = 0x1500
_SEARCH_PACKET = (
    struct.pack("<BB", 0xFF, 0x00)   # start + version
    + b"\x00\x00"                   # reserved
    + struct.pack("<II", 0, 0)      # session_id + sequence
    + struct.pack("<BB", 0, 0)      # total_pkts + cur_pkt
    + struct.pack("<H", _SEARCH_CMD)  # command
    + struct.pack("<I", 0)          # payload_length = 0
)

# Compact 4-byte probe some firmware variants respond to
_COMPACT_PACKET = b"\xff\x00\x00\x00"


@dataclass
class DiscoveredXMEyeDevice:
    ip: str
    tcp_port: int = 34567
    http_port: int = 80
    device_name: str = ""
    device_type: str = ""
    serial_no: str = ""
    mac: str = ""
    channel_count: int = 1
    software_version: str = ""
    build_date: str = ""


def _find_json_end(text: str) -> int:
    """Find the closing brace of the first JSON object in text."""
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _parse_response(data: bytes, sender_ip: str) -> DiscoveredXMEyeDevice | None:
    """Parse a raw UDP response from an XMEye device."""
    if not data:
        return None

    # Strip 20-byte DVRIP header if present
    raw = data
    if len(data) > 20 and data[0] == 0xFF:
        try:
            payload_len = struct.unpack_from("<I", data, 16)[0]
            if 20 + payload_len <= len(data):
                raw = data[20: 20 + payload_len]
        except struct.error:
            pass

    # Decode and locate JSON
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        return None

    start = text.find("{")
    if start == -1:
        return None
    text = text[start:]
    end = _find_json_end(text)
    if end == -1:
        return None

    try:
        obj = json.loads(text[:end])
    except json.JSONDecodeError:
        return None

    return DiscoveredXMEyeDevice(
        ip=obj.get("IPv4Address") or obj.get("IP") or sender_ip,
        tcp_port=int(obj.get("TCPPort") or obj.get("Port") or 34567),
        http_port=int(obj.get("HttpPort") or obj.get("WebPort") or 80),
        device_name=obj.get("DeviceName") or obj.get("Name") or "",
        device_type=obj.get("DeviceType") or obj.get("DevType") or "",
        serial_no=obj.get("SerialNo") or obj.get("SN") or "",
        mac=obj.get("MAC") or obj.get("MacAddress") or "",
        channel_count=int(obj.get("ChannelNum") or obj.get("ExtraChannel") or 1),
        software_version=obj.get("SoftWareVersion") or obj.get("Version") or "",
        build_date=obj.get("BuildDate") or obj.get("Date") or "",
    )


async def scan_xmeye_lan(timeout: float = _TIMEOUT) -> list[dict]:
    """
    Broadcast UDP discovery for XMEye/DVRIP devices on all LAN interfaces.
    Returns a list of serialisable dicts (one per unique device IP).
    """
    loop = asyncio.get_event_loop()
    seen: dict[str, DiscoveredXMEyeDevice] = {}

    def _do_scan():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        try:
            sock.bind(("", 0))
            # Send both packet variants for maximum firmware compatibility
            for pkt in (_SEARCH_PACKET, _COMPACT_PACKET):
                try:
                    sock.sendto(pkt, (_BROADCAST_ADDR, _DISCOVERY_PORT))
                except OSError as e:
                    logger.warning("XMEye broadcast send failed: %s", e)

            import time
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    sock.settimeout(max(0.1, deadline - time.monotonic()))
                    data, (sender_ip, _) = sock.recvfrom(4096)
                    if sender_ip not in seen:
                        dev = _parse_response(data, sender_ip)
                        if dev:
                            seen[dev.ip] = dev
                            logger.info("XMEye discovered: %s (%s, %d ch)",
                                        dev.ip, dev.device_name or "unknown", dev.channel_count)
                except socket.timeout:
                    break
                except OSError:
                    break
        finally:
            sock.close()

    await loop.run_in_executor(None, _do_scan)
    devices = [asdict(d) for d in seen.values()]
    logger.info("XMEye LAN scan complete: %d device(s) found", len(devices))
    return devices
