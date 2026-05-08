from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .base import DataSource, MetricSnapshot, RowPreview, SourceStatus

if TYPE_CHECKING:
    from ..config import SourceConfig

_MAX_SCAN_ITER = 10_000


class RedisSource(DataSource):
    def __init__(self, config: "SourceConfig") -> None:
        super().__init__(config)
        self._client: object | None = None

    def _build_url(self) -> str:
        c = self.config
        port = c.port or 6379
        if c.password:
            return f"redis://:{c.password}@{c.host}:{port}/{c.db}"
        return f"redis://{c.host}:{port}/{c.db}"

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(
            self._build_url(),
            socket_connect_timeout=self.config.connect_timeout,
            decode_responses=False,
        )
        await self._client.ping()  # type: ignore[union-attr]

    async def fetch_metrics(self) -> list[MetricSnapshot]:
        results: list[MetricSnapshot] = []
        for watch in self.config.watch:
            if watch.pattern is None:
                continue
            snap = await self._fetch_pattern(watch.pattern)
            results.append(snap)
        return results

    async def _fetch_pattern(self, pattern: str) -> MetricSnapshot:
        import redis.asyncio as aioredis

        client: aioredis.Redis = self._client  # type: ignore[assignment]
        try:
            key_count = 0
            truncated = False
            async for _ in client.scan_iter(match=pattern, count=100):
                key_count += 1
                if key_count >= _MAX_SCAN_ITER:
                    truncated = True
                    break

            info = await client.info("memory")
            used_mem: int = info.get("used_memory", 0)
            memory_mb = round(used_mem / 1024 / 1024, 2)

            metrics: dict = {
                "key_count": key_count,
                "memory_usage_mb": memory_mb,
            }
            if truncated:
                metrics["truncated"] = True

            return MetricSnapshot(
                source_name=self.name,
                target=pattern,
                collected_at=datetime.now(),
                metrics=metrics,
            )
        except Exception as e:
            return MetricSnapshot(
                source_name=self.name,
                target=pattern,
                collected_at=datetime.now(),
                status=SourceStatus.ERROR,
                error_msg=str(e),
            )

    async def fetch_rows(self, target: str, limit: int, offset: int = 0) -> RowPreview:
        import redis.asyncio as aioredis

        client: aioredis.Redis = self._client  # type: ignore[assignment]
        keys: list = []
        async for key in client.scan_iter(match=target, count=100):
            keys.append(key)
            if len(keys) >= offset + limit:
                break

        page_keys = keys[offset : offset + limit]
        rows: list[list] = []
        for key in page_keys:
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            raw_type = await client.type(key)
            key_type = raw_type.decode() if isinstance(raw_type, bytes) else str(raw_type)
            ttl: int = await client.ttl(key)
            mem: int = await client.memory_usage(key) or 0
            rows.append([key_str, key_type, ttl, mem])

        return RowPreview(
            source_name=self.name,
            target=target,
            columns=["key", "type", "ttl_sec", "memory_bytes"],
            rows=rows,
            total_fetched=len(rows),
            page=offset // limit if limit else 0,
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            import redis.asyncio as aioredis

            client: aioredis.Redis = self._client  # type: ignore[assignment]
            await client.aclose()
            self._client = None
