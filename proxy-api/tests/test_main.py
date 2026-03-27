"""Tests for the main entry point's scanner_loop function."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from proxy_api.main import STATS_PATH, scanner_loop


@pytest.mark.asyncio
async def test_scanner_loop_calls_run_cycle(redis_client):
    """scanner_loop calls run_cycle with redis client and stats path."""
    mock_run_cycle = AsyncMock()

    with patch("proxy_api.main.run_cycle", mock_run_cycle):
        task = asyncio.create_task(scanner_loop(redis_client))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_run_cycle.assert_called_once_with(redis_client, STATS_PATH)


@pytest.mark.asyncio
async def test_scanner_loop_survives_exception(redis_client):
    """scanner_loop catches exceptions and continues."""
    call_count = 0

    async def failing_then_ok(*args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")

    with (
        patch("proxy_api.main.run_cycle", side_effect=failing_then_ok),
        patch("proxy_api.main.CYCLE_INTERVAL", 0.01),
    ):
        task = asyncio.create_task(scanner_loop(redis_client))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert call_count >= 2, "scanner_loop should have retried after exception"


def test_stats_path_is_data_dir():
    assert Path("/data/scanner-stats.log") == STATS_PATH
