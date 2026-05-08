# PLAN: DataMonitor 구현 계획

**기반 문서**: PRD.md v1.0  
**작성일**: 2026-05-08  
**전체 일정**: 8주 (4 Phase)

---

## Phase 개요

```
Phase 1 ─── Phase 2 ─── Phase 3 ─── Phase 4
W1  W2      W3  W4      W5  W6      W7  W8
│   │       │   │       │   │       │   │
기반  핵심DB   소스확장  폴링   고급UX  내보내기  품질  배포
설정  TUI셸   PG·Redis  알림   상세뷰  스파크라인 테스트 패키징
```

---

## Phase 1 — 기반 & 핵심 (W1–W2)

**목표**: 실행 가능한 TUI 셸 + SQLite/MySQL 연결 + 정적 대시보드

### 1-1. 프로젝트 구조 셋업

- [ ] `pyproject.toml` 작성 (의존성, 빌드 설정, entry point)
- [ ] `datamonitor/` 패키지 디렉터리 및 `__init__.py` 생성
- [ ] `datamonitor/__main__.py` CLI 진입점 (argparse)
- [ ] `config.yaml` 기본 템플릿 생성
- [ ] `.gitignore`, `README.md` 초안

**산출물**: `pip install -e .` 및 `python -m datamonitor --help` 동작

### 1-2. 설정 시스템

- [ ] `datamonitor/config.py` — pydantic 모델로 `config.yaml` 파싱
- [ ] 환경변수 치환 (`${VAR}` → `os.environ`)
- [ ] 설정 파일 자동 탐색 순서 정의 (`./config.yaml` → `~/.datamonitor/config.yaml`)
- [ ] 설정 유효성 검사 오류 시 사용자 친화적 메시지 출력

**관련 설계 문서**: `docs/design/05-config-schema.md`

### 1-3. DataSource 추상 레이어

- [ ] `datamonitor/sources/base.py` — `DataSource` ABC 정의
  - `async def connect() -> None`
  - `async def fetch_metrics() -> list[MetricSnapshot]`
  - `async def fetch_rows(target, limit) -> RowPreview`
  - `async def disconnect() -> None`
- [ ] `MetricSnapshot`, `RowPreview` 데이터 클래스 정의
- [ ] `datamonitor/sources/sqlite.py` 구현
- [ ] `datamonitor/sources/mysql.py` 구현 (pymysql + SQLAlchemy core)

**관련 설계 문서**: `docs/design/02-data-sources.md`

### 1-4. TUI 앱 셸

- [ ] `datamonitor/app.py` — Textual `App` 서브클래스, 화면 구조 정의
- [ ] `datamonitor/widgets/dashboard.py` — 메인 테이블 위젯 (정적 렌더링)
- [ ] `datamonitor/widgets/statusbar.py` — 하단 상태바 (시각, 소스 수, 키 힌트)
- [ ] `q` / `Ctrl+C` 종료, `?` 도움말 키 바인딩

**산출물**: 설정 파일을 읽어 테이블을 한 번 렌더링하는 TUI 실행

**관련 설계 문서**: `docs/design/03-tui-layout.md`

### Phase 1 완료 기준

- `python -m datamonitor` 실행 시 TUI 화면 출력
- SQLite/MySQL 연결 후 row_count, table_size 조회 성공
- 설정 오류 시 친화적 에러 메시지 출력 후 종료

---

## Phase 2 — 소스 확장 & 실시간 폴링 (W3–W4)

**목표**: 모든 v1 데이터 소스 지원 + 자동 갱신 + 알림 엔진

### 2-1. 추가 데이터 소스

- [ ] `datamonitor/sources/postgres.py` (psycopg2)
- [ ] `datamonitor/sources/redis.py` (redis[hiredis])
  - `key_count`: `DBSIZE` 또는 `SCAN` + count
  - `memory_usage_mb`: `INFO memory`
  - 패턴 매칭: `SCAN MATCH <pattern>`

**관련 설계 문서**: `docs/design/02-data-sources.md`

### 2-2. PollScheduler (비동기 폴링 루프)

