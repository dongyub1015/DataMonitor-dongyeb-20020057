# 설계: 설정 스키마 및 로딩

**담당 Phase**: Phase 1  
**최종 수정**: 2026-05-08

---

## 1. 설정 파일 탐색 순서

`--config` 옵션이 없을 때 아래 순서로 파일을 탐색하고 처음 발견된 파일을 사용한다.

```
1. ./config.yaml             (현재 디렉터리)
2. ~/.datamonitor/config.yaml (사용자 홈)
3. /etc/datamonitor/config.yaml (시스템 전역, Linux/macOS)
```

파일이 없으면 명시적 오류 메시지 출력 후 종료:
```
오류: 설정 파일을 찾을 수 없습니다.
      다음 중 하나를 생성하거나 --config 옵션으로 경로를 지정하세요:
      - ./config.yaml
      - ~/.datamonitor/config.yaml
```

---

## 2. 전체 config.yaml 스키마

```yaml
# ─────────────────────────────────────────────
# DataMonitor 설정 파일 전체 스키마
# ─────────────────────────────────────────────

# 전역 설정
refresh_interval: 5          # 갱신 주기 (초), 최소: 1, 기본: 5
max_rows_preview: 20         # 상세 뷰 미리보기 행 수, 기본: 20
snapshot_dir: "./snapshots"  # 내보내기 저장 디렉터리
log_level: "WARNING"         # DEBUG | INFO | WARNING | ERROR
dotenv_file: ".env"          # 환경변수 파일 경로 (선택)

# 데이터 소스 목록
sources:
  - name: MySQL-Prod                        # 고유 이름 (공백 불가)
    type: mysql                             # mysql | postgres | sqlite | redis
    host: localhost
    port: 3306                              # 생략 시 소스 기본 포트 사용
    database: app_db
    user: monitor_user
    password: "${MYSQL_MONITOR_PASSWORD}"   # 환경변수 참조
    connect_timeout: 5                      # 연결 타임아웃 (초)
    query_timeout: 5                        # 쿼리 타임아웃 (초)
    watch:
      - table: orders
        metrics:
          - row_count
          - size_mb
        exact_count: false                  # true면 SELECT COUNT(*) 사용 (느림)
      - table: users
        metrics:
          - row_count

  - name: PG-Analytics
    type: postgres
    host: pg.internal
    port: 5432
    database: analytics
    user: monitor
    password: "${PG_MONITOR_PASSWORD}"
    watch:
      - table: events
        metrics: [row_count, size_mb]

  - name: SQLite-Local
    type: sqlite
    path: "/var/data/app.db"               # 절대 경로 권장
    watch:
      - table: jobs
        metrics: [row_count]

  - name: Redis-Cache
    type: redis
    host: localhost
    port: 6379
    db: 0                                  # Redis DB 인덱스
    password: "${REDIS_PASSWORD}"          # 선택
    watch:
      - pattern: "session:*"
        metrics: [key_count, memory_usage_mb]
      - pattern: "cache:product:*"
        metrics: [key_count]

# 알림 규칙
alerts:
  - source: MySQL-Prod                     # sources[].name 과 일치해야 함
    target: orders                         # 테이블명 또는 Redis 패턴
    metric: row_count                      # 평가할 메트릭 키
    condition: ">= 10000"                  # 지원: >= <= > < == !=
    level: warning                         # warning | critical

  - source: MySQL-Prod
    target: orders
    metric: row_count
    condition: ">= 50000"
    level: critical

  - source: Redis-Cache
    target: "session:*"
    metric: key_count
    condition: "> 10000"
    level: warning

# 민감 컬럼 마스킹 (선택)
masking:
  - source: MySQL-Prod
    table: users
    columns: [password_hash, ssn, credit_card]
    replacement: "***"
```

---

## 3. Pydantic 모델 정의

