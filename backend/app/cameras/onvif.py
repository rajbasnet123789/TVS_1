import asyncio
import logging
import socket
import struct
import time
import uuid
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 3702
SCAN_TIMEOUT = 5.0

PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
  xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </soap:Header>
  <soap:Body>
    <wsd:Probe>
      <wsd:Types>dn:NetworkVideoTransmitter</wsd:Types>
    </wsd:Probe>
  </soap:Body>
</soap:Envelope>"""


def _build_probe() -> bytes:
    return PROBE_TEMPLATE.format(message_id=str(uuid.uuid4())).encode("utf-8")


def _parse_device(response: bytes) -> dict | None:
    try:
        root = ElementTree.fromstring(response)
        ns = {
            "s": "http://www.w3.org/2003/05/soap-envelope",
            "a": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
            "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
        }
        body = root.find(".//s:Body", ns)
        if body is None:
            return None
        probe_match = body.find(".//d:ProbeMatches/d:ProbeMatch", ns)
        if probe_match is None:
            return None

        xaddr_elem = probe_match.find(".//d:XAddrs", ns)
        types_elem = probe_match.find(".//d:Types", ns)
        scopes_elem = probe_match.find(".//d:Scopes", ns)

        xaddrs = xaddr_elem.text if xaddr_elem is not None else ""
        device_url = xaddrs.split()[0] if xaddrs else ""

        # Extract device name from scopes or URL
        name = "ONVIF Camera"
        scopes_text = scopes_elem.text if scopes_elem is not None else ""
        for scope in scopes_text.split():
            if "name/" in scope.lower():
                name = scope.rsplit("/", 1)[-1].replace("_", " ").replace("%20", " ")
                break

        return {
            "name": name,
            "device_url": device_url,
            "xaddrs": xaddrs,
            "types": types_elem.text if types_elem is not None else "",
            "scopes": scopes_text,
        }
    except Exception as e:
        logger.debug("Failed to parse WS-Discovery response: %s", e)
        return None


async def discover_onvif_devices(timeout: int = SCAN_TIMEOUT) -> list[dict]:
    loop = asyncio.get_event_loop()
    devices: dict[str, dict] = {}

    def _discover():
        nonlocal devices
        # Find all local IPv4 interface addresses
        try:
            _, _, local_ips = socket.gethostbyname_ex(socket.gethostname())
        except Exception as e:
            logger.debug("Failed to get local IPs: %s", e)
            local_ips = []
        
        ips = [ip for ip in local_ips if ":" not in ip]
        if not ips:
            ips = ["0.0.0.0"]

        sockets = []
        probe = _build_probe()

        # Set up a socket on each adapter and send the probe
        for ip in ips:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("b", 4))
                
                # Direct multicast packets to this specific interface
                try:
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
                except Exception as e:
                    logger.debug("Failed to set IP_MULTICAST_IF on %s: %s", ip, e)
                
                sock.settimeout(timeout)
                sock.bind((ip, 0))
                sock.sendto(probe, (MULTICAST_GROUP, MULTICAST_PORT))
                sockets.append(sock)
                logger.debug("Sent ONVIF probe on interface %s (port %s)", ip, sock.getsockname()[1])
            except Exception as e:
                logger.debug("Failed to setup discovery socket on %s: %s", ip, e)
                if 'sock' in locals() and sock:
                    sock.close()

        if not sockets:
            logger.debug("No discovery sockets could be created")
            return

        import select
        start = time.monotonic()
        
        while (time.monotonic() - start) < timeout:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                break
                
            # Wait for any socket to be readable
            readable, _, _ = select.select(sockets, [], [], remaining)
            for sock in readable:
                try:
                    data, addr = sock.recvfrom(65535)
                    device = _parse_device(data)
                    if device and device.get("device_url"):
                        key = device["device_url"]
                        if key not in devices:
                            device["ip"] = addr[0]
                            devices[key] = device
                            logger.info("Discovered ONVIF device %s at %s", device["name"], addr[0])
                except Exception as e:
                    logger.debug("WS-Discovery recv error: %s", e)

        for sock in sockets:
            sock.close()

    await loop.run_in_executor(None, _discover)
    return list(devices.values())
