"""Tests for scanner_stats.get_last_cycle."""

from __future__ import annotations

import json
from unittest.mock import patch

from proxy_api.scanner_stats import get_last_cycle

SAMPLE_LINE = {
    "ts": "2026-03-27T08:16:55Z",
    "cycle_s": 986,
    "scraped": 5961,
    "retained": 228,
    "alive_anon": 402,
    "transparent_rejected": 0,
    "youtube_ok": 210,
    "web_general_ok": 161,
    "pool_size": 1086,
    "fast": 9,
    "slow": 109,
    "sources": {},
}

EXPECTED = {
    "at": "2026-03-27T08:16:55Z",
    "scraped": 5961,
    "alive_anon": 402,
    "youtube_ok": 210,
    "web_general_ok": 161,
    "fast": 9,
    "slow": 109,
}


def _write_lines(path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n" if lines else "")


def test_single_valid_line(tmp_path):
    stats_file = tmp_path / "stats.jsonl"
    stats_file.write_text(json.dumps(SAMPLE_LINE) + "\n")

    result = get_last_cycle(stats_file)

    assert result == EXPECTED


def test_multiple_lines_returns_last(tmp_path):
    stats_file = tmp_path / "stats.jsonl"
    first = {**SAMPLE_LINE, "ts": "2026-03-27T07:00:00Z", "scraped": 1000}
    last = {**SAMPLE_LINE, "ts": "2026-03-27T08:16:55Z", "scraped": 5961}
    stats_file.write_text(json.dumps(first) + "\n" + json.dumps(last) + "\n")

    result = get_last_cycle(stats_file)

    assert result == EXPECTED
    assert result["scraped"] == 5961  # ty: ignore[not-subscriptable]


def test_empty_file_returns_none(tmp_path):
    stats_file = tmp_path / "stats.jsonl"
    stats_file.write_text("")

    result = get_last_cycle(stats_file)

    assert result is None


def test_missing_file_returns_none(tmp_path):
    stats_file = tmp_path / "nonexistent.jsonl"

    result = get_last_cycle(stats_file)

    assert result is None


def test_malformed_last_line_returns_none(tmp_path):
    stats_file = tmp_path / "stats.jsonl"
    stats_file.write_text(json.dumps(SAMPLE_LINE) + "\nnot valid json\n")

    result = get_last_cycle(stats_file)

    assert result is None


def test_oserror_reading_file_returns_none(tmp_path):
    stats_file = tmp_path / "stats.jsonl"
    stats_file.write_text(json.dumps(SAMPLE_LINE) + "\n")

    with patch("pathlib.Path.open", side_effect=OSError("disk error")):
        result = get_last_cycle(stats_file)

    assert result is None


def test_file_with_trailing_blank_lines(tmp_path):
    """Trailing blank lines are skipped; last non-empty line is used."""
    stats_file = tmp_path / "stats.jsonl"
    stats_file.write_text(json.dumps(SAMPLE_LINE) + "\n\n\n")

    result = get_last_cycle(stats_file)

    assert result == EXPECTED
