"""
XMEye / DVRIP UDP broadcast discovery.

Sends a 20-byte DVRIP search broadcast to 255.255.255.255:34568 and
collects JSON responses from devices on the local network.

Protocol reference (reverse-engineered):
  - Broadcast port: UDP 34568
  - Discovery command code: 0x1531 (little-endian)
  - Each device replies with a JSON payload describing itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# DVRIP discovery magic — 20-byte header with cmd=0x1531 (search devices)
#
# Byte layout (all little-endian):
#   [0]    = 0xFF  start marker
#   [1]    = 0x00  version
#   [2-3]  = 0x0000
#   [4-7]  = 0x00000000  session id (zero for unauthenticated broadcast)
#   [8-11] = 0x00000000  sequence
#   [12]   = 0x00  total packets
#   [13]   = 0x00  cur packet
#   [14-15]= 0x3115 → 0x1531 LE = 5425 decimal (DeviceSearch command)
#   [16-19]= 0x00000000  payload length (no payload in search request)
_DISCOVERY_PACKET = struct.pack(
    "<BBHHIIBHHI",
    0xFF,       # start marker
    0x00,       # version
    0x0000,     # reserved
    0x0000,     # reserved
    0x00000000, # session_id
    0x00000000, # sequence
    0x00,       # total_pkts
    0x00,       # cur_pkt (as part of 16-bit field)
    0x1531,     # command = DeviceSearch (0x1531)
    0x00000000, # payload_length = 0
)

# Compact 4-byte variant used by some firmware versions
_DISCOVERY_PACKET_SHORT = bytes([0xFF, 0x00, 0x00, 0x00])

DISCOVERY_PORT = 34568
DVRIP_PORT = 34567


@dataclass
class XMEyeDevice:
    ip: str
    tcp_port: int = DVRIP_PORT
    http_port: int = 80
    device_name: str = ""
    device_type: str = ""          # "IPC", "DVR", "NVR"
    serial_no: str = ""
    mac: str = ""
    channel_count: int = 1
    build_date: str = ""
    software_version: str = ""
    raw: dict = field(default_factory=dict, repr=False)


async def discover_xmeye_devices(
    timeout: float = 5.0,
    bind_host: str = "0.0.0.0",
) -> list[XMEyeDevice]:
    """
    Broadcast-discover XMEye/Xiongmai devices on the local LAN.

    Returns a deduplicated list of XMEyeDevice objects.
    """
    loop = asyncio.get_event_loop()

    def _run_discovery() -> dict[str, XMEyeDevice]:
        devices: dict[str, XMEyeDevice] = {}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(timeout)
            sock.bind((bind_host, DISCOVERY_PORT))

            # Send both packet variants — different firmware versions respond to different ones
            sock.sendto(_DISCOVERY_PACKET, ("<broadcast>", DISCOVERY_PORT))
            sock.sendto(_DISCOVERY_PACKET_SHORT, ("<broadcast>", DISCOVERY_PORT))

            import time
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(4096)
                    ip = addr[0]
                    if ip in devices:
                        continue
                    dev = _parse_discovery_response(data, ip)
                    if dev:
                        devices[ip] = dev
                        logger.info("XMEye discovered: %s (%s) at %s", dev.device_name, dev.device_type, ip)
                except TimeoutError:
                    break
                except Exception as exc:
                    logger.debug("XMEye discovery recv error: %s", exc)
        except Exception as exc:
            logger.error("XMEye discovery socket error: %s", exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass
        return devices

    devices = await loop.run_in_executor(None, _run_discovery)
    return list(devices.values())


def _parse_discovery_response(data: bytes, src_ip: str) -> XMEyeDevice | None:
    """
    Parse a UDP discovery response from an XMEye device.

    Responses can be:
      a) Raw JSON (some firmware versions respond with bare JSON after a 20-byte header)
      b) 20-byte DVRIP header + JSON payload
      c) Bare JSON with no header
    """
    payload = data

    # Try to strip 20-byte DVRIP header if present
    if len(data) > 20 and data[0] == 0xFF:
        try:
            payload_len = struct.unpack_from("<I", data, 16)[0]
            if payload_len > 0 and len(data) >= 20 + payload_len:
                payload = data[20:20 + payload_len]
        except Exception:
            pass

    # Strip null terminators and whitespace
    payload = payload.rstrip(b"\x00").strip()

    if not payload:
        return None

    # Some devices send multiple JSON objects — try the first
    try:
        text = payload.decode("utf-8", errors="replace")
        # Handle cases where payload starts with a number or has prefix garbage
        start = text.find("{")
        if start == -1:
            return None
        text = text[start:]
        # Some responses have multiple objects — take the first complete one
        end = _find_json_end(text)
        obj = json.loads(text[:end] if end else text)
    except Exception as exc:
        logger.debug("XMEye: failed to parse response from %s: %s | raw=%r", src_ip, exc, data[:64])
        return None

    if not isinstance(obj, dict):
        return None

    ip = obj.get("IPv4Address") or src_ip
    tcp_port = obj.get("TCPPort") or obj.get("TcpPort") or DVRIP_PORT
    http_port = obj.get("HttpPort") or obj.get("WebPort") or 80

    # Channel count — NVRs report ChannelNum; standalone IPCs default to 1
    channel_count = (
        obj.get("ChannelNum")
        or obj.get("VideoInNum")
        or obj.get("DigChannel")
        or 1
    )

    return XMEyeDevice(
        ip=ip,
        tcp_port=int(tcp_port),
        http_port=int(http_port),
        device_name=obj.get("DeviceName") or obj.get("NickName") or "",
        device_type=obj.get("DeviceType") or obj.get("CatalogType") or "Unknown",
        serial_no=obj.get("SerialNo") or obj.get("SN") or "",
        mac=obj.get("MAC") or obj.get("MACAddress") or "",
        channel_count=int(channel_count),
        build_date=obj.get("BuildDate") or obj.get("BuildTime") or "",
        software_version=obj.get("SoftWareVersion") or obj.get("Version") or "",
        raw=obj,
    )


def _find_json_end(text: str, start: int = 0) -> int | None:
    """Find the closing brace index of the first complete JSON object."""
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None
