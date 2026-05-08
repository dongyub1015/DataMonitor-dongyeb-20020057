# PRD: DataMonitor — 콘솔 기반 실시간 데이터 상태 조회 관리자 도구

**문서 버전**: 1.0  
**작성일**: 2026-05-08  
**상태**: 초안

---

## 1. 개요

### 1.1 목적

운영 중인 시스템의 저장 데이터 상태(DB, 캐시, 파일 등)를 별도 GUI 없이 터미널(콘솔)에서 실시간으로 조회·모니터링할 수 있는 관리자 전용 CLI 도구를 개발한다.

### 1.2 배경 및 문제 정의

| 현황 문제 | 영향 |
|---|---|
| 데이터 이상 발생 시 DB 클라이언트를 별도로 열어야 함 | 장애 대응 시간 증가 |
| 실시간 변화 추이를 눈으로 확인할 방법이 없음 | 문제 패턴 파악 어려움 |
| 비개발자 운영팀이 직접 쿼리를 작성해야 함 | 휴먼 에러 위험 |

### 1.3 목표

- 콘솔 하나로 주요 데이터 지표를 **실시간(폴링 또는 스트림)** 으로 확인
- 관리자가 **키보드만으로** 데이터 소스 전환·필터링·정렬 수행
- 이상 값 감지 시 콘솔 내 **시각적 경고**(색상, 기호) 즉시 표시

---

## 2. 사용자 및 사용 시나리오

### 2.1 주요 사용자

| 페르소나 | 역할 | 핵심 니즈 |
|---|---|---|
| 백엔드 엔지니어 | 개발·운영 | 특정 테이블 레코드 수·최신 row 실시간 확인 |
| DevOps / SRE | 시스템 운영 | 전체 데이터 소스 헬스 한눈에 파악 |
| 운영팀 담당자 | 비즈니스 운영 | 주문·재고 등 핵심 수치 빠르게 조회 |

### 2.2 핵심 시나리오

1. **장애 대응**: 서비스 이상 발생 → 콘솔에서 DataMonitor 실행 → 3초 내 이상 지표 특정
2. **정기 점검**: 배치 작업 완료 후 결과 데이터 건수 및 오류 로우 즉시 확인
3. **용량 모니터링**: 테이블/캐시 크기 추이를 실시간 그래프(ASCII)로 확인

---

## 3. 기능 요구사항

### 3.1 F1 — 대시보드 뷰 (기본 화면)

- 실행 즉시 **설정된 데이터 소스 목록과 핵심 지표**를 표 형태로 출력
- 지정 주기(기본 `5s`, 최소 `1s`)로 자동 갱신
- 화면 상단: 현재 시각, 갱신 주기, 연결된 소스 수 표시
- 이상 임계값 초과 셀은 색상(빨강/노랑)으로 강조

```
╔══════════════════════════════════════════════════════════════╗
║  DataMonitor v1.0        2026-05-08 14:32:05   Refresh: 5s  ║
╠══════════╦══════════════╦═══════════╦════════╦═══════════════╣
║ Source   ║ Table / Key  ║ Row Count ║ Size   ║ Last Updated  ║
╠══════════╬══════════════╬═══════════╬════════╬═══════════════╣
║ MySQL    ║ orders       ║    12,847 ║  24MB  ║ 0s ago        ║
║ MySQL    ║ users        ║   430,012 ║ 512MB  ║ 0s ago        ║
║ Redis    ║ session:*    ║     3,201 ║   8MB  ║ 0s ago        ║
║ [!] PG   ║ audit_log    ║ 9,999,999 ║  98%   ║ 12s ago       ║  ← 경고
╚══════════╩══════════════╩═══════════╩════════╩═══════════════╝
[q] Quit  [r] Refresh  [f] Filter  [s] Sort  [d] Detail  [e] Export
```

### 3.2 F2 — 상세 뷰

- 대시보드에서 항목 선택 → 해당 테이블/키의 **최근 N개 레코드** 미리보기
- 컬럼 너비 자동 조정, 긴 값은 말줄임 처리
- 페이지네이션 (`PgUp` / `PgDn`)

### 3.3 F3 — 실시간 변화 추이 (Sparkline)

- 선택한 지표(레코드 수, 응답 시간 등)를 ASCII 스파크라인으로 표시
- 최근 60개 샘플 보관, 화면 너비에 맞춰 동적 리사이즈

