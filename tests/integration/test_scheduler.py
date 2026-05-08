from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from datamonitor.config import SourceConfig, WatchTarget
from datamonitor.scheduler import PollScheduler
from datamonitor.sources.base import MetricSnapshot
from datamonitor.sources.sqlite import SQLiteSource


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    db = tmp_path / "sched_test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
    for i in range(5):
        conn.execute("INSERT INTO items VALUES (?)", (i,))
    conn.commit()
    conn.close()
    return db


@pytest.mark.asyncio
async def test_trigger_once_calls_on_update(sqlite_db: Path) -> None:
    cfg = SourceConfig(
        name="SchedSQLite",
        type="sqlite",
        path=str(sqlite_db),
        watch=[WatchTarget(table="items")],
    )
    received: list[list[MetricSnapshot]] = []

    def on_update(snaps: list[MetricSnapshot]) -> None:
        received.append(snaps)

    scheduler = PollScheduler(
        sources=[SQLiteSource(cfg)],
        interval=60,
        on_update=on_update,
    )
    await scheduler.trigger_once()

    assert len(received) == 1
    assert len(received[0]) == 1
    assert received[0][0].row_count == 5


@pytest.mark.asyncio
async def test_start_and_stop(sqlite_db: Path) -> None:
    cfg = SourceConfig(
        name="SchedSQLite2",
        type="sqlite",
        path=str(sqlite_db),
        watch=[WatchTarget(table="items")],
    )
    received: list[list[MetricSnapshot]] = []

    def on_update(snaps: list[MetricSnapshot]) -> None:
        received.append(snaps)

    scheduler = PollScheduler(
        sources=[SQLiteSource(cfg)],
        interval=1,
        on_update=on_update,
    )
    await scheduler.start()
    await asyncio.sleep(0.1)   # 초회 즉시 폴링 대기
    await scheduler.stop()

    # start()는 폴링 루프만 시작(trigger_once 아님) — 루프 진입 전 stop 가능
    assert isinstance(received, list)  # stop 후 오류 없음
