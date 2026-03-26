import pytest
from aioresponses import aioresponses

from proxy_api.source_fetcher import Proxy
from proxy_api.validators import (
    BANDWIDTH_URL,
    HTTPBIN_URL,
    YOUTUBE_URL,
    check_alive_and_anonymity,
    check_bandwidth,
    check_youtube,
)


@pytest.mark.unit
async def test_alive_proxy_elite():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(HTTPBIN_URL, payload={"origin": "1.2.3.4", "headers": {"Host": "httpbin.org", "Accept": "*/*"}})
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")
    assert result is not None
    assert result.alive is True
    assert result.anonymity == "elite"
    assert result.latency_ms > 0


@pytest.mark.unit
async def test_transparent_proxy_rejected():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(HTTPBIN_URL, payload={"origin": "1.2.3.4", "headers": {"X-Forwarded-For": "99.99.99.99", "Host": "httpbin.org"}})
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")
    assert result is not None
    assert result.anonymity == "transparent"


@pytest.mark.unit
async def test_anonymous_proxy():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(HTTPBIN_URL, payload={"origin": "1.2.3.4", "headers": {"Via": "1.1 proxy.example.com", "Host": "httpbin.org"}})
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")
    assert result is not None
    assert result.anonymity == "anonymous"


@pytest.mark.unit
async def test_dead_proxy_returns_none():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(HTTPBIN_URL, exception=TimeoutError("test"))
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")
    assert result is None


@pytest.mark.unit
async def test_socks5_proxy_path():
    proxy = Proxy(addr="1.2.3.4:1080", source="test", protocol="socks5")
    with aioresponses() as m:
        m.get(HTTPBIN_URL, payload={"origin": "1.2.3.4", "headers": {"Host": "httpbin.org"}})
        result = await check_alive_and_anonymity(proxy, real_ip="99.99.99.99")
    assert result is not None
    assert result.anonymity == "elite"


@pytest.mark.unit
async def test_youtube_ok_with_markers():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    body = "<html>" + "x" * 10000 + "ytInitialPlayerResponse" + "videoDetails" + "</html>"
    with aioresponses() as m:
        m.get(YOUTUBE_URL, body=body)
        result = await check_youtube(proxy)
    assert result is True


@pytest.mark.unit
async def test_youtube_fail_captcha():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    body = "<html>Please verify you are not a robot captcha</html>"
    with aioresponses() as m:
        m.get(YOUTUBE_URL, body=body)
        result = await check_youtube(proxy)
    assert result is False


@pytest.mark.unit
async def test_youtube_fail_short_response():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(YOUTUBE_URL, body="short")
        result = await check_youtube(proxy)
    assert result is False


@pytest.mark.unit
async def test_youtube_fail_timeout():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(YOUTUBE_URL, exception=TimeoutError("test"))
        result = await check_youtube(proxy)
    assert result is False


@pytest.mark.unit
async def test_bandwidth_fast_proxy():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    data = b"x" * 2_000_000
    with aioresponses() as m:
        m.get(BANDWIDTH_URL, body=data)
        speed = await check_bandwidth(proxy)
    assert speed > 0


@pytest.mark.unit
async def test_bandwidth_timeout():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(BANDWIDTH_URL, exception=TimeoutError("test"))
        speed = await check_bandwidth(proxy)
    assert speed == 0


@pytest.mark.unit
async def test_bandwidth_incomplete():
    proxy = Proxy(addr="1.2.3.4:8080", source="test", protocol="http")
    with aioresponses() as m:
        m.get(BANDWIDTH_URL, body=b"x" * 100)  # too small
        speed = await check_bandwidth(proxy)
    assert speed == 0
