from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from datamonitor.config import AppConfig, load_config


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def test_minimal_config_uses_defaults(tmp_path: Path) -> None:
    p = _write(tmp_path, {"sources": []})
    cfg = load_config(p)
    assert isinstance(cfg, AppConfig)
    assert cfg.refresh_interval == 5
    assert cfg.max_rows_preview == 20


def test_refresh_interval_override(tmp_path: Path) -> None:
    p = _write(tmp_path, {"refresh_interval": 10, "sources": []})
    cfg = load_config(p)
    assert cfg.refresh_interval == 10


def test_env_var_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PASS_XYZ", "supersecret")
    p = _write(tmp_path, {
        "sources": [{
            "name": "MySQL-Test",
            "type": "mysql",
            "database": "testdb",
            "password": "${TEST_PASS_XYZ}",
            "watch": [],
        }]
    })
    cfg = load_config(p)
    assert cfg.sources[0].password == "supersecret"


def test_missing_env_var_exits(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "sources": [{
            "name": "MySQL-Test",
            "type": "mysql",
            "database": "db",
            "password": "${__NONEXISTENT_VAR_12345__}",
            "watch": [],
        }]
    })
    with pytest.raises(SystemExit):
        load_config(p)


def test_source_name_with_space_is_invalid(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "sources": [{
            "name": "My Source",
            "type": "sqlite",
            "path": "/tmp/test.db",
            "watch": [],
        }]
    })
    with pytest.raises(SystemExit):
        load_config(p)


def test_alert_referencing_unknown_source_exits(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "sources": [],
        "alerts": [{
            "source": "NoSuchSource",
            "target": "orders",
            "metric": "row_count",
            "condition": ">= 1000",
            "level": "warning",
        }],
    })
    with pytest.raises(SystemExit):
        load_config(p)


def test_invalid_alert_condition_exits(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "sources": [{
            "name": "DB",
            "type": "sqlite",
            "path": "/tmp/db",
            "watch": [],
        }],
        "alerts": [{
            "source": "DB",
            "target": "orders",
            "metric": "row_count",
            "condition": "INVALID",
            "level": "warning",
        }],
    })
    with pytest.raises(SystemExit):
        load_config(p)


def test_config_file_not_found_exits() -> None:
    with pytest.raises(SystemExit):
        load_config("/nonexistent/__datamonitor_test_xyz__.yaml")


def test_password_hidden_in_repr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PASS_REPR", "verysecret")
    p = _write(tmp_path, {
        "sources": [{
            "name": "MySQL-Repr",
            "type": "mysql",
            "database": "db",
            "password": "${TEST_PASS_REPR}",
            "watch": [],
        }]
    })
    cfg = load_config(p)
    assert "verysecret" not in repr(cfg.sources[0])
    assert "***" in repr(cfg.sources[0])
