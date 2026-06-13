import asyncio
import base64
import ipaddress
import logging
import re
import socket
import struct
from xml.etree import ElementTree

import httpx

from app.cameras.schemas import ONVIFChannel, ONVIFDevice
from app.config import settings

logger = logging.getLogger(__name__)

SOAP_NS = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wsd": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "dn": "http://www.onvif.org/ver10/network/wsdl",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tev": "http://www.onvif.org/ver10/events/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
    "wsa": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
}

KNOWN_BRANDS: list[tuple[re.Pattern, str, list[str]]] = [
    (re.compile(r"hikvision|hik", re.I), "hikvision", [
        "rtsp://{user}@{ip}:554/Streaming/Channels/{channel:03d}",
        "rtsp://{ip}:554/Streaming/Channels/{channel:03d}",
    ]),
    (re.compile(r"dahua|dalhua|imou", re.I), "dahua", [
        "rtsp://{user}@{ip}:554/cam/realmonitor?channel={channel}&subtype=0",
        "rtsp://{ip}:554/cam/realmonitor?channel={channel}&subtype=0",
    ]),
    (re.compile(r"uniview|unv", re.I), "uniview", [
        "rtsp://{user}@{ip}:554/av0_{channel_idx}",
        "rtsp://{ip}:554/av0_{channel_idx}",
    ]),
    (re.compile(r"tiandy|tandy", re.I), "tiandy", [
        "rtsp://{user}@{ip}:554/stream{channel}",
        "rtsp://{ip}:554/stream{channel}",
    ]),
    (re.compile(r"axis|axc", re.I), "axis", [
        "rtsp://{user}@{ip}:554/axis-media/media.amp?videocodec=h264&resolution=1920x1080",
        "rtsp://{ip}:554/axis-media/media.amp?videocodec=h264&resolution=1920x1080",
    ]),
    (re.compile(r"bosch|bosh", re.I), "bosch", [
        "rtsp://{user}@{ip}:554/rtsp_tunnel?h26x=1",
        "rtsp://{ip}:554/rtsp_tunnel?h26x=1",
    ]),
]

FALLBACK_PATTERNS: list[str] = [
    "rtsp://{user}@{ip}:554/stream1",
    "rtsp://{ip}:554/stream1",
    "rtsp://{user}@{ip}:554/onvif1",
    "rtsp://{ip}:554/onvif1",
    "rtsp://{user}@{ip}:554/h264",
    "rtsp://{ip}:554/h264",
    "rtsp://{user}@{ip}:554/0",
    "rtsp://{ip}:554/0",
]


def _build_auth_header(username: str | None, password: str | None) -> str | None:
    if username and password:
        raw = f"{username}:{password}"
        return f"Basic {base64.b64encode(raw.encode()).decode()}"
    return None


def _onvif_url(ip: str, path: str = "/onvif/device_service") -> str:
    return f"http://{ip}{path}"


async def _soap_post(
    url: str, action: str, body_xml: str, auth_header: str | None = None, timeout: float = 5.0
) -> ElementTree.Element | None:
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema">
  <soap:Header>
    <wsa:Action>{action}</wsa:Action>
  </soap:Header>
  <soap:Body>
    {body_xml}
  </soap:Body>
</soap:Envelope>"""
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    if auth_header:
        headers["Authorization"] = auth_header
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, content=envelope.encode(), headers=headers)
            if resp.status_code >= 300:
                logger.debug(f"SOAP {action} -> {resp.status_code} from {url}")
                return None
            return ElementTree.fromstring(resp.content)
    except Exception as e:
        logger.debug(f"SOAP {action} failed for {url}: {e}")
        return None


async def _get_device_info(ip: str, auth: str | None = None) -> dict:
    url = _onvif_url(ip)
    root = await _soap_post(url, "http://www.onvif.org/ver10/device/wsdl/GetDeviceInformation", """
    <tds:GetDeviceInformation/>
""", auth)
    if root is None:
        return {}
    ns = {"tds": "http://www.onvif.org/ver10/device/wsdl"}
    info = root.find(".//tds:GetDeviceInformationResponse", ns)
    if info is None:
        return {}
    return {
        "manufacturer": _find_text(info, "tds:Manufacturer", ns),
        "model": _find_text(info, "tds:Model", ns),
        "firmware": _find_text(info, "tds:FirmwareVersion", ns),
        "serial": _find_text(info, "tds:SerialNumber", ns),
    }


async def _get_capabilities(ip: str, auth: str | None = None) -> dict:
    url = _onvif_url(ip)
    root = await _soap_post(url, "http://www.onvif.org/ver10/device/wsdl/GetCapabilities", """
    <tds:GetCapabilities>
      <tds:Category>All</tds:Category>
    </tds:GetCapabilities>
