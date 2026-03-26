"""Cycle statistics logging — JSON lines to file + Docker stdout."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class CycleStats:
    cycle_seconds: int
    scraped: int
    retained: int
    alive_anon: int
    transparent_rejected: int
    youtube_ok: int
    pool_size: int
    sources: dict[str, int] = field(default_factory=dict)
    fast_count: int = 0
    slow_count: int = 0


def format_stats_line(stats: CycleStats) -> str:
    """Format cycle stats as a single JSON line (no trailing newline)."""
    return json.dumps(
        {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cycle_s": stats.cycle_seconds,
            "scraped": stats.scraped,
            "retained": stats.retained,
            "alive_anon": stats.alive_anon,
            "transparent_rejected": stats.transparent_rejected,
            "youtube_ok": stats.youtube_ok,
            "pool_size": stats.pool_size,
            "fast": stats.fast_count,
            "slow": stats.slow_count,
            "sources": stats.sources,
        }
    )


def append_stats(path: Path, stats: CycleStats) -> None:
    """Append a stats line to the file. Creates file if needed."""
    line = format_stats_line(stats)
    with path.open("a") as f:
        f.write(line + "\n")
