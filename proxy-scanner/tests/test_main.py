import json

import pytest
from aioresponses import aioresponses

from proxy_scanner.main import run_cycle
from proxy_scanner.pool_manager import POOL_KEY
from proxy_scanner.source_fetcher import SOURCES


def _youtube_body() -> str:
    return "<html>" + "x" * 10000 + "ytInitialPlayerResponse" + "videoDetails" + "</html>"


@pytest.mark.integration
async def test_run_cycle_end_to_end(redis_client, tmp_path):
    stats_path = tmp_path / "stats.log"
    with aioresponses() as m:
        # One source returns one proxy
        m.get(SOURCES["proxyscrape_http"], body="1.2.3.4:8080\n")
        for name, url in SOURCES.items():
            if name != "proxyscrape_http":
                m.get(url, body="")

        # Our real IP lookup
        m.get("https://httpbin.org/ip", payload={"origin": "99.99.99.99"})

        # Stage 1: httpbin/anything succeeds — elite proxy
        m.get("https://httpbin.org/anything", payload={"origin": "1.2.3.4", "headers": {"Host": "httpbin.org"}})

        # Stage 2: YouTube succeeds
        m.get("https://www.youtube.com/watch?v=jNQXAC9IVRw", body=_youtube_body())

        stats = await run_cycle(redis_client, stats_path)

    assert stats.youtube_ok == 1
    assert stats.pool_size == 1

    # Check Redis has the proxy
    members = await redis_client.smembers(POOL_KEY)
    assert len(members) == 1
    entry = json.loads(next(iter(members)))
    assert entry["addr"] == "1.2.3.4:8080"

    # Check stats file was written
    assert stats_path.exists()
    line = json.loads(stats_path.read_text().strip())
    assert line["youtube_ok"] == 1
