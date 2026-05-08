# 설계: DataSource 레이어

**담당 Phase**: Phase 1–2  
**최종 수정**: 2026-05-08

---

## 1. DataSource 추상 클래스

모든 데이터 소스 구현체가 따르는 계약(contract)이다.

```python
# datamonitor/sources/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceStatus(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"


@dataclass
class MetricSnapshot:
    source_name: str
    target: str                     # 테이블명 또는 Redis 패턴
    collected_at: datetime
    status: SourceStatus = SourceStatus.OK
    metrics: dict[str, Any] = field(default_factory=dict)
    error_msg: str | None = None

    # 공통 지표 접근자 (메트릭 이름은 소스마다 동일하게 정규화)
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
        """설정된 모든 watch 대상의 지표를 조회해 반환."""

    @abstractmethod
    async def fetch_rows(self, target: str, limit: int, offset: int = 0) -> RowPreview:
        """상세 뷰용: 대상 테이블/키의 최근 row 미리보기."""

    @abstractmethod
    async def disconnect(self) -> None:
        """연결 해제. 예외를 억제한다."""

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()
```

---

## 2. 정규화된 메트릭 이름

소스 유형에 관계없이 동일한 키 이름을 사용한다.

| 메트릭 키 | 타입 | 설명 |
|---|---|---|
| `row_count` | `int` | 레코드(또는 키) 수 |
| `size_mb` | `float` | 테이블/DB/메모리 크기 (MiB) |
| `size_pct` | `float` | 용량 대비 사용률 0.0–100.0 |
| `last_modified` | `datetime` | 마지막 변경 시각 (지원 시) |
| `query_time_ms` | `float` | 메트릭 조회 소요 시간 |

---

## 3. MySQL / MariaDB 소스

```python
# datamonitor/sources/mysql.py
```

### 3.1 연결

- SQLAlchemy `create_engine()` + `asyncio.to_thread()` 래핑
- 연결 풀: `pool_size=2`, `max_overflow=0` (모니터 전용 최소 풀)
- 연결 문자열: `mysql+pymysql://user:password@host:port/database`

### 3.2 메트릭 조회 쿼리

**row_count**
```sql
SELECT TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = :database AND TABLE_NAME = :table;
```
> `TABLE_ROWS`는 InnoDB에서 추정값. 정확도가 필요한 경우 `SELECT COUNT(*)`를 fallback으로 제공하는 옵션(`exact_count: true`) 지원.

**size_mb**
```sql
SELECT ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS size_mb
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = :database AND TABLE_NAME = :table;
```

### 3.3 fetch_rows 쿼리

```sql
SELECT * FROM `{table}` ORDER BY 1 DESC LIMIT :limit OFFSET :offset;
```

> SQL injection 방지: 테이블명은 config에서 정의된 허용 목록(`watch[].table`)에서만 사용. `:limit`, `:offset`은 바인딩 파라미터.

---

## 4. PostgreSQL 소스

```python
# datamonitor/sources/postgres.py
```

### 4.1 연결

- `psycopg2` + `asyncio.to_thread()`
- 연결 문자열: `postgresql+psycopg2://user:password@host:port/database`

### 4.2 메트릭 조회 쿼리

**row_count** (빠른 추정값)
```sql
SELECT reltuples::bigint AS row_count
FROM pg_class
WHERE relname = :table;
```

**size_mb**
```sql
SELECT pg_total_relation_size(:table) / 1024.0 / 1024.0 AS size_mb;
```

**size_pct** (테이블스페이스 용량 대비 — 선택적)
```sql
SELECT pg_database_size(current_database()) / 1024.0 / 1024.0 AS db_size_mb;
```

---

## 5. SQLite 소스

```python
# datamonitor/sources/sqlite.py
```

### 5.1 특이사항

- 파일 기반: `config.path`에 `.db` 파일 경로 지정
- 연결: `sqlite3` 표준 라이브러리 + `asyncio.to_thread()`

### 5.2 메트릭 조회

**row_count**
```sql
SELECT COUNT(*) FROM "{table}";
```
> SQLite는 `information_schema` 미지원 → 직접 COUNT 사용.

**size_mb**
```python
import os
size_mb = os.path.getsize(db_path) / 1024 / 1024
```

---

## 6. Redis 소스

```python
# datamonitor/sources/redis.py
```

### 6.1 연결

- `redis.asyncio.Redis` (네이티브 비동기, `asyncio.to_thread` 불필요)
- 연결: `redis.asyncio.from_url(f"redis://{host}:{port}/{db}")`

### 6.2 메트릭 조회

**key_count (패턴 매칭)**
```
SCAN 0 MATCH <pattern> COUNT 100  → 반복 순회
```
> `KEYS <pattern>` 대신 `SCAN`을 사용해 블로킹 방지.  
> 큰 키스페이스 보호: 최대 10,000회 iteration 후 중단, `truncated=True` 플래그 설정.

**memory_usage_mb**
```
INFO memory → used_memory_human 파싱
```

### 6.3 fetch_rows (키 목록 미리보기)

```
SCAN → 최근 N개 키 수집
  └── TYPE key → string/hash/list/set/zset
  └── MEMORY USAGE key → 개별 키 크기 (bytes)
```

상세 뷰에서는 키 이름, 타입, TTL, 메모리 사용량을 컬럼으로 표시.

---

## 7. SourceConfig 스키마 (pydantic)

```python
from pydantic import BaseModel, Field
from typing import Literal

class WatchTarget(BaseModel):
    table: str | None = None          # SQL 소스용
    pattern: str | None = None        # Redis용
    metrics: list[str] = ["row_count", "size_mb"]
    exact_count: bool = False         # MySQL InnoDB 정확 카운트 여부

class SourceConfig(BaseModel):
    name: str
    type: Literal["mysql", "postgres", "sqlite", "redis"]
    host: str = "localhost"
    port: int | None = None           # None이면 소스 기본 포트 사용
    database: str | None = None
    path: str | None = None           # SQLite 전용
    user: str | None = None
    password: str | None = None       # 환경변수 치환 처리
    db: int = 0                       # Redis DB 인덱스
    connect_timeout: int = 5          # 초
    query_timeout: int = 5            # 초
    watch: list[WatchTarget] = Field(default_factory=list)
```

---

## 8. 소스 팩토리

```python
# datamonitor/sources/__init__.py

from .mysql import MySQLSource
from .postgres import PostgresSource
from .sqlite import SQLiteSource
from .redis import RedisSource
from .base import DataSource
from ..config import SourceConfig

def create_source(config: SourceConfig) -> DataSource:
    mapping = {
        "mysql": MySQLSource,
        "postgres": PostgresSource,
        "sqlite": SQLiteSource,
        "redis": RedisSource,
    }
    cls = mapping.get(config.type)
    if cls is None:
        raise ValueError(f"지원하지 않는 소스 유형: {config.type}")
    return cls(config)
```

---

## 9. 보안: SQL Injection 방지

| 위험 요소 | 대응 방법 |
|---|---|
| 테이블명 | config `watch[].table`의 허용 목록만 사용. 실행 시 `^[a-zA-Z0-9_]+$` 정규식 검증 |
| 파라미터 | SQLAlchemy `text()` + `:param` 바인딩 사용 |
| Redis 패턴 | `SCAN MATCH` 인수로만 사용, 쉘 실행 없음 |
| 연결 정보 | 환경변수 참조, 런타임 로그에 비밀번호 출력 금지 |
