from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING

from .base import DataSource, MetricSnapshot, RowPreview, SourceStatus

if TYPE_CHECKING:
    from ..config import SourceConfig


class SQLiteSource(DataSource):
    def __init__(self, config: "SourceConfig") -> None:
        super().__init__(config)
        self._path: str = config.path or ""

    async def connect(self) -> None:
        if not self._path:
            raise ConnectionError("SQLite 소스에 path가 설정되지 않았습니다.")
        if not os.path.exists(self._path):
            raise ConnectionError(f"SQLite 파일을 찾을 수 없습니다: {self._path}")

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
            conn = sqlite3.connect(self._path, timeout=self.config.query_timeout)
            try:
                (row_count,) = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
                size_mb = round(os.path.getsize(self._path) / 1024 / 1024, 2)
                return MetricSnapshot(
                    source_name=self.name,
                    target=table,
                    collected_at=datetime.now(),
                    metrics={"row_count": int(row_count), "size_mb": size_mb},
                )
            finally:
                conn.close()
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
        conn = sqlite3.connect(self._path, timeout=self.config.query_timeout)
        try:
            cur = conn.execute(
                f'SELECT * FROM "{target}" LIMIT ? OFFSET ?', (limit, offset)
            )
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()]
            return RowPreview(
                source_name=self.name,
                target=target,
                columns=columns,
                rows=rows,
                total_fetched=len(rows),
                page=offset // limit if limit else 0,
            )
        finally:
            conn.close()

    async def disconnect(self) -> None:
        pass  # 연결이 쿼리별로 열리고 닫힘
