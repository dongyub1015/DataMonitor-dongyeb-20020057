from __future__ import annotations

from datetime import datetime

import pytest

from datamonitor.alerts import AlertEvaluator, _OK
from datamonitor.config import AlertLevel, AlertRule
from datamonitor.sources.base import MetricSnapshot, SourceStatus


def _snap(source: str, target: str, **metrics: object) -> MetricSnapshot:
    return MetricSnapshot(
        source_name=source,
        target=target,
        collected_at=datetime.now(),
        metrics=dict(metrics),
    )


def _rule(
    source: str,
    target: str,
    metric: str,
    condition: str,
    level: AlertLevel,
) -> AlertRule:
    return AlertRule(
        source=source, target=target, metric=metric, condition=condition, level=level
    )


# ── 기본 동작 ────────────────────────────────────────────────────────────────

def test_no_event_below_threshold() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    assert ev.evaluate(_snap("db", "orders", row_count=500)) == []


def test_event_fires_on_threshold() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    events = ev.evaluate(_snap("db", "orders", row_count=1500))
    assert len(events) == 1
    assert events[0].level == AlertLevel.WARNING
    assert events[0].value == 1500


def test_no_duplicate_event_for_same_level() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    ev.evaluate(_snap("db", "orders", row_count=1500))   # 첫 발화
    assert ev.evaluate(_snap("db", "orders", row_count=2000)) == []  # 동일 레벨 → 무시


# ── 상태 전이 ─────────────────────────────────────────────────────────────────

def test_recovery_emits_event() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    ev.evaluate(_snap("db", "orders", row_count=1500))   # 경고 발화
    events = ev.evaluate(_snap("db", "orders", row_count=500))  # 복구
    assert len(events) == 1
    assert events[0].is_recovery
    assert events[0].level == _OK


def test_warning_then_critical_escalation() -> None:
    rules = [
        _rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING),
        _rule("db", "orders", "row_count", ">= 5000", AlertLevel.CRITICAL),
    ]
    ev = AlertEvaluator(rules)
    ev.evaluate(_snap("db", "orders", row_count=2000))   # WARNING 발화
    events = ev.evaluate(_snap("db", "orders", row_count=6000))  # CRITICAL 에스컬레이션
    critical = [e for e in events if e.level == AlertLevel.CRITICAL]
    assert len(critical) == 1


# ── CRITICAL이 WARNING을 억제 ──────────────────────────────────────────────────

def test_critical_suppresses_warning_on_same_metric() -> None:
    rules = [
        _rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING),
        _rule("db", "orders", "row_count", ">= 5000", AlertLevel.CRITICAL),
    ]
    ev = AlertEvaluator(rules)
    events = ev.evaluate(_snap("db", "orders", row_count=6000))
    levels = [e.level for e in events]
    assert AlertLevel.CRITICAL in levels
    assert AlertLevel.WARNING not in levels


# ── 다른 소스/타겟은 영향을 받지 않음 ──────────────────────────────────────────

def test_unrelated_source_not_triggered() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    events = ev.evaluate(_snap("other_db", "orders", row_count=9999))
    assert events == []


def test_unrelated_target_not_triggered() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    events = ev.evaluate(_snap("db", "users", row_count=9999))
    assert events == []


# ── 메트릭 누락 ───────────────────────────────────────────────────────────────

def test_missing_metric_no_event() -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", ">= 1000", AlertLevel.WARNING)])
    events = ev.evaluate(_snap("db", "orders", size_mb=100))  # row_count 없음
    assert events == []


# ── 조건 연산자 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("condition, value, expect_event", [
    (">= 100", 100, True),
    (">= 100", 99, False),
    ("<= 50", 50, True),
    ("<= 50", 51, False),
    ("> 100", 101, True),
    ("> 100", 100, False),
    ("< 50", 49, True),
    ("< 50", 50, False),
    ("== 42", 42, True),
    ("== 42", 43, False),
    ("!= 42", 43, True),
    ("!= 42", 42, False),
])
def test_condition_operators(condition: str, value: int, expect_event: bool) -> None:
    ev = AlertEvaluator([_rule("db", "orders", "row_count", condition, AlertLevel.WARNING)])
    events = ev.evaluate(_snap("db", "orders", row_count=value))
    assert bool(events) == expect_event
