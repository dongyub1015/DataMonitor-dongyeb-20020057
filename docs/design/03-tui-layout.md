# 설계: TUI 레이아웃 및 위젯

**담당 Phase**: Phase 1–3  
**최종 수정**: 2026-05-08

---

## 1. 화면 구조 (Textual Layout)

```
┌─────────────────────────────────────────────────────────────────┐
│  HeaderBar                                               [항상 표시] │
│  DataMonitor v1.0    2026-05-08 14:32:05    Refresh: 5s  [3 sources] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  DashboardWidget                                    [기본 화면]  │
│  ┌──────────┬──────────────┬───────────┬────────┬─────────────┐  │
│  │ Source   │ Table / Key  │ Row Count │ Size   │ Last Updated│  │
│  ├──────────┼──────────────┼───────────┼────────┼─────────────┤  │
│  │ MySQL    │ orders       │    12,847 │  24MB  │ 0s ago      │  │
│  │▶MySQL    │ users        │   430,012 │ 512MB  │ 0s ago      │ ← 선택 행
│  │ Redis    │ session:*    │     3,201 │   8MB  │ 0s ago      │  │
│  │[!]PG     │ audit_log    │ 9,999,999 │  98%   │ 12s ago     │ ← 경고
│  └──────────┴──────────────┴───────────┴────────┴─────────────┘  │
│                                                                  │
│  SparklinePanel (g 키 토글)                        [옵션 패널]  │
│  users row_count (60s) ▁▂▃▄▅▆▇█▇▆▅  430,012 (+1,203)           │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  FilterBar (/ 키 활성화)                           [조건부 표시] │
│  Filter: orders_                                                  │
├─────────────────────────────────────────────────────────────────┤
│  StatusBar                                               [항상 표시] │
│  [q]Quit [r]Refresh [/]Filter [s]Sort [g]Graph [e]Export [?]Help│
└─────────────────────────────────────────────────────────────────┘
```

### 상세 뷰 진입 시

```
┌─────────────────────────────────────────────────────────────────┐
│  HeaderBar                                                       │
├─────────────────────────────────────────────────────────────────┤
│  DetailWidget                               [Enter로 진입]       │
│  MySQL-Prod › users      Page 1 / 3                              │
│  ┌────┬──────────────┬───────────────────────┬────────────────┐  │
│  │ id │ email        │ created_at            │ status         │  │
│  ├────┼──────────────┼───────────────────────┼────────────────┤  │
│  │  1 │ alice@ex.com │ 2026-05-08 12:00:00   │ active         │  │
│  │  2 │ bob@ex.co... │ 2026-05-07 09:30:12   │ inactive       │  │
│  └────┴──────────────┴───────────────────────┴────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  StatusBar                                                       │
│  [Esc]Back [PgUp]Prev [PgDn]Next [e]Export                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Textual 위젯 계층

```
DataMonitorApp (App)
├── HeaderBar (Static)                 # 시각, 갱신 주기, 소스 수
├── ContentSwitcher                    # 뷰 전환 컨테이너
│   ├── DashboardScreen (Screen)
│   │   ├── DashboardWidget (DataTable)
│   │   └── SparklinePanel (Widget, 토글)
│   │       └── SparklineWidget (Widget) × N
│   └── DetailScreen (Screen)
│       └── DetailWidget (DataTable)
├── FilterBar (Input, 조건부)          # / 키로 표시
└── StatusBar (Static)                 # 키 힌트 + 알림 메시지
```

---

## 3. 키 바인딩 상태머신

```
                          ┌─────────────────┐
                          │   DASHBOARD     │ ← 기본 화면
                          └──────┬──────────┘
         ┌─────────────────┬─────┘──────────┬───────────────┐
         │ Enter           │ /              │ g             │ e
         ▼                 ▼                ▼               ▼
    ┌──────────┐     ┌──────────┐    ┌──────────┐   ┌───────────┐
    │  DETAIL  │     │  FILTER  │    │SPARKLINE │   │  EXPORT   │
    │  (screen)│     │  (input) │    │  (panel) │   │  (modal)  │
    └──────┬───┘     └──────┬───┘    └──────┬───┘   └─────┬─────┘
           │ Esc            │ Esc           │ g           │ Esc/Enter
           └────────────────┴───────────────┴─────────────┘
                                    │
                             DASHBOARD 복귀
