from __future__ import annotations

import fnmatch
import sys
from collections import deque
from datetime import datetime
from enum import Enum, auto

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input, Static

from .alerts import AlertEvaluator, AlertEvent
from .config import AlertLevel, AppConfig
from .exporter import Exporter
from .scheduler import PollScheduler
from .sources import create_source
from .sources.base import DataSource, MetricSnapshot, RowPreview
from .widgets.dashboard import DashboardWidget
from .widgets.detail import DetailScreen
from .widgets.sparkline import SparklinePanel
from .widgets.statusbar import StatusBar

_VERSION = "0.1.0"


class SortMode(Enum):
    DEFAULT = auto()
    NAME_ASC = auto()
    SIZE_DESC = auto()

    def next(self) -> "SortMode":
        members = list(SortMode)
        return members[(members.index(self) + 1) % len(members)]

    def label(self) -> str:
        return {
            SortMode.DEFAULT: "기본",
            SortMode.NAME_ASC: "이름↑",
            SortMode.SIZE_DESC: "크기↓",
        }[self]


class _MetricsUpdated(Message):
    def __init__(self, snapshots: list[MetricSnapshot]) -> None:
        super().__init__()
        self.snapshots = snapshots


class DataMonitorApp(App):
    """DataMonitor TUI 애플리케이션."""

    DEFAULT_CSS = """
    Screen { background: $background; }
    #header {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    DashboardWidget { height: 1fr; margin: 0; }
    SparklinePanel { display: none; }
    SparklinePanel.visible { display: block; }
    #filter-input {
        height: 1;
        border: none;
        background: $surface;
        display: none;
    }
    #filter-input.visible { display: block; }
    StatusBar {
        height: 1;
        dock: bottom;
        background: $primary-darken-2;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "종료", show=False),
        Binding("r", "refresh", "갱신", show=False),
        Binding("plus", "increase_interval", "+주기", show=False),
        Binding("minus", "decrease_interval", "-주기", show=False),
        Binding("f", "toggle_filter", "필터", show=False),
        Binding("slash", "toggle_filter", "필터", show=False),
        Binding("s", "cycle_sort", "정렬", show=False),
        Binding("g", "toggle_sparkline", "그래프", show=False),
        Binding("e", "export_snapshot", "내보내기", show=False),
        Binding("question_mark", "show_help", "도움말", show=False),
    ]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._sources: list[DataSource] = [create_source(s) for s in config.sources]
        self._snapshots: dict[str, MetricSnapshot] = {}
        self._history: dict[str, deque[MetricSnapshot]] = {}
        self._alert_history: deque[AlertEvent] = deque(maxlen=100)
        self._alert_evaluator = AlertEvaluator(config.alerts)
        self._scheduler = PollScheduler(
            sources=self._sources,
            interval=config.refresh_interval,
            on_update=self._enqueue_metrics,
        )
        self._exporter = Exporter(config.snapshot_dir)
        self._sort_mode = SortMode.DEFAULT
        self._filter_text = ""
        self._sparkline_visible = False

    # ── 레이아웃 ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header")
        yield DashboardWidget()
        yield SparklinePanel(id="sparkline")
        yield Input(placeholder="필터: 소스명 또는 테이블명 (와일드카드 * 지원)", id="filter-input")
        yield StatusBar()

    # ── 생명주기 ──────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        self.query_one(StatusBar).update_status("데이터 로딩 중...", timeout=60)
        await self._scheduler.trigger_once()
        await self._scheduler.start()
        self.set_interval(1.0, self._update_header_clock)

    async def on_unmount(self) -> None:
        await self._scheduler.stop()

    # ── 메트릭 수신 ───────────────────────────────────────────────────────

    def _enqueue_metrics(self, snapshots: list[MetricSnapshot]) -> None:
        self.post_message(_MetricsUpdated(snapshots))

    def on__metrics_updated(self, event: _MetricsUpdated) -> None:
        for snap in event.snapshots:
            key = f"{snap.source_name}:{snap.target}"
            self._snapshots[key] = snap
            if key not in self._history:
                self._history[key] = deque(maxlen=60)
            self._history[key].append(snap)

            for ae in self._alert_evaluator.evaluate(snap):
                self._alert_history.append(ae)
                self._handle_alert(ae)

        self._update_header()
        self._refresh_dashboard()
        self._refresh_sparkline()

    # ── 알림 처리 ─────────────────────────────────────────────────────────

    def _handle_alert(self, event: AlertEvent) -> None:
        if event.is_recovery:
            self.query_one(StatusBar).update_status(event.message, timeout=5)
        elif event.level == AlertLevel.CRITICAL:
            sys.stdout.write("\a")
            sys.stdout.flush()
            self.query_one(StatusBar).update_status(event.message, timeout=30)
        else:
            self.query_one(StatusBar).update_status(event.message, timeout=15)

    # ── 액션 ─────────────────────────────────────────────────────────────

    async def action_refresh(self) -> None:
        self.query_one(StatusBar).update_status("갱신 중...", timeout=30)
        await self._scheduler.trigger_once()

    def action_increase_interval(self) -> None:
        self._config.refresh_interval += 1
        self._scheduler.set_interval(self._config.refresh_interval)
        self._update_header()
        self.query_one(StatusBar).update_status(
            f"갱신 주기: {self._config.refresh_interval}s"
        )

    def action_decrease_interval(self) -> None:
        if self._config.refresh_interval > 1:
            self._config.refresh_interval -= 1
            self._scheduler.set_interval(self._config.refresh_interval)
            self._update_header()
            self.query_one(StatusBar).update_status(
                f"갱신 주기: {self._config.refresh_interval}s"
            )

    def action_cycle_sort(self) -> None:
        self._sort_mode = self._sort_mode.next()
        self._refresh_dashboard()
        self.query_one(StatusBar).update_status(
            f"정렬: {self._sort_mode.label()}"
        )

    def action_toggle_filter(self) -> None:
        inp = self.query_one("#filter-input", Input)
        if "visible" in inp.classes:
            inp.remove_class("visible")
            self._filter_text = ""
            self._refresh_dashboard()
        else:
            inp.add_class("visible")
            inp.focus()

    def action_toggle_sparkline(self) -> None:
        self._sparkline_visible = not self._sparkline_visible
        panel = self.query_one(SparklinePanel)
        if self._sparkline_visible:
            panel.add_class("visible")
            self._refresh_sparkline()
        else:
            panel.remove_class("visible")

    def action_export_snapshot(self) -> None:
        snapshots = list(self._snapshots.values())
        if not snapshots:
            self.query_one(StatusBar).update_status("내보낼 데이터가 없습니다.")
            return
        try:
            path = self._exporter.export(snapshots, fmt="json")
            self.query_one(StatusBar).update_status(f"저장 완료: {path}")
        except Exception as exc:
            self.query_one(StatusBar).update_status(f"내보내기 실패: {exc}")

    def action_show_help(self) -> None:
        self.query_one(StatusBar).update_status(
            "[b]q[/b]종료  [b]r[/b]갱신  [b]+/-[/b]주기  "
            "[b]↑↓[/b]이동  [b]Enter[/b]상세  [b]/[/b]필터  "
            "[b]s[/b]정렬  [b]g[/b]그래프  [b]e[/b]내보내기",
            timeout=15,
        )

    # ── 대시보드 이벤트 ───────────────────────────────────────────────────

    async def on_data_table_row_selected(self, event: DashboardWidget.RowSelected) -> None:
        row_key = str(event.row_key.value) if event.row_key.value else ""
        if not row_key or ":" not in row_key:
            return
        source_name, target = row_key.split(":", 1)
        await self._push_detail(source_name, target)

    # ── 필터 입력 ─────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter_text = event.value
        self._refresh_dashboard()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_toggle_filter()

    # ── 상세 뷰 ──────────────────────────────────────────────────────────

    async def _push_detail(self, source_name: str, target: str) -> None:
        source = next((s for s in self._sources if s.name == source_name), None)
        if source is None:
            return

        max_rows = self._config.max_rows_preview

        async def fetcher(page: int) -> RowPreview:
            await source.connect()
            try:
                return await source.fetch_rows(target, max_rows, page * max_rows)
            finally:
                await source.disconnect()

        await self.push_screen(DetailScreen(source_name, target, fetcher, max_rows))

    # ── 내부 렌더링 헬퍼 ─────────────────────────────────────────────────

    def _refresh_dashboard(self) -> None:
        snapshots = self._apply_filter_sort(list(self._snapshots.values()))
        self.query_one(DashboardWidget).update_snapshots(snapshots, self._config)

    def _refresh_sparkline(self) -> None:
        if not self._sparkline_visible or not self._snapshots:
            return
        try:
            dashboard = self.query_one(DashboardWidget)
            cursor_row = dashboard.cursor_row
            rows = list(self._snapshots.values())
            if 0 <= cursor_row < len(rows):
                snap = rows[cursor_row]
                value = snap.row_count
                if value is not None:
                    label = f"{snap.source_name} › {snap.target} › row_count"
                    self.query_one(SparklinePanel).push_sample(label, value)
        except Exception:
            pass

    def _apply_filter_sort(self, snapshots: list[MetricSnapshot]) -> list[MetricSnapshot]:
        if self._filter_text:
            pat = (
                f"*{self._filter_text}*"
                if "*" not in self._filter_text
                else self._filter_text
            )
            snapshots = [
                s for s in snapshots
                if fnmatch.fnmatch(s.source_name.lower(), pat.lower())
                or fnmatch.fnmatch(s.target.lower(), pat.lower())
            ]

        if self._sort_mode == SortMode.NAME_ASC:
            snapshots = sorted(snapshots, key=lambda s: (s.source_name, s.target))
        elif self._sort_mode == SortMode.SIZE_DESC:
            snapshots = sorted(snapshots, key=lambda s: s.size_mb or 0.0, reverse=True)

        return snapshots

    # ── 헤더 ─────────────────────────────────────────────────────────────

    def _header_text(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n = len(self._sources)
        interval = self._config.refresh_interval
        sort_info = f"  Sort:{self._sort_mode.label()}" if self._sort_mode != SortMode.DEFAULT else ""
        return (
            f" DataMonitor v{_VERSION}"
            f"    {now}"
            f"    Refresh: {interval}s"
            f"    Sources: {n}"
            f"{sort_info}"
        )

    def _update_header(self) -> None:
        self.query_one("#header", Static).update(self._header_text())

    def _update_header_clock(self) -> None:
        self._update_header()
