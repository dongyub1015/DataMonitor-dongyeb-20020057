# DataMonitor

콘솔에서 실행하는 Python TUI 도구 — DB·캐시 등 저장 데이터 상태를 실시간으로 조회·모니터링한다.

## 설치

```bash
pip install -e .           # 개발 모드
pip install -e ".[dev]"    # 테스트·린트 도구 포함
```

## 빠른 시작

```bash
# 설정 파일 복사 후 편집
cp config.yaml.example config.yaml

# 실행
python -m datamonitor

# 설정 파일 명시
python -m datamonitor --config /path/to/config.yaml

# 특정 소스만 표시
python -m datamonitor --source MySQL-Prod

# 갱신 주기 오버라이드 (초)
python -m datamonitor --interval 2

# CI/CD용 비대화형 스냅샷
python -m datamonitor --snapshot --format json --output report.json
```

## 키 바인딩

| 키 | 동작 |
|---|---|
| `q` / `Ctrl+C` | 종료 |
| `r` | 즉시 수동 갱신 |
| `+` / `-` | 갱신 주기 증감 (1s 단위) |
| `↑` / `↓` | 행 이동 |
| `Enter` | 상세 뷰 진입 |
| `Esc` | 이전 화면 복귀 |
| `/` 또는 `f` | 필터 입력 모드 |
| `s` | 정렬 기준 순환 (기본→이름↑→크기↓) |
| `g` | 스파크라인 패널 토글 |
| `e` | 현재 상태 JSON 스냅샷 저장 |
| `?` | 키 도움말 표시 |

## 지원 데이터 소스

| 유형 | `type` 값 | 드라이버 |
|---|---|---|
| MySQL / MariaDB | `mysql` | pymysql + SQLAlchemy |
| PostgreSQL | `postgres` | psycopg2 + SQLAlchemy |
| SQLite | `sqlite` | 내장 sqlite3 |
| Redis | `redis` | redis[hiredis] |

## 설정

```yaml
refresh_interval: 5          # 갱신 주기 (초)
max_rows_preview: 20         # 상세 뷰 행 수
snapshot_dir: "./snapshots"  # 내보내기 저장 디렉터리

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
        metrics: [row_count, size_mb]

alerts:
  - source: MySQL-Prod
    target: orders
    metric: row_count
    condition: ">= 50000"
    level: critical
```

전체 옵션은 `config.yaml.example` 참조.

## 보안

- DB 비밀번호는 반드시 `${ENV_VAR}` 형식으로 참조 — 평문 저장 금지
- 모니터링 계정은 `SELECT`, `SHOW` 읽기 전용 권한만 부여
- 설정 파일 권한: `chmod 600 config.yaml` 권고

```sql
-- MySQL 읽기 전용 계정 생성 예시
CREATE USER 'monitor_user'@'localhost' IDENTIFIED BY '...';
GRANT SELECT, SHOW DATABASES ON *.* TO 'monitor_user'@'localhost';
```

## 개발

```bash
pytest                                          # 전체 테스트
pytest tests/unit/                              # 단위 테스트
pytest tests/unit/test_alerts.py -v            # 특정 파일
pytest --cov=datamonitor --cov-report=term-missing   # 커버리지
ruff check datamonitor/                         # 린트
mypy datamonitor/                               # 타입 검사
```

## 요구사항

- Python 3.10+
- 터미널 크기: 최소 80×24
- 호환 터미널: Windows Terminal, iTerm2, Linux xterm
