# 설계: Alert 엔진

**담당 Phase**: Phase 2  
**최종 수정**: 2026-05-08

---

## 1. 개요

Alert 엔진은 매 폴링 사이클 후 `AlertEvaluator`가 호출되어 모든 알림 규칙을 평가한다. 핵심 설계 원칙은 **상태 전이 기반 이벤트** — 동일 상태가 지속되는 동안은 알림을 반복 발생시키지 않는다.

---

## 2. 데이터 모델

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AlertLevel(Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    id: str                    # "MySQL-Prod:orders:row_count:warning"
    source_name: str
    target: str                # 테이블명 또는 Redis 패턴
    metric: str                # "row_count", "size_mb", ...
    condition: str             # ">= 50000", "< 5", "> 90.0"
    level: AlertLevel


@dataclass
class AlertEvent:
    rule_id: str
    source_name: str
    target: str
    metric: str
    value: float | int
    level: AlertLevel
    prev_level: AlertLevel
    triggered_at: datetime
    message: str               # 사람이 읽을 수 있는 설명
```

---

## 3. 조건 파싱

```python
# datamonitor/alerts.py

import operator
import re

_OP_MAP = {
    ">=": operator.ge,
    "<=": operator.le,
    ">":  operator.gt,
    "<":  operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}

_CONDITION_RE = re.compile(r"^\s*(>=|<=|>|<|==|!=)\s*(\d+(?:\.\d+)?)\s*$")

def parse_condition(condition: str) -> tuple[callable, float]:
    """
    ">= 50000" → (operator.ge, 50000.0)
    파싱 실패 시 ValueError raise.
    """
    m = _CONDITION_RE.match(condition)
    if not m:
        raise ValueError(f"알림 조건 파싱 실패: {condition!r}")
    op_fn = _OP_MAP[m.group(1)]
    threshold = float(m.group(2))
    return op_fn, threshold
```

앱 시작 시 모든 AlertRule의 condition을 미리 파싱한다. 파싱 실패 규칙은 경고 로그 후 비활성화된다.

---

## 4. 상태 전이 모델

```
         ┌──────────────────────────────────────────┐
         │              AlertEvaluator               │
         │                                           │
         │  _state: dict[rule_id → AlertLevel]       │
         │                                           │
         │  초기값: AlertLevel.OK                    │
         └──────────────────────────────────────────┘

상태 전이 규칙:
─────────────────────────────────────────────────────
현재 상태    조건 평가    → 새 상태    이벤트 발행?
─────────────────────────────────────────────────────
OK          False        OK          아니오 (변화 없음)
OK          True         WARNING     예 (OK → WARNING)
WARNING     True         WARNING     아니오 (동일 레벨)
WARNING     False        OK          예 (경고 해제)
CRITICAL    True (≥)    CRITICAL    아니오
WARNING     True (≥)    CRITICAL    예 (에스컬레이션)
─────────────────────────────────────────────────────

규칙 우선순위: CRITICAL 규칙이 WARNING 규칙보다 먼저 평가.
같은 target+metric에 CRITICAL과 WARNING 규칙이 모두 있을 때,
CRITICAL 조건을 만족하면 WARNING 이벤트는 억제한다.
```

---

## 5. AlertEvaluator 구현 구조

```python
class AlertEvaluator:
    def __init__(self, rules: list[AlertRule]) -> None:
        self._rules = sorted(rules, key=lambda r: r.level.value, reverse=True)
        self._compiled: dict[str, tuple[callable, float]] = {}
        self._state: dict[str, AlertLevel] = {}
        self._compile_all()

    def _compile_all(self) -> None:
        for rule in self._rules:
            try:
                self._compiled[rule.id] = parse_condition(rule.condition)
                self._state[rule.id] = AlertLevel.OK
            except ValueError as e:
                # 시작 시 경고, 해당 규칙 비활성화
                logging.warning("알림 규칙 비활성화: %s — %s", rule.id, e)

    def evaluate(self, snapshot: MetricSnapshot) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        value = snapshot.metrics.get(rule.metric)

        for rule in self._rules:
            if rule.source_name != snapshot.source_name:
                continue
            if rule.target != snapshot.target:
                continue
            if rule.id not in self._compiled:
                continue

            value = snapshot.metrics.get(rule.metric)
            if value is None:
                continue

            op_fn, threshold = self._compiled[rule.id]
            triggered = op_fn(value, threshold)
            new_level = rule.level if triggered else AlertLevel.OK
            prev_level = self._state[rule.id]

            if new_level != prev_level:
                self._state[rule.id] = new_level
                events.append(AlertEvent(
                    rule_id=rule.id,
                    source_name=rule.source_name,
                    target=rule.target,
                    metric=rule.metric,
                    value=value,
                    level=new_level,
                    prev_level=prev_level,
                    triggered_at=snapshot.collected_at,
                    message=self._format_message(rule, value, new_level),
                ))

        return events

    def _format_message(
        self, rule: AlertRule, value: float, level: AlertLevel
    ) -> str:
        verb = "해제" if level == AlertLevel.OK else f"[{level.value.upper()}]"
        return f"{verb} {rule.source_name} › {rule.target}: {rule.metric}={value:,} ({rule.condition})"
```

---

## 6. 알림 이벤트 처리 흐름

```
PollScheduler
    └─▶ AlertEvaluator.evaluate(snapshot)
           └─▶ list[AlertEvent]
                   └─▶ DataMonitorApp.handle_alerts(events)
                           ├─▶ AppState.alerts.append(event)      # 이력 보관
                           ├─▶ StatusBarWidget.show_alert(event)  # 상태바 표시
                           ├─▶ DashboardWidget.mark_row(event)    # 행 색상 변경
                           └─▶ sys.stdout.write("\a")             # 콘솔 벨
```

---

## 7. 알림 이력 관리

```python
# AppState 내부
alerts: deque[AlertEvent] = field(default_factory=lambda: deque(maxlen=100))
```

- 세션 종료 시 이력 소멸 (파일 지속성 없음, v1 범위)
- 알림 이력 조회: `?` 도움말 모달에서 마지막 10건 표시 (Phase 3에서 별도 뷰 검토)

---

## 8. 상태바 알림 표시 규칙

| 조건 | 표시 내용 | 지속 시간 |
|---|---|---|
| CRITICAL 발생 | `⛔ [CRITICAL] MySQL-Prod › orders: row_count=51,000` | 30초 또는 다음 이벤트까지 |
| WARNING 발생 | `⚠ [WARNING] MySQL-Prod › orders: row_count=51,000` | 15초 또는 다음 이벤트까지 |
| OK 복구 | `✓ 해제 MySQL-Prod › orders: row_count=4,500` | 5초 |
| 다중 이벤트 | 가장 심각한 이벤트 표시 + `(+N개)` | - |

---

## 9. 설정 예시 및 규칙 ID 생성

```yaml
alerts:
  - source: MySQL-Prod
    target: orders
    metric: row_count
    condition: ">= 10000"
    level: warning

  - source: MySQL-Prod
    target: orders
    metric: row_count
    condition: ">= 50000"
    level: critical
```

규칙 ID 자동 생성 규칙:
```
"{source_name}:{target}:{metric}:{level}"
→ "MySQL-Prod:orders:row_count:warning"
→ "MySQL-Prod:orders:row_count:critical"
```

같은 source+target+metric에 복수 레벨이 있으면 CRITICAL이 충족될 때 WARNING 알림은 억제된다.
