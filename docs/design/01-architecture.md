# 설계: 전체 시스템 아키텍처

**담당 Phase**: Phase 1–2  
**최종 수정**: 2026-05-08

---

## 1. 아키텍처 개요

DataMonitor는 **이벤트 기반 비동기 TUI 애플리케이션**이다. Textual의 비동기 이벤트 루프 위에서 폴링 스케줄러와 알림 평가기가 동작하며, 모든 UI 갱신은 Textual의 reactive 시스템을 통해 이루어진다.

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLI Entry Point                           │
│              python -m datamonitor [options]                     │
└─────────────────────────────┬────────────────────────────────────┘
                              │ argparse → AppConfig
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DataMonitorApp (Textual)                    │
│                                                                  │
│  ┌────────────┐   ┌──────────────────┐   ┌───────────────────┐  │
│  │ AppState   │◀──│  PollScheduler   │──▶│  AlertEvaluator   │  │
│  │ (reactive) │   │  (asyncio Tasks) │   │                   │  │
│  └────────────┘   └──────────────────┘   └───────────────────┘  │
│         │                  │                        │            │
│         ▼                  │                        │            │
│  ┌──────────────────────┐  │  ┌─────────────────────────────┐   │
│  │   TUI Widget Layer   │  │  │      DataSource Layer        │   │
│  │                      │  │  │                              │   │
│  │ DashboardWidget      │  └─▶│ MySQLSource                  │   │
│  │ DetailWidget         │     │ PostgresSource               │   │
│  │ SparklineWidget      │     │ SQLiteSource                 │   │
│  │ StatusBarWidget      │     │ RedisSource                  │   │
│  └──────────────────────┘     └─────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼ (e 키)
┌────────────────┐
│   Exporter     │
│ JSON/CSV/Text  │
└────────────────┘
```

---

## 2. 핵심 컴포넌트

### 2.1 AppState

모든 런타임 데이터를 보관하는 단일 진실 공급원(Single Source of Truth).

```python
@dataclass
class AppState:
    snapshots: dict[str, MetricSnapshot]   # source_key → 최신 지표
    history: dict[str, deque[MetricSnapshot]]  # 스파크라인용 60샘플
    alerts: deque[AlertEvent]              # 세션 알림 이력 (maxlen=100)
    filter_text: str                       # 현재 필터 문자열
    sort_mode: SortMode                    # 현재 정렬 기준
    selected_row: int                      # 커서 위치
    refresh_interval: int                  # 현재 갱신 주기 (초)
```

Textual의 `reactive` 데코레이터를 활용해 `snapshots` 변경 시 DashboardWidget이 자동 갱신된다.

### 2.2 PollScheduler

```
PollScheduler
├── 소스별 독립 asyncio.Task 생성
├── 각 Task: sleep(interval) → source.fetch_metrics() → AppState 갱신
├── 갱신 주기 변경: 기존 Task 취소 → 새 Task 생성
└── 소스 연결 실패: exponential backoff (1s → 2s → 4s, max 3회)
```

**핵심 불변식**: 한 소스의 폴링 실패가 다른 소스에 영향을 주지 않는다.

### 2.3 AlertEvaluator

매 폴링 완료 후 `PollScheduler`가 호출한다. 조건 평가 결과를 이전 상태(`prev_level`)와 비교해 **상태 전이가 발생할 때만** `AlertEvent`를 발행한다 — 중복 알림 방지.

```
정상(ok) → 경고(warning) → 위험(critical)  : 이벤트 발행
위험(critical) → 경고(warning) → 정상(ok)  : 복구 이벤트 발행
동일 레벨 유지                             : 이벤트 없음
```

---

## 3. 데이터 흐름 상세

### 3.1 정상 갱신 사이클

```
1. PollScheduler.Task(MySQL-Prod)
   └─▶ MySQLSource.fetch_metrics()
       └─▶ SQLAlchemy execute: SELECT COUNT(*), ... FROM information_schema
       └─▶ MetricSnapshot(source="MySQL-Prod", table="orders", row_count=12847, ...)