""", auth)
    if root is None:
        return {}
    ns = {"tt": "http://www.onvif.org/ver10/schema", "tds": "http://www.onvif.org/ver10/device/wsdl"}
    caps = root.find(".//tds:GetCapabilitiesResponse", ns)
    if caps is None:
        return {}
    result: dict[str, str | None] = {}
    for key, path in [("media", ".//tt:Media/tt:XAddr"), ("events", ".//tt:Events/tt:XAddr"),
                       ("ptz", ".//tt:PTZ/tt:XAddr"), ("imaging", ".//tt:Imaging/tt:XAddr"),
                       ("device", ".//tt:Device/tt:XAddr")]:
        el = caps.find(path, ns)
        result[key] = el.text if el is not None else None
    return result


async def _get_profiles(media_url: str, auth: str | None = None) -> list[dict]:
    root = await _soap_post(media_url, "http://www.onvif.org/ver10/media/wsdl/GetProfiles", """
    <trt:GetProfiles/>
""", auth)
    if root is None:
        return []
    ns = {"trt": "http://www.onvif.org/ver10/media/wsdl", "tt": "http://www.onvif.org/ver10/schema"}
    profiles: list[dict] = []
    for profile in root.findall(".//trt:Profiles", ns):
        token = profile.get("token", "")
        name = profile.find("tt:Name", ns)
        enc = profile.find(".//tt:VideoEncoderConfiguration/tt:Encoding", ns)
        res_w = profile.find(".//tt:VideoEncoderConfiguration/tt:Resolution/tt:Width", ns)
        res_h = profile.find(".//tt:VideoEncoderConfiguration/tt:Resolution/tt:Height", ns)
        profiles.append({
            "token": token,
            "name": name.text if name is not None else None,
            "encoding": enc.text if enc is not None else None,
            "width": int(res_w.text) if res_w is not None else None,
            "height": int(res_h.text) if res_h is not None else None,
        })
    return profiles


async def _get_stream_uri(media_url: str, profile_token: str, auth: str | None = None) -> str | None:
    body = f"""
    <trt:GetStreamUri>
      <trt:StreamSetup>
        <tt:Stream>RTP-Unicast</tt:Stream>
        <tt:Transport>
          <tt:Protocol>RTSP</tt:Protocol>
        </tt:Transport>
      </trt:StreamSetup>
      <trt:ProfileToken>{profile_token}</trt:ProfileToken>
    </trt:GetStreamUri>
