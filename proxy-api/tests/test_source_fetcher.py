import pytest
from aioresponses import aioresponses

from proxy_api.source_fetcher import SOURCES, Proxy, fetch_all_sources


@pytest.mark.unit
def test_sources_dict_has_expected_entries():
    assert len(SOURCES) == 12
    assert "proxyscrape_http" in SOURCES
    assert "proxifly_socks5" in SOURCES


@pytest.mark.integration
async def test_fetch_all_sources_parses_lines():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], body="1.2.3.4:8080\n5.6.7.8:3128\n")
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="")

        proxies = await fetch_all_sources()

    assert len(proxies) == 2
    assert proxies[0] == Proxy(addr="1.2.3.4:8080", source="proxyscrape_http", protocol="http")
    assert proxies[1] == Proxy(addr="5.6.7.8:3128", source="proxyscrape_http", protocol="http")


@pytest.mark.integration
async def test_fetch_deduplicates_by_addr_protocol():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], body="1.2.3.4:8080\n")
        m.get(SOURCES["thespeedx_http"], body="1.2.3.4:8080\n")
        m.get(SOURCES["proxyscrape_socks5"], body="1.2.3.4:8080\n")
        for name, url in SOURCES.items():
            if name not in ("proxyscrape_http", "thespeedx_http", "proxyscrape_socks5"):
                m.get(url, body="")

        proxies = await fetch_all_sources()

    assert len(proxies) == 2
    protocols = {p.protocol for p in proxies}
    assert protocols == {"http", "socks5"}


@pytest.mark.integration
async def test_fetch_skips_failed_source():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], exception=TimeoutError("test"))
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="9.9.9.9:1080\n" if "socks5" in name else "")

        proxies = await fetch_all_sources()

    assert len(proxies) > 0


@pytest.mark.integration
async def test_fetch_strips_whitespace_and_skips_empty():
    with aioresponses() as m:
        m.get(SOURCES["proxyscrape_http"], body="  1.2.3.4:8080  \n\n\n5.6.7.8:3128\n")
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="")

        proxies = await fetch_all_sources()

    assert len(proxies) == 2
    assert proxies[0].addr == "1.2.3.4:8080"
