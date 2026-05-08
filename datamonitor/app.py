from __future__ import annotations

import sys
from collections import deque
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from .alerts import AlertEvaluator, AlertEvent
from .config import AlertLevel, AppConfig
from .scheduler import PollScheduler
from .sources import create_source
from .sources.base import DataSource, MetricSnapshot
from .widgets.dashboard import DashboardWidget
from .widgets.statusbar import StatusBar

_VERSION = "0.1.0"


class _MetricsUpdated(Message):
    """폴링 스케줄러가 새 메트릭을 수집했을 때 발행하는 내부 메시지."""

    def __init__(self, snapshots: list[MetricSnapshot]) -> None:
        super().__init__()
        self.snapshots = snapshots


class DataMonitorApp(App):
    """DataMonitor TUI 애플리케이션."""

    DEFAULT_CSS = """
    Screen {
        background: $background;
    }
    #header {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    DashboardWidget {
        height: 1fr;
        margin: 0;
    }
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
        Binding("question_mark", "show_help", "도움말", show=False),
    ]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._sources: list[DataSource] = [create_source(s) for s in config.sources]
        self._snapshots: dict[str, MetricSnapshot] = {}
        self._alert_history: deque[AlertEvent] = deque(maxlen=100)
        self._alert_evaluator = AlertEvaluator(config.alerts)
        self._scheduler = PollScheduler(
            sources=self._sources,
            interval=config.refresh_interval,
            on_update=self._enqueue_metrics,
        )

    # ── 레이아웃 ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header")
        yield DashboardWidget()
        yield StatusBar()

    # ── 생명주기 ──────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        self.query_one(StatusBar).update_status("데이터 로딩 중...", timeout=60)
        # 초회 즉시 조회 후 폴링 루프 시작
        await self._scheduler.trigger_once()
        await self._scheduler.start()
        # 헤더 시각 1초 갱신
        self.set_interval(1.0, self._update_header_clock)

    async def on_unmount(self) -> None:
        await self._scheduler.stop()

    # ── 메트릭 수신 (스케줄러 콜백 → Textual 메시지) ─────────────────────

    def _enqueue_metrics(self, snapshots: list[MetricSnapshot]) -> None:
        """asyncio Task에서 호출 — post_message로 메인 루프에 안전하게 전달."""
        self.post_message(_MetricsUpdated(snapshots))

    def on__metrics_updated(self, event: _MetricsUpdated) -> None:
        for snap in event.snapshots:
            self._snapshots[f"{snap.source_name}:{snap.target}"] = snap
            alert_events = self._alert_evaluator.evaluate(snap)
            for ae in alert_events:
                self._alert_history.append(ae)
                self._handle_alert(ae)

        self._update_header()
        self.query_one(DashboardWidget).update_snapshots(
            list(self._snapshots.values()), self._config
        )

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
            f"갱신 주기 변경: {self._config.refresh_interval}s"
        )

    def action_decrease_interval(self) -> None:
        if self._config.refresh_interval > 1:
            self._config.refresh_interval -= 1
            self._scheduler.set_interval(self._config.refresh_interval)
            self._update_header()
            self.query_one(StatusBar).update_status(
                f"갱신 주기 변경: {self._config.refresh_interval}s"
            )

    def action_show_help(self) -> None:
        self.query_one(StatusBar).update_status(
            "[b]q[/b]종료  [b]r[/b]갱신  [b]+/-[/b]주기  "
            "[b]↑↓[/b]이동  [b]Enter[/b]상세  [b]f[/b]필터  "
            "[b]g[/b]그래프  [b]e[/b]내보내기",
            timeout=15,
        )

    # ── 헤더 갱신 ─────────────────────────────────────────────────────────

    def _header_text(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n = len(self._sources)
        interval = self._config.refresh_interval
        return (
            f" DataMonitor v{_VERSION}"
            f"    {now}"
            f"    Refresh: {interval}s"
            f"    Sources: {n}"
        )

    def _update_header(self) -> None:
        self.query_one("#header", Static).update(self._header_text())

    def _update_header_clock(self) -> None:
        self._update_header()