2. PollScheduler
   └─▶ AppState.update(snapshot)
       └─▶ AppState.history["MySQL-Prod:orders"].append(snapshot)

3. AlertEvaluator.evaluate(snapshot)
   └─▶ rule: row_count >= 50000? → No → ok 유지

4. Textual reactive 트리거
   └─▶ DashboardWidget.refresh()
       └─▶ 해당 행 데이터 갱신, Last Updated = "0s ago"
```

### 3.2 알림 발생 사이클

```
1. MetricSnapshot(row_count=51000)
2. AlertEvaluator: 51000 >= 50000 → critical
3. prev_level[rule_id] == ok → 상태 전이 발생
4. AlertEvent 발행:
   └─▶ AppState.alerts.append(event)
   └─▶ StatusBarWidget: 알림 메시지 표시
   └─▶ DashboardWidget: 해당 행 [!] 빨강 강조
   └─▶ sys.stdout.write("\a")  # 콘솔 벨
```

### 3.3 소스 연결 실패

```
MySQLSource.fetch_metrics() raises ConnectionError
└─▶ PollScheduler.handle_error()
    └─▶ MetricSnapshot(status=ERROR, error_msg="Connection refused")
    └─▶ AppState.update(snapshot)
    └─▶ DashboardWidget: 해당 행 회색 표시 + "ERR" 표시
    └─▶ backoff: sleep(2^attempt), max attempt=3
    └─▶ 3회 실패 → status=DISCONNECTED, 폴링 중단
```

---

## 4. 비동기 모델

```
asyncio event loop (Textual 관리)
├── PollScheduler.Task(MySQL-Prod)   # 독립 코루틴
├── PollScheduler.Task(Redis-Cache)  # 독립 코루틴
├── PollScheduler.Task(PG-Prod)      # 독립 코루틴
├── Textual UI event loop            # 키 입력, 화면 갱신
└── Textual Timer (Last Updated 카운터)  # 1초 주기
```

모든 DB I/O는 `asyncio.to_thread()`로 동기 드라이버를 감싸 이벤트 루프를 블록하지 않는다.  
Redis는 `redis.asyncio` 클라이언트를 사용해 네이티브 비동기 처리한다.

---

## 5. 모듈 의존 관계

```
__main__.py
    └── app.py (DataMonitorApp)
            ├── config.py (AppConfig, SourceConfig, AlertRule)
            ├── scheduler.py (PollScheduler)
            │       └── sources/base.py (DataSource ABC)
            │               ├── sources/mysql.py
            │               ├── sources/postgres.py
            │               ├── sources/sqlite.py
            │               └── sources/redis.py
            ├── alerts.py (AlertEvaluator)
            ├── exporter.py (Exporter)
            └── widgets/
                    ├── dashboard.py
                    ├── detail.py
                    ├── sparkline.py
                    └── statusbar.py
```

**순환 의존 없음**: `widgets` → `app` 방향 import 금지. 위젯은 `AppState`를 직접 참조하지 않고 Textual message/reactive를 통해 데이터를 받는다.

---

## 6. 오류 격리 전략

| 계층 | 오류 유형 | 처리 |
|---|---|---|
| DataSource | 연결 실패 | `status=ERROR` 스냅샷 발행, backoff 재시도 |
| DataSource | 쿼리 타임아웃 | 5초 타임아웃 설정, 타임아웃 시 `status=TIMEOUT` |
| AlertEvaluator | 조건 파싱 오류 | 앱 시작 시 사전 검증, 실패 시 해당 규칙 비활성화 |
| Exporter | 파일 쓰기 실패 | 상태바에 오류 메시지, 앱 종료 없음 |
| TUI 렌더링 | 터미널 크기 < 80×24 | 경고 오버레이 표시, 최대한 렌더링 시도 |
