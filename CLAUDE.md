# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 프로젝트 개요

DataMonitor는 콘솔에서 실행하는 Python TUI 도구로, DB·캐시 등 저장 데이터 상태를 실시간으로 조회·모니터링한다. GUI 없이 터미널 하나로 운영하는 것이 핵심 가치다.

**기반 문서**: `PRD.md` (요구사항) · `PLAN.md` (구현 계획) · `docs/design/` (상세 설계)

---

## 개발 명령어

```bash
# 개발 의존성 포함 설치
pip install -e ".[dev]"

# 실행
python -m datamonitor
python -m datamonitor --config config.yaml
python -m datamonitor --snapshot --format json --output report.json  # 비대화형

# 테스트
pytest                                    # 전체
pytest tests/unit/                        # 단위 테스트만
pytest tests/unit/test_alerts.py -v       # 단일 파일
pytest --cov=datamonitor --cov-report=term-missing  # 커버리지

# 린트 / 타입 검사
ruff check datamonitor/
mypy datamonitor/

# 패키징
python -m build
```

---

## 아키텍처

### 컴포넌트 관계

```
__main__.py (argparse)
    └── app.py (DataMonitorApp : Textual App)
            ├── config.py          설정 로딩 (pydantic + yaml)
            ├── scheduler.py       PollScheduler — 소스별 asyncio.Task
            │       └── sources/   DataSource 구현체들
            ├── alerts.py          AlertEvaluator
            ├── exporter.py        JSON/CSV/Text 내보내기
            └── widgets/           Textual 위젯 (UI 전용)
```

**핵심 불변식**: `widgets/` 모듈은 `app.py`를 import하지 않는다. 위젯은 Textual reactive/message 시스템을 통해서만 데이터를 받는다.

### 데이터 흐름

1. `PollScheduler`가 소스별 독립 `asyncio.Task`를 생성해 `DataSource.fetch_metrics()`를 주기적으로 호출한다.
2. 결과 `MetricSnapshot`이 `AppState`에 저장되면 Textual reactive가 `DashboardWidget`을 자동 갱신한다.
3. 매 폴링 후 `AlertEvaluator.evaluate(snapshot)`이 호출되고, **상태 전이가 발생할 때만** `AlertEvent`를 발행한다 (동일 레벨 반복 알림 없음).

### 비동기 처리 규칙

- 모든 동기 DB 드라이버(pymysql, psycopg2, sqlite3)는 `asyncio.to_thread()`로 감싼다.
- Redis만 `redis.asyncio` 네이티브 비동기 클라이언트를 사용한다.
- 한 소스의 폴링 실패가 다른 소스에 전파되면 안 된다 — `PollScheduler`가 소스별로 예외를 격리한다.

---

## DataSource 추가 방법

새 소스를 추가할 때 따를 패턴:

1. `datamonitor/sources/base.py`의 `DataSource` ABC를 상속
2. `connect()` / `fetch_metrics()` / `fetch_rows()` / `disconnect()` 4개 메서드 구현
3. `fetch_metrics()`는 항상 `MetricSnapshot` 리스트를 반환 — 오류 시 `status=ERROR` 스냅샷 반환 (예외 전파 금지)
4. `datamonitor/sources/__init__.py`의 `create_source()` 팩토리에 매핑 추가
5. `SourceConfig.type`의 `Literal` 타입에 새 문자열 추가

메트릭 키는 소스 유형 무관하게 `row_count`, `size_mb`, `size_pct`, `query_time_ms`로 정규화한다 (`docs/design/02-data-sources.md` §2 참조).

---

## Alert 엔진 핵심 규칙

- 조건 문자열 `">= 50000"` 등은 앱 시작 시 파싱·컴파일 — 런타임 파싱 없음
- CRITICAL과 WARNING 규칙이 같은 target+metric에 공존할 때, CRITICAL 조건 충족 시 WARNING 이벤트는 억제
- `AlertEvaluator._state`가 상태를 보관 — 동일 레벨 유지 중에는 이벤트를 발행하지 않음
- 규칙 ID 형식: `"{source}:{target}:{metric}:{level}"`

---

## 설정 시스템

- `config.yaml` 값 중 `${ENV_VAR}` 형식 문자열은 환경변수로 치환 (`datamonitor/config.py`)
- `SourceConfig.password`는 로그·repr에서 `***`로 마스킹 필수
- `AppConfig`의 Pydantic `model_validator`가 알림 규칙의 source 참조 유효성을 시작 시 검증
- 설정 오류는 `SystemExit`으로 처리 — 예외를 상위로 전파하지 않음

---

## TUI 위젯 개발 시 주의사항

- 화면 갱신은 `DataTable.update_cell()`로 변경된 셀만 업데이트 (전체 재렌더링 방지)
- "Last Updated" 컬럼은 `Textual Timer(interval=1)`로 독립 갱신
- 최소 터미널 크기 80×24 — `App.on_resize()`에서 미달 시 경고 오버레이 표시 (종료 없음)
- 스파크라인 렌더링: `deque(maxlen=60)` 샘플, Unicode 블록 문자 `▁▂▃▄▅▆▇█` 사용

---

## SQL 보안

- 테이블명은 `config.yaml`의 `watch[].table` 허용 목록에서만 사용, 실행 시 `^[a-zA-Z0-9_]+$` 검증
- 모든 값 파라미터는 SQLAlchemy `:param` 바인딩 사용 — f-string SQL 금지
- `fetch_rows()` 쿼리의 `LIMIT`/`OFFSET`은 바인딩 파라미터로만 전달

---

## 구현 진행 상태

현재 Phase 1 진행 전 (소스 코드 없음). `PLAN.md`의 Phase별 완료 기준을 체크포인트로 사용한다.

| Phase | 기간 | 핵심 목표 |
|---|---|---|
| 1 | W1–2 | 프로젝트 구조, SQLite/MySQL, 정적 대시보드 TUI |
| 2 | W3–4 | PostgreSQL/Redis, 비동기 폴링, 알림 엔진 |
| 3 | W5–6 | 상세 뷰, 스파크라인, 필터/정렬, 내보내기 |
| 4 | W7–8 | 테스트(목표 커버리지 70%+), 성능 검증, PyPI 배포 |
