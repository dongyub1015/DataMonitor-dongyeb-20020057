from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from datamonitor.config import SourceConfig, WatchTarget
from datamonitor.sources.base import SourceStatus
from datamonitor.sources.sqlite import SQLiteSource


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount REAL, status TEXT)")
    conn.execute("CREATE TABLE users  (id INTEGER PRIMARY KEY, email TEXT)")
    for i in range(10):
        conn.execute("INSERT INTO orders VALUES (?, ?, ?)", (i, i * 100.0, "active"))
        conn.execute("INSERT INTO users  VALUES (?, ?)", (i, f"user{i}@example.com"))
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def source_config(sqlite_db: Path) -> SourceConfig:
    return SourceConfig(
        name="TestSQLite",
        type="sqlite",
        path=str(sqlite_db),
        watch=[
            WatchTarget(table="orders", metrics=["row_count", "size_mb"]),
            WatchTarget(table="users", metrics=["row_count"]),
        ],
    )


# ── 연결 ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_success(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()  # 예외 없이 성공
    await src.disconnect()


@pytest.mark.asyncio
async def test_connect_missing_file_raises() -> None:
    cfg = SourceConfig(
        name="Bad",
        type="sqlite",
        path="/nonexistent/__datamonitor_test__.db",
        watch=[],
    )
    src = SQLiteSource(cfg)
    with pytest.raises(ConnectionError):
        await src.connect()


# ── 메트릭 조회 ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_metrics_returns_all_watches(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()
    snaps = await src.fetch_metrics()
    await src.disconnect()

    assert len(snaps) == 2
    targets = {s.target for s in snaps}
    assert "orders" in targets
    assert "users" in targets


@pytest.mark.asyncio
async def test_row_count_correct(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()
    snaps = await src.fetch_metrics()
    await src.disconnect()

    orders_snap = next(s for s in snaps if s.target == "orders")
    assert orders_snap.status == SourceStatus.OK
    assert orders_snap.row_count == 10


@pytest.mark.asyncio
async def test_size_mb_non_negative(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()
    snaps = await src.fetch_metrics()
    await src.disconnect()

    for snap in snaps:
        assert snap.size_mb is not None
        assert snap.size_mb >= 0


@pytest.mark.asyncio
async def test_invalid_table_returns_error_snapshot(source_config: SourceConfig) -> None:
    bad_cfg = SourceConfig(
        name="TestSQLite",
        type="sqlite",
        path=source_config.path,
        watch=[WatchTarget(table="nonexistent_table")],
    )
    src = SQLiteSource(bad_cfg)
    await src.connect()
    snaps = await src.fetch_metrics()
    await src.disconnect()

    assert len(snaps) == 1
    assert snaps[0].status == SourceStatus.ERROR
    assert snaps[0].error_msg is not None


# ── Row 미리보기 ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_rows_returns_columns(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()
    preview = await src.fetch_rows("orders", limit=5, offset=0)
    await src.disconnect()

    assert "id" in preview.columns
    assert "amount" in preview.columns
    assert "status" in preview.columns


@pytest.mark.asyncio
async def test_fetch_rows_limit_respected(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()
    preview = await src.fetch_rows("orders", limit=3, offset=0)
    await src.disconnect()

    assert len(preview.rows) == 3


@pytest.mark.asyncio
async def test_fetch_rows_offset_pagination(source_config: SourceConfig) -> None:
    src = SQLiteSource(source_config)
    await src.connect()
    first_page = await src.fetch_rows("orders", limit=5, offset=0)
    second_page = await src.fetch_rows("orders", limit=5, offset=5)
    await src.disconnect()

    first_ids = {r[0] for r in first_page.rows}
    second_ids = {r[0] for r in second_page.rows}
    assert first_ids.isdisjoint(second_ids), "페이지 간 행이 중복되면 안 됩니다"


# ── 컨텍스트 매니저 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_manager(source_config: SourceConfig) -> None:
    async with SQLiteSource(source_config) as src:
        snaps = await src.fetch_metrics()
    assert len(snaps) == 2
