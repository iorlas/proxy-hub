import json
import tempfile
from pathlib import Path

import pytest

from proxy_api.stats import CycleStats, append_stats, format_stats_line


@pytest.mark.unit
def test_format_stats_line_is_valid_json():
    stats = CycleStats(
        cycle_seconds=152,
        scraped=5009,
        retained=142,
        alive_anon=170,
        transparent_rejected=4,
        youtube_ok=82,
        pool_size=224,
        sources={"proxifly_socks5": 57, "monosans_http": 6},
    )
    line = format_stats_line(stats)
    parsed = json.loads(line)
    assert parsed["cycle_s"] == 152
    assert parsed["scraped"] == 5009
    assert parsed["pool_size"] == 224
    assert "ts" in parsed
    assert parsed["sources"]["proxifly_socks5"] == 57


@pytest.mark.unit
def test_format_stats_line_has_no_newline():
    stats = CycleStats(
        cycle_seconds=10,
        scraped=0,
        retained=0,
        alive_anon=0,
        transparent_rejected=0,
        youtube_ok=0,
        pool_size=0,
        sources={},
    )
    line = format_stats_line(stats)
    assert "\n" not in line


@pytest.mark.unit
def test_append_stats_creates_and_appends():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "stats.log"
        stats = CycleStats(
            cycle_seconds=10,
            scraped=100,
            retained=5,
            alive_anon=10,
            transparent_rejected=0,
            youtube_ok=8,
            pool_size=13,
            sources={},
        )
        append_stats(path, stats)
        append_stats(path, stats)
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        json.loads(lines[0])  # should not raise