```python
# datamonitor/config.py

from __future__ import annotations
import os
import re
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AlertLevel(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class WatchTarget(BaseModel):
    table: str | None = None
    pattern: str | None = None
    metrics: list[str] = Field(default_factory=lambda: ["row_count", "size_mb"])
    exact_count: bool = False

    @model_validator(mode="after")
    def table_or_pattern(self) -> "WatchTarget":
        if self.table is None and self.pattern is None:
            raise ValueError("watch 항목은 table 또는 pattern 중 하나가 필요합니다.")
        return self


class SourceConfig(BaseModel):
    name: str
    type: Literal["mysql", "postgres", "sqlite", "redis"]
    host: str = "localhost"
    port: int | None = None
    database: str | None = None
    path: str | None = None            # SQLite 전용
    user: str | None = None
    password: str | None = None
    db: int = 0                        # Redis DB 인덱스
    connect_timeout: int = 5
    query_timeout: int = 5
    watch: list[WatchTarget] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError(f"소스 이름에 공백을 사용할 수 없습니다: {v!r}")
        return v


class AlertRule(BaseModel):
    source: str
    target: str
    metric: str
    condition: str
    level: AlertLevel

    @field_validator("condition")
    @classmethod
    def valid_condition(cls, v: str) -> str:
        pattern = r"^\s*(>=|<=|>|<|==|!=)\s*\d+(?:\.\d+)?\s*$"
        if not re.match(pattern, v):
            raise ValueError(f"지원하지 않는 조건 형식: {v!r}  (예: '>= 10000')")
        return v


class MaskingRule(BaseModel):
    source: str
    table: str
    columns: list[str]
    replacement: str = "***"


class AppConfig(BaseModel):
    refresh_interval: int = Field(default=5, ge=1)
    max_rows_preview: int = Field(default=20, ge=1, le=200)
    snapshot_dir: str = "./snapshots"
    log_level: LogLevel = LogLevel.WARNING
    dotenv_file: str | None = None
    sources: list[SourceConfig] = Field(default_factory=list)
    alerts: list[AlertRule] = Field(default_factory=list)
    masking: list[MaskingRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def alert_sources_exist(self) -> "AppConfig":
        source_names = {s.name for s in self.sources}
        for rule in self.alerts:
            if rule.source not in source_names:
                raise ValueError(
                    f"알림 규칙의 source '{rule.source}'가 sources 목록에 없습니다."
                )
        return self
```

---

## 4. 환경변수 치환

`${VAR_NAME}` 형식을 YAML 로딩 후 문자열 치환으로 처리한다.

```python
_ENV_RE = re.compile(r"\$\{([^}]+)\}")

def _substitute_env(value: str) -> str:
    def replace(m: re.Match) -> str:
        var_name = m.group(1)
        result = os.environ.get(var_name)
        if result is None:
            raise EnvironmentError(
                f"환경변수 '{var_name}'가 설정되지 않았습니다.\n"
                f"  .env 파일 또는 환경변수를 확인하세요."
            )
        return result
    return _ENV_RE.sub(replace, value)

def _substitute_env_recursive(obj: object) -> object:
    if isinstance(obj, str):
        return _substitute_env(obj)
    if isinstance(obj, dict):
        return {k: _substitute_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env_recursive(i) for i in obj]
    return obj
```

---

## 5. 설정 로딩 함수

```python
def load_config(path: str | Path | None = None) -> AppConfig:
    resolved = _find_config_file(path)

    # 1. .env 파일 로딩 (python-dotenv)
    _load_dotenv(resolved.parent)

    # 2. YAML 파싱
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}

    # 3. 환경변수 치환
    substituted = _substitute_env_recursive(raw)

    # 4. Pydantic 유효성 검사
    try:
        return AppConfig.model_validate(substituted)
    except ValidationError as e:
        raise SystemExit(f"설정 파일 오류:\n{e}") from None


def _find_config_file(path: str | Path | None) -> Path:
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"설정 파일 없음: {p}")
        return p

    candidates = [
        Path("config.yaml"),
        Path.home() / ".datamonitor" / "config.yaml",
        Path("/etc/datamonitor/config.yaml"),
    ]
    for c in candidates:
        if c.exists():
            return c

    raise SystemExit(
        "설정 파일을 찾을 수 없습니다.\n"
        "  ./config.yaml 을 생성하거나 --config 옵션을 사용하세요.\n"
        "  템플릿: https://github.com/your-org/datamonitor/blob/main/config.yaml.example"
    )
```

---

## 6. 소스별 기본 포트

`port: null` (미지정) 시 소스 유형에 따라 자동 결정:

| type | 기본 포트 |
|---|---|
| mysql | 3306 |
| postgres | 5432 |
| sqlite | N/A (파일 경로 사용) |
| redis | 6379 |

---

## 7. 보안 가이드라인

- **평문 비밀번호 금지**: `password:` 값은 반드시 `${ENV_VAR}` 형식으로 작성
- **파일 권한**: `config.yaml`에 `chmod 600` 적용 권고 (README에 문서화)
- **로그 출력 금지**: `SourceConfig.password` 필드는 `repr`/`str`에서 마스킹
  ```python
  def __repr__(self) -> str:
      d = self.model_dump()
      if d.get("password"):
          d["password"] = "***"
      return f"SourceConfig({d})"
  ```
- **민감 컬럼 마스킹**: `masking` 섹션에 정의된 컬럼은 Detail 뷰에서 `***` 치환
