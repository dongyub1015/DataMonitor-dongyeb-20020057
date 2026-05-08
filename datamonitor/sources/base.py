from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import SourceConfig


class SourceStatus(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"


@dataclass
class MetricSnapshot:
    source_name: str
    target: str
    collected_at: datetime
    status: SourceStatus = SourceStatus.OK
    metrics: dict[str, Any] = field(default_factory=dict)
    error_msg: str | None = None

    @property
    def row_count(self) -> int | None:
        return self.metrics.get("row_count")

    @property
    def size_mb(self) -> float | None:
        return self.metrics.get("size_mb")


@dataclass
class RowPreview:
    source_name: str
    target: str
    columns: list[str]
    rows: list[list[Any]]
    total_fetched: int
    page: int = 0


class DataSource(ABC):
    def __init__(self, config: "SourceConfig") -> None:
        self.config = config
        self.name = config.name

    @abstractmethod
    async def connect(self) -> None:
        """연결 수립. 실패 시 ConnectionError raise."""

    @abstractmethod
    async def fetch_metrics(self) -> list[MetricSnapshot]:
        """설정된 모든 watch 대상의 지표를 반환. 오류 시 status=ERROR 스냅샷 반환."""

    @abstractmethod
    async def fetch_rows(self, target: str, limit: int, offset: int = 0) -> RowPreview:
        """상세 뷰용 row 미리보기."""

    @abstractmethod
    async def disconnect(self) -> None:
        """연결 해제. 예외를 억제한다."""

    async def __aenter__(self) -> "DataSource":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
