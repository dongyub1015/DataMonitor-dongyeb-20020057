from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .sources.base import DataSource, MetricSnapshot

log = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3


class PollScheduler:
    """소스별 독립 asyncio.Task로 폴링을 수행한다.

    한 소스의 실패가 다른 소스에 전파되지 않도록 Task를 분리한다.
    """

    def __init__(
        self,
        sources: list[DataSource],
        interval: int,
        on_update: Callable[[list[MetricSnapshot]], None],
    ) -> None:
        self._sources = sources
        self._interval = interval
        self._on_update = on_update
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._tasks = [
            asyncio.create_task(self._poll_loop(src), name=f"poll:{src.name}")
            for src in self._sources
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def set_interval(self, interval: int) -> None:
        self._interval = interval

    async def trigger_once(self) -> None:
        """모든 소스를 즉시 한 번 폴링한다 (수동 갱신용)."""
        tasks = [asyncio.create_task(self._poll_source_once(src)) for src in self._sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        snapshots: list[MetricSnapshot] = []
        for r in results:
            if isinstance(r, list):
                snapshots.extend(r)
        if snapshots:
            self._on_update(snapshots)

    # ── 내부 폴링 루프 ────────────────────────────────────────────────────

    async def _poll_loop(self, source: DataSource) -> None:
        attempt = 0
        while self._running:
            snapshots = await self._poll_source_once(source)
            if snapshots is not None:
                attempt = 0
                self._on_update(snapshots)
            else:
                attempt += 1
                backoff = min(2 ** (attempt - 1), 30)
                log.warning(
                    "[%s] 폴링 실패 (시도 %d/%d) — %ds 후 재시도",
                    source.name,
                    attempt,
                    _MAX_ATTEMPTS,
                    backoff,
                )
                if attempt >= _MAX_ATTEMPTS:
                    log.error("[%s] 최대 재시도 초과. 폴링 중단.", source.name)
                    break
                await asyncio.sleep(backoff)
                continue

            await asyncio.sleep(self._interval)

    async def _poll_source_once(self, source: DataSource) -> list[MetricSnapshot] | None:
        try:
            await source.connect()
            snapshots = await source.fetch_metrics()
            return snapshots
        except Exception as exc:
            log.debug("[%s] 폴링 오류: %s", source.name, exc)
            return None
        finally:
            await source.disconnect()
