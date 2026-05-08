from __future__ import annotations

import logging
import operator
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .config import AlertLevel, AlertRule
from .sources.base import MetricSnapshot

log = logging.getLogger(__name__)

_OP_MAP: dict[str, Callable] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}
_COND_RE = re.compile(r"^\s*(>=|<=|>|<|==|!=)\s*(\d+(?:\.\d+)?)\s*$")

_OK = "ok"  # 정상 상태 sentinel (AlertLevel 아님)


@dataclass
class AlertEvent:
    rule_id: str
    source_name: str
    target: str
    metric: str
    value: float | int
    level: AlertLevel | str    # AlertLevel 또는 "ok" (복구)
    prev_level: AlertLevel | str
    triggered_at: datetime
    message: str

    @property
    def is_recovery(self) -> bool:
        return self.level == _OK


def _parse_condition(condition: str) -> tuple[Callable, float]:
    m = _COND_RE.match(condition)
    if not m:
        raise ValueError(f"조건 파싱 실패: {condition!r}")
    return _OP_MAP[m.group(1)], float(m.group(2))


class AlertEvaluator:
    """매 폴링 후 알림 규칙을 평가하고 상태 전이 시에만 AlertEvent를 발행한다."""

    def __init__(self, rules: list[AlertRule]) -> None:
        # CRITICAL 규칙을 먼저 평가
        self._rules = sorted(
            rules, key=lambda r: 0 if r.level == AlertLevel.CRITICAL else 1
        )
        self._compiled: dict[str, tuple[Callable, float]] = {}
        self._state: dict[str, AlertLevel | str] = {}
        self._compile_all()

    def _compile_all(self) -> None:
        for rule in self._rules:
            rule_id = _rule_id(rule)
            try:
                self._compiled[rule_id] = _parse_condition(rule.condition)
                self._state[rule_id] = _OK
            except ValueError as e:
                log.warning("알림 규칙 비활성화: %s — %s", rule_id, e)

    def evaluate(self, snapshot: MetricSnapshot) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        # CRITICAL이 충족된 (source, target, metric) 집합 — WARNING 억제용
        critical_fired: set[tuple[str, str, str]] = set()

        for rule in self._rules:
            if rule.source != snapshot.source_name or rule.target != snapshot.target:
                continue

            rid = _rule_id(rule)
            if rid not in self._compiled:
                continue

            value = snapshot.metrics.get(rule.metric)
            if value is None:
                continue

            op_fn, threshold = self._compiled[rid]
            triggered: bool = op_fn(value, threshold)

            if triggered and rule.level == AlertLevel.CRITICAL:
                critical_fired.add((rule.source, rule.target, rule.metric))

            # 같은 metric에서 CRITICAL이 이미 발화했으면 WARNING 억제
            key = (rule.source, rule.target, rule.metric)
            if triggered and rule.level == AlertLevel.WARNING and key in critical_fired:
                continue

            new_level: AlertLevel | str = rule.level if triggered else _OK
            prev_level = self._state[rid]

            if new_level != prev_level:
                self._state[rid] = new_level
                events.append(
                    AlertEvent(
                        rule_id=rid,
                        source_name=rule.source,
                        target=rule.target,
                        metric=rule.metric,
                        value=value,
                        level=new_level,
                        prev_level=prev_level,
                        triggered_at=snapshot.collected_at,
                        message=_format_message(rule, value, new_level),
                    )
                )

        return events


def _rule_id(rule: AlertRule) -> str:
    return f"{rule.source}:{rule.target}:{rule.metric}:{rule.level.value}"


def _format_message(
    rule: AlertRule, value: float | int, level: AlertLevel | str
) -> str:
    if level == _OK:
        verb = "✓ 해제"
    elif level == AlertLevel.CRITICAL:
        verb = "⛔ [CRITICAL]"
    else:
        verb = "⚠ [WARNING]"
    return (
        f"{verb} {rule.source} › {rule.target}: "
        f"{rule.metric}={value:,} ({rule.condition})"
    )
