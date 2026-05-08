from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


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
    def _table_or_pattern(self) -> "WatchTarget":
        if self.table is None and self.pattern is None:
            raise ValueError("watch 항목은 table 또는 pattern 중 하나가 필요합니다.")
        return self


class SourceConfig(BaseModel):
    name: str
    type: Literal["mysql", "postgres", "sqlite", "redis"]
    host: str = "localhost"
    port: int | None = None
    database: str | None = None
    path: str | None = None
    user: str | None = None
    password: str | None = None
    db: int = 0
    connect_timeout: int = 5
    query_timeout: int = 5
    watch: list[WatchTarget] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError(f"소스 이름에 공백을 사용할 수 없습니다: {v!r}")
        return v

    def __repr__(self) -> str:
        d = self.model_dump()
        if d.get("password"):
            d["password"] = "***"
        return f"SourceConfig({d})"


class AlertRule(BaseModel):
    source: str
    target: str
    metric: str
    condition: str
    level: AlertLevel

    @field_validator("condition")
    @classmethod
    def _valid_condition(cls, v: str) -> str:
        if not re.match(r"^\s*(>=|<=|>|<|==|!=)\s*\d+(?:\.\d+)?\s*$", v):
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
    def _alert_sources_exist(self) -> "AppConfig":
        source_names = {s.name for s in self.sources}
        for rule in self.alerts:
            if rule.source not in source_names:
                raise ValueError(
                    f"알림 규칙의 source '{rule.source}'가 sources 목록에 없습니다."
                )
        return self


_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(value: str) -> str:
    def _replace(m: re.Match) -> str:
        var = m.group(1)
        result = os.environ.get(var)
        if result is None:
            raise EnvironmentError(
                f"환경변수 '{var}'가 설정되지 않았습니다.\n"
                "  .env 파일 또는 셸 환경변수를 확인하세요."
            )
        return result

    return _ENV_RE.sub(_replace, value)


def _subst_recursive(obj: object) -> object:
    if isinstance(obj, str):
        return _substitute_env(obj)
    if isinstance(obj, dict):
        return {k: _subst_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_recursive(i) for i in obj]
    return obj


def _find_config_file(path: str | Path | None) -> Path:
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"오류: 설정 파일을 찾을 수 없습니다: {p}")
        return p

    candidates: list[Path] = [
        Path("config.yaml"),
        Path.home() / ".datamonitor" / "config.yaml",
    ]
    if os.name != "nt":
        candidates.append(Path("/etc/datamonitor/config.yaml"))

    for c in candidates:
        if c.exists():
            return c

    raise SystemExit(
        "오류: 설정 파일을 찾을 수 없습니다.\n"
        "  다음 중 하나를 생성하거나 --config 옵션으로 경로를 지정하세요:\n"
        "    ./config.yaml\n"
        "    ~/.datamonitor/config.yaml\n"
        "  예시: cp config.yaml.example config.yaml"
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    resolved = _find_config_file(path)

    try:
        from dotenv import load_dotenv

        env_file = resolved.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass

    raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}

    try:
        substituted = _subst_recursive(raw)
    except EnvironmentError as e:
        raise SystemExit(f"환경변수 오류:\n  {e}") from None

    try:
        return AppConfig.model_validate(substituted)
    except ValidationError as e:
        raise SystemExit(f"설정 파일 오류 ({resolved}):\n{e}") from None