"""
    root = await _soap_post(media_url, "http://www.onvif.org/ver10/media/wsdl/GetStreamUri", body, auth)
    if root is None:
        return None
    ns = {"trt": "http://www.onvif.org/ver10/media/wsdl", "tt": "http://www.onvif.org/ver10/schema"}
    uri = root.find(".//trt:GetStreamUriResponse/tt:MediaUri/tt:Uri", ns)
    if uri is not None and uri.text:
        raw = uri.text.strip()
        if raw.startswith("rtsp://"):
            return raw
    return None


def _find_text(parent: ElementTree.Element, path: str, ns: dict) -> str | None:
    el = parent.find(path, ns)
    return el.text if el is not None else None


def _detect_brand(manufacturer: str | None, model: str | None) -> str | None:
    text = f"{manufacturer or ''} {model or ''}"
    for pattern, brand, _ in KNOWN_BRANDS:
        if pattern.search(text):
            return brand
    return None


def _build_fallback_rtsp_urls(ip: str, channel: int, brand: str | None = None) -> list[str]:
    urls: list[str] = []
    if brand:
        for _, b, patterns in KNOWN_BRANDS:
            if b == brand:
                for tmpl in patterns:
                    user_placeholder = "admin:admin"
                    urls.append(tmpl.format(ip=ip, channel=channel, channel_idx=channel - 1, user=user_placeholder))
                    urls.append(tmpl.format(ip=ip, channel=channel, channel_idx=channel - 1, user=""))
                break
    for tmpl in FALLBACK_PATTERNS:
        urls.append(tmpl.format(ip=ip, channel=channel, user="admin:admin"))
        urls.append(tmpl.format(ip=ip, channel=channel, user=""))
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


async def _probe_device_onvif(ip: str, username: str | None = None, password: str | None = None) -> ONVIFDevice | None:
    auth = _build_auth_header(username, password)
    info = await _get_device_info(ip, auth)
    if not info:
        info = await _get_device_info(ip, None)
    if not info.get("manufacturer") and not info.get("model"):
        return None

    manufacturer = info.get("manufacturer") or "Unknown"
    model = info.get("model") or "Unknown"
    brand = _detect_brand(manufacturer, model)
    device_url = _onvif_url(ip)

    caps = await _get_capabilities(ip, auth)
    media_url = caps.get("media") or _onvif_url(ip, "/onvif/media_service")

    profiles = await _get_profiles(str(media_url), auth)
    channels: list[ONVIFChannel] = []
    first_rtsp: str | None = None

    for i, prof in enumerate(profiles):
        token = prof["token"]
        stream_url = await _get_stream_uri(str(media_url), token, auth)
        channel = ONVIFChannel(
            channel=i + 1,
            profile_token=token,
            rtsp_url=stream_url,
            name=prof.get("name"),
            encoding=prof.get("encoding"),
            resolution_width=prof.get("width"),
            resolution_height=prof.get("height"),
        )
        channels.append(channel)
        if stream_url and not first_rtsp:
            first_rtsp = stream_url

    if not channels:
        fallback_urls = _build_fallback_rtsp_urls(ip, 1, brand)
        channels.append(ONVIFChannel(channel=1, profile_token="", rtsp_url=fallback_urls[0] if fallback_urls else None))
        if fallback_urls:
            first_rtsp = fallback_urls[0]

    return ONVIFDevice(
        ip=ip,
        manufacturer=manufacturer,
        model=model,
        brand=brand,
        rtsp_url=first_rtsp,
        onvif_address=f"http://{ip}:80/onvif/device_service",
        device_service_url=device_url,
        channels=channels,
    )


async def _probe_ip(ip: str, username: str | None = None, password: str | None = None) -> ONVIFDevice | None:
    try:
        device = await _probe_device_onvif(ip, username, password)
        if device:
            return device
    except Exception as e:
        logger.debug(f"ONVIF probe failed for {ip}: {e}")
    return None


def _resolve_subnet(subnet: str) -> list[str]:
    try:
        net = ipaddress.ip_network(subnet, strict=False)
        return [str(ip) for ip in net.hosts()]
    except ValueError:
        logger.warning(f"Invalid subnet: {subnet}")
        return []


class ONVIFScanner:
    def __init__(self):
        self.MULTICAST_ADDR = "239.255.255.250"
        self.MULTICAST_PORT = 3702
        self._scanning = False
        self._found_devices: list[ONVIFDevice] = []

    async def scan(self, subnet: str | None = None, ip: str | None = None,
                   username: str | None = None, password: str | None = None,
                   timeout: int = 15):
        self._scanning = True
        self._found_devices = []
        subnet = subnet or settings.onvif_scan_subnet

        logger.info(f"Starting ONVIF scan (subnet={subnet}, ip={ip})...")

        if ip:
            logger.info(f"Probing specific IP: {ip}")
            device = await _probe_ip(ip, username, password)
            if device:
                self._found_devices.append(device)
                logger.info(f"Found device at {ip}: {device.manufacturer} {device.model}")
        else:
            await self._discover_multicast(subnet, timeout)
            discovered_ips = {d.ip for d in self._found_devices}
            target_ips = _resolve_subnet(subnet)
            probe_ips = [ip for ip in target_ips if ip not in discovered_ips]

            if probe_ips:
                logger.info(f"Direct-probing {len(probe_ips)} IPs on {subnet}")
                batch_size = 20
                sem = asyncio.Semaphore(batch_size)

                async def probe(addr: str):
                    async with sem:
                        device = await _probe_ip(addr, username, password)
                        if device:
                            self._found_devices.append(device)

                tasks = [probe(addr) for addr in probe_ips]
                await asyncio.gather(*tasks)

        logger.info(f"ONVIF scan complete: {len(self._found_devices)} device(s) found")
        self._scanning = False
        return self._found_devices

    async def _discover_multicast(self, subnet: str, timeout: int):
        probe_msg = self._build_probe_message()
        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)

        try:
            sock.sendto(probe_msg, (self.MULTICAST_ADDR, self.MULTICAST_PORT))
            logger.debug("WS-Discovery probe sent")

            while True:
                try:
                    data, addr = await loop.run_in_executor(None, sock.recvfrom, 65535)
                    ip = addr[0]
                    device = await self._parse_multicast_response(data, ip)
                    if device and not any(d.ip == device.ip for d in self._found_devices):
                        logger.info(f"Multicast found: {device.ip} - {device.manufacturer} {device.model}")
                        full_device = await _probe_device_onvif(ip)
                        if full_device:
                            self._found_devices.append(full_device)
                        else:
                            self._found_devices.append(device)
                except socket.timeout:
                    break
        except Exception as e:
            logger.error(f"ONVIF multicast error: {e}")
        finally:
            sock.close()

    def _build_probe_message(self):
        return """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>uuid:00000000-0000-0000-0000-000000000001</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </soap:Header>
  <soap:Body>
    <wsd:Probe>
      <wsd:Types>dn:NetworkVideoTransmitter</wsd:Types>
    </wsd:Probe>
  </soap:Body>
</soap:Envelope>""".encode()

    async def _parse_multicast_response(self, data: bytes, ip: str) -> ONVIFDevice | None:
        try:
            root = ElementTree.fromstring(data)
            xaddrs = root.findall(".//wsd:XAddrs", SOAP_NS)
            if xaddrs and xaddrs[0].text:
                rtsp_url = self._guess_rtsp_url(ip)
                return ONVIFDevice(
                    ip=ip,
                    manufacturer="Unknown",
                    model="Unknown",
                    rtsp_url=rtsp_url,
                    onvif_address=f"http://{ip}/onvif/device_service",
                )
        except Exception as e:
            logger.debug(f"Failed to parse multicast response from {ip}: {e}")
        return None

    def _guess_rtsp_url(self, ip: str) -> str:
        return f"rtsp://{ip}:554/stream1"

    @property
    def status(self) -> dict:
        return {
            "scanning": self._scanning,
            "found": len(self._found_devices),
            "devices": [d.model_dump() for d in self._found_devices],
        }


scanner = ONVIFScanner()
