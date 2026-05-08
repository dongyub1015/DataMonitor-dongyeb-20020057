# Changelog

## v0.1.0 (2026-05-08)

### 추가

**Phase 1 — 기반 & 핵심 TUI 셸**
- `config.py`: pydantic 기반 설정 로딩, 환경변수 치환, 친화적 오류 메시지
- `sources/base.py`: `DataSource` ABC, `MetricSnapshot`, `RowPreview` 데이터 클래스
- `sources/sqlite.py`: SQLite 소스 구현
- `sources/mysql.py`: MySQL/MariaDB 소스 구현 (SQL injection 방지 포함)
- `widgets/dashboard.py`: 메인 대시보드 테이블 위젯, 색상 강조
- `widgets/statusbar.py`: 키 힌트 및 알림 메시지 상태바
- `app.py`: Textual 기반 TUI 앱 셸
- `__main__.py`: CLI 진입점 (`--config`, `--source`, `--interval`, `--snapshot`)

**Phase 2 — 소스 확장 & 실시간 폴링**
- `sources/postgres.py`: PostgreSQL 소스 구현
- `sources/redis.py`: Redis 소스 구현 (SCAN 기반 key_count, 네이티브 비동기)
- `scheduler.py`: `PollScheduler` — 소스별 독립 asyncio.Task, exponential backoff
- `alerts.py`: `AlertEvaluator` — 상태 전이 기반 이벤트, CRITICAL 시 WARNING 억제
- 헤더 시계 1초 자동 갱신

**Phase 3 — 고급 UX**
- `exporter.py`: JSON / CSV / 텍스트 스냅샷 내보내기
- `widgets/sparkline.py`: ASCII 스파크라인 패널 (▁▂▃▄▅▆▇█, deque 60샘플)
- `widgets/detail.py`: 상세 뷰 Screen (페이지네이션, 셀 말줄임)
- 필터 모드 (`/` 키, fnmatch 와일드카드)
- 정렬 순환 (`s` 키: 기본→이름↑→크기↓)
- `Enter`로 상세 뷰 진입

**Phase 4 — 품질 & 문서화**
- 단위 테스트: `test_config`, `test_alerts`, `test_exporter`, `test_sparkline`
- 통합 테스트: `test_sqlite_source`, `test_scheduler`
- `README.md`, `CHANGELOG.md`, `config.yaml.example`