- [ ] `datamonitor/scheduler.py` — `PollScheduler` 구현
  - 각 소스를 독립 `asyncio.Task`로 병렬 폴링
  - 갱신 주기 변경 시 Task 재스케줄링
  - 소스 연결 실패 시 재시도 (exponential backoff, max 3회)
- [ ] 폴링 결과를 `AppState`에 저장 → Textual reactive 변수 연동
- [ ] 대시보드 위젯 자동 갱신 연결

**관련 설계 문서**: `docs/design/01-architecture.md`

### 2-3. Alert 엔진

- [ ] `datamonitor/alerts.py` — `AlertEvaluator` 구현
  - 조건 파싱: `">= 10000"`, `"< 5"` 등 문자열 → 비교 함수
  - 매 폴링 후 모든 알림 규칙 평가
  - 상태 변화(정상→경고→위험)만 이벤트 발생 (중복 알림 방지)
- [ ] 알림 발생 시:
  - 대시보드 해당 행 색상 강조 (warning=노랑, critical=빨강)
  - 상태바에 알림 메시지 표시
  - 콘솔 벨 출력 (`\a`)
- [ ] 세션 알림 이력: 인메모리 `deque(maxlen=100)` 보관

**관련 설계 문서**: `docs/design/04-alert-engine.md`

### 2-4. 키 바인딩 확장

- [ ] `r` — 즉시 수동 갱신
- [ ] `+` / `-` — 갱신 주기 증감 (1s 단위, 최소 1s)
- [ ] `↑` / `↓` — 행 선택 이동

### Phase 2 완료 기준

- 4개 소스(MySQL, PostgreSQL, SQLite, Redis) 동시 폴링 동작
- 알림 규칙 위반 시 색상 강조 및 상태바 메시지 출력
- 갱신 주기 변경이 즉시 반영

---

## Phase 3 — 고급 UX (W5–W6)

**목표**: 상세 뷰, 스파크라인, 필터/정렬, 스냅샷 내보내기

### 3-1. 상세 뷰 위젯

- [ ] `datamonitor/widgets/detail.py` — `Enter` 키로 진입
  - 선택된 테이블/키의 최근 N행 조회 후 렌더링
  - 컬럼 너비 자동 계산 (터미널 폭 기준)
  - 긴 값 말줄임 (`...`) 처리
- [ ] 페이지네이션: `PgUp` / `PgDn`
- [ ] `Esc` 또는 `q` 로 대시보드 복귀

### 3-2. 스파크라인 위젯

- [ ] `datamonitor/widgets/sparkline.py`
  - `deque(maxlen=60)` 로 샘플 보관
  - Unicode 블록 문자(`▁▂▃▄▅▆▇█`)로 ASCII 그래프 렌더링
  - 화면 너비에 맞춰 표시 샘플 수 동적 조정
  - 현재값 및 전 샘플 대비 변화량(`+23`) 표시
- [ ] `g` 키로 대시보드 하단 스파크라인 패널 토글

### 3-3. 필터 및 정렬

- [ ] `/` 키 → 하단 검색 입력창 활성화
  - 입력 중 실시간 필터링 (소스명, 테이블명 대상)
  - 와일드카드: `*` → `.*` 정규식 변환
  - `Esc` 로 필터 해제
- [ ] `s` 키 → 정렬 기준 순환
  - 순서: 이름(ASC) → 크기(DESC) → 변화율(DESC) → 기본(설정 순서)
  - 현재 정렬 기준 상태바에 표시

### 3-4. 스냅샷 내보내기

- [ ] `datamonitor/exporter.py` — `Exporter` 구현
  - JSON: 전체 `AppState` 직렬화
  - CSV: 대시보드 테이블 행 목록
  - 텍스트: 현재 화면 ASCII 렌더링
- [ ] `e` 키 → 포맷 선택 모달 → 저장
- [ ] 파일명 자동 생성: `snapshot_YYYYMMDD_HHMMSS.<ext>`
- [ ] 비대화형 모드: `--snapshot --format json --output <path>` CLI 옵션

### Phase 3 완료 기준

