from __future__ import annotations

from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from .config import AppConfig
from .sources import create_source
from .sources.base import DataSource, MetricSnapshot
from .widgets.dashboard import DashboardWidget
from .widgets.statusbar import StatusBar

_VERSION = "0.1.0"


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

    # ── 레이아웃 ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header")
        yield DashboardWidget()
        yield StatusBar()

    # ── 생명주기 ──────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        self.query_one(StatusBar).update_status("데이터 로딩 중...", timeout=60)
        await self._do_refresh()

    # ── 액션 ─────────────────────────────────────────────────────────────

    async def action_refresh(self) -> None:
        self.query_one(StatusBar).update_status("갱신 중...", timeout=30)
        await self._do_refresh()

    def action_increase_interval(self) -> None:
        self._config.refresh_interval += 1
        self._update_header()
        self.query_one(StatusBar).update_status(
            f"갱신 주기 변경: {self._config.refresh_interval}s"
        )

    def action_decrease_interval(self) -> None:
        if self._config.refresh_interval > 1:
            self._config.refresh_interval -= 1
            self._update_header()
            self.query_one(StatusBar).update_status(
                f"갱신 주기 변경: {self._config.refresh_interval}s"
            )

    def action_show_help(self) -> None:
        self.query_one(StatusBar).update_status(
            "키 도움말: [b]q[/b]종료  [b]r[/b]갱신  [b]+/-[/b]주기  "
            "[b]↑↓[/b]이동  [b]Enter[/b]상세  [b]f[/b]필터  "
            "[b]g[/b]그래프  [b]e[/b]내보내기",
            timeout=15,
        )

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────

    async def _do_refresh(self) -> None:
        snapshots: list[MetricSnapshot] = []
        errors: list[str] = []

        for source in self._sources:
            try:
                await source.connect()
                result = await source.fetch_metrics()
                snapshots.extend(result)
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")
            finally:
                await source.disconnect()

        self._update_header()
        self.query_one(DashboardWidget).update_snapshots(snapshots, self._config)

        if errors:
            self.query_one(StatusBar).update_status(
                f"연결 오류 ({len(errors)}건): {errors[0]}"
            )
        else:
            self.query_one(StatusBar).update_status(None)

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