```
orders row count (last 60s)
▁▂▃▄▅▆▇█▇▆▅▅▆▇▇▆▅▅▄▄▄▅▆▇█▇▆▅▄▃▂▁  12,847 (+23)
```

### 3.4 F4 — 필터 및 검색

- `/` 키로 인라인 검색 모드 진입
- 테이블명, 소스명, 컬럼명으로 필터링
- 와일드카드 지원(`orders*`, `*log`)

### 3.5 F5 — 알림 규칙 (Alert Rule)

- 설정 파일(`config.yaml`)에 임계값 규칙 정의
- 조건 충족 시 콘솔 벨(`\a`) + 화면 깜빡임 + 상태바 메시지
- 알림 이력은 세션 내 로그에 보관

```yaml
# config.yaml 예시
alerts:
  - source: MySQL
    table: orders
    metric: row_count
    condition: ">= 10000"
    level: warning
```

### 3.6 F6 — 스냅샷 내보내기

- `e` 키 → 현재 대시보드 상태를 **JSON / CSV / 텍스트** 파일로 저장
- 파일명 자동 생성: `snapshot_20260508_143205.json`

### 3.7 F7 — 다중 데이터 소스 지원

| 소스 유형 | 지원 여부 | 비고 |
|---|---|---|
| MySQL / MariaDB | ✅ | `pymysql` |
| PostgreSQL | ✅ | `psycopg2` |
| SQLite | ✅ | 내장 |
| Redis | ✅ | `redis-py` |
| MongoDB | 🔲 v2 예정 | |
| REST API 엔드포인트 | 🔲 v2 예정 | |

---

## 4. 비기능 요구사항

| 항목 | 요구 수준 |
|---|---|
| 갱신 지연 | 갱신 주기 ±200ms 이내 |
| CPU 사용률 | 유휴 시 < 2% (폴링 5s 기준) |
| 메모리 | 프로세스 상주 < 50MB |
| 터미널 호환 | Windows Terminal, iTerm2, Linux xterm |
| Python 버전 | 3.10 이상 |
| 최소 터미널 크기 | 80×24 characters |
| 의존성 설치 | `pip install -e .` 단일 명령으로 완료 |

---

## 5. 기술 스택 및 아키텍처

### 5.1 핵심 라이브러리

| 역할 | 선택 라이브러리 | 근거 |
|---|---|---|
| TUI 렌더링 | `textual` | 비동기 이벤트 루프, 위젯 시스템 |
| DB 연결 풀 | `sqlalchemy` (core only) | 다중 소스 추상화 |
| Redis 연결 | `redis[hiredis]` | 고성능 파서 |
| 설정 파싱 | `pydantic` + `pyyaml` | 타입 안전 설정 |
| 비동기 처리 | `asyncio` (표준 라이브러리) | |

### 5.2 컴포넌트 구조

```
DataMonitor/
├── datamonitor/
│   ├── __main__.py          # 진입점: python -m datamonitor
│   ├── app.py               # Textual App 루트
│   ├── config.py            # 설정 로딩 (pydantic)
│   ├── sources/
│   │   ├── base.py          # DataSource 추상 클래스
│   │   ├── mysql.py
│   │   ├── postgres.py
│   │   ├── sqlite.py
│   │   └── redis.py
│   ├── widgets/
│   │   ├── dashboard.py     # 메인 테이블 위젯
│   │   ├── detail.py        # 상세 뷰 위젯
│   │   ├── sparkline.py     # 추이 그래프 위젯
│   │   └── statusbar.py     # 하단 상태바
│   ├── alerts.py            # 알림 규칙 평가기
│   └── exporter.py          # 스냅샷 내보내기
├── config.yaml              # 기본 설정 파일
├── pyproject.toml
└── PRD.md
```

### 5.3 데이터 흐름

```
┌─────────────┐   async poll   ┌──────────────┐   metrics   ┌─────────────┐
│  DataSource │ ─────────────▶ │PollScheduler │ ──────────▶ │  AlertEval  │
│  (MySQL 등) │                └──────────────┘             └──────┬──────┘
└─────────────┘                        │ DataSnapshot              │ alert
                                       ▼                           ▼
                               ┌──────────────┐         ┌─────────────────┐
                               │  App State   │ ──────▶ │  TUI Renderer   │
                               │  (in-memory) │         │  (Textual)      │
                               └──────────────┘         └─────────────────┘
```

