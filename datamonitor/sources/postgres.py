from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .base import DataSource, MetricSnapshot, RowPreview, SourceStatus

if TYPE_CHECKING:
    from ..config import SourceConfig

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _safe_table(name: str) -> str:
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"유효하지 않은 테이블명: {name!r}")
    return name


class PostgresSource(DataSource):
    def __init__(self, config: "SourceConfig") -> None:
        super().__init__(config)
        self._engine: Engine | None = None

    def _build_url(self) -> str:
        c = self.config
        port = c.port or 5432
        user = c.user or ""
        pwd = c.password or ""
        return f"postgresql+psycopg2://{user}:{pwd}@{c.host}:{port}/{c.database}"

    async def connect(self) -> None:
        await asyncio.to_thread(self._create_engine)

    def _create_engine(self) -> None:
        self._engine = create_engine(
            self._build_url(),
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args={"connect_timeout": self.config.connect_timeout},
        )
        with self._engine.connect():
            pass

    async def fetch_metrics(self) -> list[MetricSnapshot]:
        results: list[MetricSnapshot] = []
        for watch in self.config.watch:
            if watch.table is None:
                continue
            snap = await asyncio.to_thread(self._fetch_table, watch.table)
            results.append(snap)
        return results

    def _fetch_table(self, table: str) -> MetricSnapshot:
        try:
            _safe_table(table)
            with self._engine.connect() as conn:  # type: ignore[union-attr]
                row_count: Any = conn.execute(
                    text("SELECT reltuples::bigint FROM pg_class WHERE relname = :tbl"),
                    {"tbl": table},
                ).scalar() or 0

                size_mb: Any = conn.execute(
                    text("SELECT pg_total_relation_size(:tbl) / 1024.0 / 1024.0"),
                    {"tbl": table},
                ).scalar() or 0.0

            return MetricSnapshot(
                source_name=self.name,
                target=table,
                collected_at=datetime.now(),
                metrics={"row_count": int(row_count), "size_mb": round(float(size_mb), 2)},
            )
        except Exception as e:
            return MetricSnapshot(
                source_name=self.name,
                target=table,
                collected_at=datetime.now(),
                status=SourceStatus.ERROR,
                error_msg=str(e),
            )

    async def fetch_rows(self, target: str, limit: int, offset: int = 0) -> RowPreview:
        return await asyncio.to_thread(self._fetch_rows, target, limit, offset)

    def _fetch_rows(self, target: str, limit: int, offset: int) -> RowPreview:
        _safe_table(target)
        with self._engine.connect() as conn:  # type: ignore[union-attr]
            result = conn.execute(
                text(f'SELECT * FROM "{target}" LIMIT :lim OFFSET :off'),
                {"lim": limit, "off": offset},
            )
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchall()]
        return RowPreview(
            source_name=self.name,
            target=target,
            columns=columns,
            rows=rows,
            total_fetched=len(rows),
            page=offset // limit if limit else 0,
        )

    async def disconnect(self) -> None:
        if self._engine is not None:
            await asyncio.to_thread(self._engine.dispose)
            self._engine = None