```

### 전체 키 바인딩 정의

| 키 | 컨텍스트 | 동작 | 구현 위치 |
|---|---|---|---|
| `q` | 전체 | 종료 | `App.action_quit()` |
| `Ctrl+C` | 전체 | 종료 | Textual 기본 처리 |
| `?` | 전체 | 도움말 모달 | `App.action_help()` |
| `r` | Dashboard | 즉시 갱신 | `App.action_refresh()` |
| `+` | Dashboard | 갱신 주기 +1s | `App.action_increase_interval()` |
| `-` | Dashboard | 갱신 주기 -1s (min 1s) | `App.action_decrease_interval()` |
| `↑` `↓` | Dashboard | 행 이동 | `DashboardWidget` 기본 처리 |
| `Enter` | Dashboard | 상세 뷰 진입 | `App.action_detail()` |
| `f` | Dashboard | 필터바 열기 | `App.action_filter()` |
| `/` | Dashboard | 필터바 열기 | `App.action_filter()` |
| `s` | Dashboard | 정렬 기준 순환 | `App.action_sort()` |
| `g` | Dashboard | 스파크라인 패널 토글 | `App.action_toggle_sparkline()` |
| `e` | Dashboard, Detail | 내보내기 모달 | `App.action_export()` |
| `Esc` | Filter, Detail | 이전 화면 복귀 | 각 화면의 `on_key()` |
| `PgUp` `PgDn` | Detail | 페이지 이동 | `DetailWidget.action_page()` |

---

## 4. DashboardWidget

`textual.widgets.DataTable` 서브클래스.

### 4.1 컬럼 정의

| 컬럼 | 너비 | 정렬 | 설명 |
|---|---|---|---|
| Status | 3 | center | 정상=공백, 경고=`[!]`, 에러=`[✗]` |
| Source | 12 | left | 소스 이름 |
| Target | 16 | left | 테이블/키 패턴 |
| Row Count | 11 | right | 천 단위 구분 |
| Size | 8 | right | `24.3MB` 형식 |
| Last Updated | 13 | right | `0s ago`, `5s ago` |

### 4.2 색상 강조 규칙

```python
# Textual Rich markup 사용
LEVEL_STYLE = {
    AlertLevel.OK:       "",                      # 기본 색상
    AlertLevel.WARNING:  "bold yellow",
    AlertLevel.CRITICAL: "bold red on dark_red",
    SourceStatus.ERROR:  "dim",
    SourceStatus.TIMEOUT:"yellow",
}
```

### 4.3 갱신 전략

- Textual `reactive` 변수 `snapshots`가 변경되면 `watch_snapshots()` 호출
- `DataTable.update_cell()` 로 변경된 셀만 업데이트 (전체 테이블 재렌더링 방지)
- "Last Updated" 컬럼은 Textual `Timer(interval=1)` 로 독립 갱신

---

## 5. SparklineWidget

### 5.1 렌더링 알고리즘

```python
BLOCKS = "▁▂▃▄▅▆▇█"

def render_sparkline(samples: deque[int], width: int) -> str:
    if not samples:
        return " " * width
    display = list(samples)[-width:]          # 화면 너비만큼 자름
    min_v, max_v = min(display), max(display)
    span = max_v - min_v or 1
    chars = [BLOCKS[int((v - min_v) / span * 7)] for v in display]
    return "".join(chars)
```

### 5.2 패널 레이아웃

```
┌───────────────────────────────────────────────────────────┐
│ [MySQL-Prod] users › row_count   (last 60 samples, 5s ea) │
│ ▁▂▃▄▅▆▇█▇▆▅▅▆▇▇▆▅▅▄▄▄▅▆▇█  430,012  (+1,203 / +0.28%)   │
└───────────────────────────────────────────────────────────┘
```

- 선택된 행의 메트릭에 자동 포커스
- 여러 행 선택 가능 (멀티 스파크라인, 수직 스택)

---

## 6. FilterBar

```
Filter: orders_     (← 실시간 입력)
```

- Textual `Input` 위젯을 `dock=bottom` 배치
- `on_input_changed`: 입력마다 `DashboardWidget.apply_filter(pattern)` 호출
- 필터 적용: 소스명·테이블명을 `fnmatch` 패턴 매칭
- 필터 상태에서 `↑↓Enter` 동작은 대시보드와 동일

---

## 7. StatusBar

```
[정상] [q]Quit [r]Refresh [/]Filter [s]Sort:Name↑ [g]Graph [e]Export [?]Help
[알림] ⚠ MySQL-Prod › audit_log: row_count=9,999,999 (critical)  5s ago
```

- 알림 메시지는 10초 후 자동으로 키 힌트 표시로 복귀
- 정렬 모드는 `[s]Sort:Name↑` 형식으로 현재 상태 표시

---

## 8. 터미널 크기 처리

```python
# App.on_resize() 핸들러
def on_resize(self, event: Resize) -> None:
    if event.size.width < 80 or event.size.height < 24:
        self.push_screen(SizeWarningScreen())
    else:
        self.pop_screen()  # 경고 화면 제거 (있을 경우)
```

- 80×24 미만: 중앙에 경고 오버레이 표시 (앱 종료 없음)
- 크기 복구 시 자동으로 정상 화면으로 복귀