---

## 6. 사용자 인터페이스 — 키 바인딩

| 키 | 동작 |
|---|---|
| `q` / `Ctrl+C` | 종료 |
| `r` | 즉시 수동 갱신 |
| `+` / `-` | 갱신 주기 증감 (1s 단위) |
| `↑` / `↓` | 항목 선택 이동 |
| `Enter` | 상세 뷰 진입 |
| `Esc` | 이전 뷰로 돌아가기 |
| `f` | 필터 입력창 열기 |
| `s` | 정렬 기준 순환 (이름 → 크기 → 변화율) |
| `g` | 스파크라인 뷰 토글 |
| `e` | 현재 상태 스냅샷 내보내기 |
| `?` | 키 바인딩 도움말 표시 |

---

## 7. 설정 파일 명세 (`config.yaml`)

```yaml
refresh_interval: 5          # 기본 갱신 주기 (초)
max_rows_preview: 20         # 상세 뷰 미리보기 행 수
snapshot_dir: "./snapshots"  # 내보내기 저장 경로

sources:
  - name: MySQL-Prod
    type: mysql
    host: localhost
    port: 3306
    database: app_db
    user: monitor_user
    password: "${MYSQL_MONITOR_PASSWORD}"   # 환경변수 참조
    watch:
      - table: orders
        metrics: [row_count, table_size_mb]
      - table: users
        metrics: [row_count]

  - name: Redis-Cache
    type: redis
    host: localhost
    port: 6379
    db: 0
    watch:
      - pattern: "session:*"
        metrics: [key_count, memory_usage_mb]

alerts:
  - source: MySQL-Prod
    target: orders
    metric: row_count
    condition: ">= 50000"
    level: critical
```

---

## 8. 실행 방법

```bash
# 설치
pip install -e .

# 기본 실행 (config.yaml 자동 탐색)
python -m datamonitor

# 설정 파일 명시
python -m datamonitor --config /path/to/config.yaml

# 특정 소스만 조회
python -m datamonitor --source MySQL-Prod

# 갱신 주기 오버라이드
python -m datamonitor --interval 2

# 비대화형 스냅샷 (CI/CD 파이프라인용)
python -m datamonitor --snapshot --format json --output report.json
```

---

## 9. 보안 고려사항

- DB 비밀번호는 `config.yaml`에 평문 저장 **금지** — 환경변수(`${VAR}`) 또는 `.env` 파일 참조
- 연결 계정은 **읽기 전용 권한** (`SELECT`, `SHOW`) 만 부여
- 콘솔 출력에 민감 컬럼(패스워드 해시, 주민번호 등) 마스킹 설정 지원
- 설정 파일 권한: `chmod 600 config.yaml` 권고 사항 문서화

---

## 10. 개발 단계 및 마일스톤

| 단계 | 내용 | 목표 일정 |
|---|---|---|
| M1 | 프로젝트 구조 셋업, MySQL/SQLite 연결, 기본 대시보드 출력 | +2주 |
| M2 | PostgreSQL·Redis 소스 추가, 알림 규칙 엔진 | +4주 |
| M3 | 스파크라인 뷰, 필터·정렬, 스냅샷 내보내기 | +6주 |
| M4 | 통합 테스트, 문서화, PyPI 패키지 배포 | +8주 |

---

## 11. 성공 지표 (KPI)

| 지표 | 목표 |
|---|---|
| 장애 인지까지 평균 시간 | 도구 도입 전 대비 50% 단축 |
| 관리자 쿼리 직접 작성 횟수 | 월 20건 → 5건 이하 |
| 초기 설정 소요 시간 | 신규 소스 추가 5분 이내 |
| 갱신 주기 준수율 | 95% 이상 (±200ms 이내) |

---

## 12. 미결 사항 (Open Questions)

- [ ] MongoDB 지원을 v1에 포함할지 여부 → 팀 우선순위 논의 필요
- [ ] 알림을 Slack / 이메일로 외부 발송하는 기능 범위 포함 여부
- [ ] 다중 사용자 동시 접속 시 공유 세션(tmux 등) 외 별도 지원 필요 여부
- [ ] 읽기 전용 외 긴급 데이터 수정(`UPDATE`/`DELETE`) 기능 포함 여부 (보안 리스크 검토 필요)
