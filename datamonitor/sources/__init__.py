from __future__ import annotations

from typing import TYPE_CHECKING

from .base import DataSource, MetricSnapshot, RowPreview, SourceStatus
from .mysql import MySQLSource
from .postgres import PostgresSource
from .redis import RedisSource
from .sqlite import SQLiteSource

if TYPE_CHECKING:
    from ..config import SourceConfig

__all__ = [
    "DataSource",
    "MetricSnapshot",
    "RowPreview",
    "SourceStatus",
    "create_source",
]


def create_source(config: "SourceConfig") -> DataSource:
    mapping: dict[str, type[DataSource]] = {
        "sqlite": SQLiteSource,
        "mysql": MySQLSource,
        "postgres": PostgresSource,
        "redis": RedisSource,
    }
    cls = mapping.get(config.type)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 소스 유형: {config.type!r}\n"
            f"  지원 유형: {', '.join(mapping)}"
        )
    return cls(config)
