"""Scanner cycle stats reader — reads the last JSON line from the stats log file."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)


def get_last_cycle(stats_path: Path) -> dict | None:
    """Return the last scanner cycle stats from the stats log file.

    Reads the last non-empty line, parses it as JSON, and returns a mapped dict.
    Returns None if the file doesn't exist, is empty, or the last line is malformed.
    """
    if not stats_path.exists():
        return None

    last_line = ""
    try:
        with stats_path.open() as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
    except OSError:
        log.exception("Failed to read stats file %s", stats_path)
        return None

    if not last_line:
        return None

    try:
        data = json.loads(last_line)
    except json.JSONDecodeError:
        log.warning("Malformed JSON in last line of %s", stats_path)
        return None

    return {
        "at": data["ts"],
        "scraped": data["scraped"],
        "alive_anon": data["alive_anon"],
        "youtube_ok": data["youtube_ok"],
        "web_general_ok": data["web_general_ok"],
        "fast": data["fast"],
        "slow": data["slow"],
    }