- 상세 뷰 진입·복귀 정상 동작
- 스파크라인이 60샘플 기준 올바르게 렌더링
- 필터 입력 시 실시간 행 필터링
- `e` 키로 JSON/CSV/텍스트 파일 저장 성공

---

## Phase 4 — 품질 & 배포 (W7–W8)

**목표**: 테스트 커버리지 확보, 문서화, PyPI 릴리스

### 4-1. 테스트

- [ ] `tests/unit/` — 단위 테스트
  - `test_config.py`: 설정 파싱, 환경변수 치환, 유효성 검사
  - `test_alerts.py`: 조건 파싱, 상태 전이, 중복 방지
  - `test_exporter.py`: JSON/CSV/텍스트 출력 형식 검증
  - `test_sparkline.py`: 샘플 보관, Unicode 렌더링
- [ ] `tests/integration/` — 통합 테스트
  - SQLite 소스: 실제 파일 DB 연결·조회
  - 폴링 루프: 2사이클 실행 후 `AppState` 갱신 확인
- [ ] `pytest-asyncio` 활용, 커버리지 목표 70%+

### 4-2. 성능 프로파일링

- [ ] 유휴 CPU < 2% 검증 (5s 폴링, 단일 소스)
- [ ] 메모리 < 50MB 검증 (`tracemalloc`)
- [ ] 갱신 지연 ±200ms 이내 검증

### 4-3. 문서화

- [ ] `README.md` 완성 (설치, 빠른 시작, 설정 예시, 스크린샷)
- [ ] `config.yaml.example` — 전체 옵션 주석 포함
- [ ] `CHANGELOG.md` v1.0.0 항목
- [ ] 보안 가이드: 읽기 전용 계정 생성 SQL 예시

### 4-4. 패키징 & 릴리스

- [ ] `pyproject.toml` classifiers, license, homepage 정비
- [ ] `python -m build` 빌드 검증
- [ ] PyPI TestPyPI 업로드 테스트
- [ ] PyPI 정식 릴리스 (v1.0.0)

### Phase 4 완료 기준

- `pytest` 전체 통과
- CPU/메모리 비기능 요구사항 충족 확인
- PyPI에서 `pip install datamonitor` 설치 성공

---

## 의존성 관리

```toml
# pyproject.toml dependencies
[project.dependencies]
textual = ">=0.50"
sqlalchemy = ">=2.0"
pymysql = ">=1.1"
psycopg2-binary = ">=2.9"
redis = {version = ">=5.0", extras = ["hiredis"]}
pydantic = ">=2.0"
pyyaml = ">=6.0"
python-dotenv = ">=1.0"

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pytest-cov", "ruff", "mypy"]
```

---

## 설계 문서 목록

| 파일 | 내용 | 담당 Phase |
|---|---|---|
| `docs/design/01-architecture.md` | 전체 시스템 아키텍처, 컴포넌트 관계, 데이터 흐름 | Phase 1–2 |
| `docs/design/02-data-sources.md` | DataSource ABC, 각 소스 구현 명세, 메트릭 정의 | Phase 1–2 |
| `docs/design/03-tui-layout.md` | Textual 위젯 계층, 화면 레이아웃, 키 바인딩 상태머신 | Phase 1–3 |
| `docs/design/04-alert-engine.md` | 알림 조건 파싱, 상태 전이, 이벤트 버스 설계 | Phase 2 |
| `docs/design/05-config-schema.md` | config.yaml 전체 스키마, pydantic 모델, 환경변수 처리 | Phase 1 |

---

## 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|---|---|---|
| Textual API 변경 (버전 업) | 중 | 버전 고정 (`textual>=0.50,<1.0`) |
| psycopg2 Windows 빌드 실패 | 중 | `psycopg2-binary` 사용, 실패 시 `asyncpg` 대안 |
| Redis 패턴 SCAN 성능 (대용량 키) | 중 | 타임아웃 설정, SCAN count 조정 옵션 제공 |
| 터미널 크기 < 80×24 | 저 | 최소 크기 미달 시 경고 메시지 출력 후 계속 |
