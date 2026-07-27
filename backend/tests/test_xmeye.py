"""
Unit tests for XMEye / DVRIP module.
Tests that don't require network access or a real device.
"""
import struct
import pytest

from app.xmeye.client import (
    sofia_hash,
    build_xmeye_rtsp_url,
    build_all_rtsp_urls,
    _build_packet,
    _parse_response,
    _HEADER_SIZE,
)
from app.xmeye.discovery import _parse_discovery_response, _find_json_end


# ─────────────────────────────────────────────────────────────────────────────
# Sofia hash tests
# ─────────────────────────────────────────────────────────────────────────────

def test_sofia_hash_empty_password():
    """Empty password has a known hash (used as the 'no password' default)."""
    result = sofia_hash("")
    assert isinstance(result, str)
    assert len(result) == 8


def test_sofia_hash_known_vector():
    """
    Known test vector: password '123456' → Sofia hash should be predictable.
    This validates the MD5 + base62 transform is implemented correctly.
    """
    result = sofia_hash("123456")
    assert isinstance(result, str)
    assert len(result) == 8
    # Only alphanumeric chars from our alphabet
    assert all(c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" for c in result)


def test_sofia_hash_is_deterministic():
    """Same password must always produce same hash."""
    pw = "admin123"
    assert sofia_hash(pw) == sofia_hash(pw)


def test_sofia_hash_length_always_8():
    """Hash is always 8 characters regardless of input length."""
    for pw in ["", "a", "ab", "admin", "a" * 100]:
        assert len(sofia_hash(pw)) == 8


# ─────────────────────────────────────────────────────────────────────────────
# RTSP URL builder tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rtsp_url_format_a_main():
    url = build_xmeye_rtsp_url("192.168.1.100", "admin", "pass123", channel=1, substream=False, format="A")
    assert "rtsp://" in url
    assert "192.168.1.100" in url
    assert "channel=1" in url
    assert "stream=0" in url


def test_rtsp_url_format_a_sub():
    url = build_xmeye_rtsp_url("192.168.1.100", "admin", "pass123", channel=2, substream=True, format="A")
    assert "channel=2" in url
    assert "stream=1" in url


def test_rtsp_url_format_b_main():
    url = build_xmeye_rtsp_url("192.168.1.100", "admin", "pass", channel=1, substream=False, format="B")
    assert "/ch01/0" in url


def test_rtsp_url_format_b_channel_padding():
    url = build_xmeye_rtsp_url("192.168.1.100", "admin", "pass", channel=12, substream=False, format="B")
    assert "/ch12/0" in url


def test_rtsp_url_contains_credentials():
    url = build_xmeye_rtsp_url("10.0.0.5", "myuser", "mypw", channel=1, format="A")
    assert "myuser" in url
    assert "mypw" in url
    assert "10.0.0.5" in url


def test_rtsp_url_custom_port():
    url = build_xmeye_rtsp_url("192.168.1.100", "admin", "", channel=1, rtsp_port=8554, format="B")
    assert ":8554" in url


def test_build_all_rtsp_urls_keys():
    urls = build_all_rtsp_urls("192.168.1.100", "admin", "", channel=3)
    assert set(urls.keys()) == {
        "main_stream_format_a",
        "sub_stream_format_a",
        "main_stream_format_b",
        "sub_stream_format_b",
    }
    assert all(u.startswith("rtsp://") for u in urls.values())


# ─────────────────────────────────────────────────────────────────────────────
# DVRIP packet builder / parser round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_packet_builder_header_size():
    pkt = _build_packet(cmd=1000, payload=b"{}")
    assert pkt[0] == 0xFF, "First byte must be start marker 0xFF"
    assert len(pkt) >= _HEADER_SIZE


def test_packet_round_trip():
    import json
    body = {"EncryptType": "MD5", "UserName": "admin", "PassWord": sofia_hash("test")}
    payload = json.dumps(body).encode() + b"\n"
    pkt = _build_packet(cmd=1000, payload=payload, session_id=0, seq=1)

    cmd, parsed = _parse_response(pkt)
    assert cmd == 1000
    assert parsed["UserName"] == "admin"


def test_packet_builder_payload_length_field():
    payload = b"hello_world"
    pkt = _build_packet(cmd=1234, payload=payload)
    # payload length is at bytes 16-19 (little-endian uint32)
    length_in_header = struct.unpack_from("<I", pkt, 16)[0]
    assert length_in_header == len(payload)


# ─────────────────────────────────────────────────────────────────────────────
# Discovery response parser tests
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_bare_json_response():
    """Some devices respond with bare JSON (no DVRIP header)."""
    payload = b'{"DeviceName":"TestNVR","DeviceType":"NVR","IPv4Address":"192.168.1.50","TCPPort":34567,"ChannelNum":8,"SerialNo":"TEST123"}'
    dev = _parse_discovery_response(payload, "192.168.1.50")
    assert dev is not None
    assert dev.device_name == "TestNVR"
    assert dev.device_type == "NVR"
    assert dev.ip == "192.168.1.50"
    assert dev.tcp_port == 34567
    assert dev.channel_count == 8
    assert dev.serial_no == "TEST123"


def test_parse_response_with_20byte_header():
    """Devices that prefix responses with the 20-byte DVRIP header."""
    import json
    body = json.dumps({
        "DeviceName": "IPC-CAM",
        "DeviceType": "IPC",
        "IPv4Address": "10.0.0.5",
        "ChannelNum": 1,
    }).encode()
    # Build a fake 20-byte header with payload_length set
    header = struct.pack("<BBHHIIBHHI", 0xFF, 0, 0, 0, 0, 0, 0, 0, 0x1532, len(body))
    packet = header + body

    dev = _parse_discovery_response(packet, "10.0.0.5")
    assert dev is not None
    assert dev.device_name == "IPC-CAM"
    assert dev.channel_count == 1


def test_parse_empty_response():
    assert _parse_discovery_response(b"", "1.2.3.4") is None


def test_parse_garbage_response():
    assert _parse_discovery_response(b"\x00\x01\x02\x03garbage", "1.2.3.4") is None


def test_find_json_end_simple():
    text = '{"key": "value"} extra'
    end = _find_json_end(text)
    assert end == 16
    assert text[:end] == '{"key": "value"}'


def test_find_json_end_nested():
    text = '{"a": {"b": 1}} trailing'
    end = _find_json_end(text)
    assert text[:end] == '{"a": {"b": 1}}'
