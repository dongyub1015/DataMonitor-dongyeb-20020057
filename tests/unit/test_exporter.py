from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from datamonitor.exporter import Exporter
from datamonitor.sources.base import MetricSnapshot, SourceStatus


def _snap(
    source: str = "MySQL",
    target: str = "orders",
    row_count: int = 1000,
    size_mb: float = 24.5,
    status: SourceStatus = SourceStatus.OK,
    error_msg: str | None = None,
) -> MetricSnapshot:
    return MetricSnapshot(
        source_name=source,
        target=target,
        collected_at=datetime.fromisoformat("2026-05-08T12:00:00"),
        status=status,
        metrics={"row_count": row_count, "size_mb": size_mb},
        error_msg=error_msg,
    )


# ── JSON ─────────────────────────────────────────────────────────────────────

def test_json_contains_required_fields(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([_snap()], fmt="json")

    data = json.loads(path.read_text())
    assert len(data) == 1
    record = data[0]
    assert record["source"] == "MySQL"
    assert record["target"] == "orders"
    assert record["metrics"]["row_count"] == 1000
    assert record["status"] == "ok"
    assert "collected_at" in record


def test_json_multiple_snapshots(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    snaps = [_snap("MySQL", "orders"), _snap("Redis", "session:*")]
    path = exporter.export(snaps, fmt="json")

    data = json.loads(path.read_text())
    assert len(data) == 2


# ── CSV ─────────────────────────────────────────────────────────────────────

def test_csv_header_row(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([_snap()], fmt="csv")

    lines = path.read_text().strip().split("\n")
    assert lines[0] == "source,target,status,row_count,size_mb,collected_at"


def test_csv_data_row(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([_snap()], fmt="csv")

    lines = path.read_text().strip().split("\n")
    assert "MySQL" in lines[1]
    assert "orders" in lines[1]
    assert "1000" in lines[1]


# ── 텍스트 ───────────────────────────────────────────────────────────────────

def test_text_contains_source_and_target(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([_snap()], fmt="text")

    content = path.read_text()
    assert "MySQL" in content
    assert "orders" in content


# ── 파일 경로 ────────────────────────────────────────────────────────────────

def test_auto_filename_pattern(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([_snap()], fmt="json")

    assert "snapshot_" in path.name
    assert path.suffix == ".json"


def test_auto_filename_csv_ext(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([_snap()], fmt="csv")

    assert path.suffix == ".csv"


def test_custom_output_path(tmp_path: Path) -> None:
    exporter = Exporter(str(tmp_path / "snapshots"))
    custom = str(tmp_path / "my_report.json")
    path = exporter.export([_snap()], fmt="json", output=custom)

    assert path == Path(custom)
    assert path.exists()


def test_snapshot_dir_created_automatically(tmp_path: Path) -> None:
    snap_dir = tmp_path / "deep" / "nested" / "snapshots"
    exporter = Exporter(str(snap_dir))
    exporter.export([_snap()], fmt="json")

    assert snap_dir.exists()


# ── Redis 메트릭 폴백 ─────────────────────────────────────────────────────────

def test_redis_key_count_in_csv(tmp_path: Path) -> None:
    redis_snap = MetricSnapshot(
        source_name="Redis",
        target="session:*",
        collected_at=datetime.fromisoformat("2026-05-08T12:00:00"),
        metrics={"key_count": 3201, "memory_usage_mb": 8.0},
    )
    exporter = Exporter(str(tmp_path / "snapshots"))
    path = exporter.export([redis_snap], fmt="csv")

    content = path.read_text()
    assert "3201" in content
