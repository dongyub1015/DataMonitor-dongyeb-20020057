from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import DataTable

from ..sources.base import MetricSnapshot, SourceStatus

if TYPE_CHECKING:
    from ..config import AppConfig, AlertLevel

_STATUS_COL = "status"
_SOURCE_COL = "source"
_TARGET_COL = "target"
_ROWCOUNT_COL = "row_count"
_SIZE_COL = "size"
_UPDATED_COL = "updated"


def _fmt_row_count(v: int | None) -> str:
    if v is None:
        return "—"
    return f"{v:,}"


def _fmt_size(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1024:
        return f"{v / 1024:.1f}GB"
    return f"{v:.1f}MB"


def _fmt_updated(dt: datetime) -> str:
    delta = int((datetime.now() - dt).total_seconds())
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    return f"{delta // 3600}h ago"


class DashboardWidget(DataTable):
    """메인 대시보드 — 모든 소스의 지표를 테이블로 표시."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_column("", width=3, key=_STATUS_COL)
        self.add_column("Source", width=14, key=_SOURCE_COL)
        self.add_column("Table / Key", width=18, key=_TARGET_COL)
        self.add_column("Row Count", width=12, key=_ROWCOUNT_COL)
        self.add_column("Size", width=9, key=_SIZE_COL)
        self.add_column("Last Updated", width=13, key=_UPDATED_COL)

    def update_snapshots(
        self,
        snapshots: list[MetricSnapshot],
        config: "AppConfig",
    ) -> None:
        self.clear()
        alert_map = self._build_alert_map(config)

        for snap in snapshots:
            level = alert_map.get(f"{snap.source_name}:{snap.target}")
            self.add_row(
                *self._make_row_cells(snap, level),
                key=f"{snap.source_name}:{snap.target}",
            )

    def _make_row_cells(
        self,
        snap: MetricSnapshot,
        alert_level: "AlertLevel | None",
    ) -> tuple[Text, Text, Text, Text, Text, Text]:
        from ..config import AlertLevel

        if snap.status == SourceStatus.ERROR:
            style = "dim red"
            status_text = Text("✗", style="bold red")
        elif snap.status == SourceStatus.TIMEOUT:
            style = "yellow"
            status_text = Text("?", style="bold yellow")
        elif alert_level == AlertLevel.CRITICAL:
            style = "bold red"
            status_text = Text("!", style="bold red")
        elif alert_level == AlertLevel.WARNING:
            style = "bold yellow"
            status_text = Text("!", style="bold yellow")
        else:
            style = ""
            status_text = Text(" ")

        def t(v: str) -> Text:
            return Text(v, style=style)

        if snap.status in (SourceStatus.ERROR, SourceStatus.TIMEOUT):
            row_count_text = t(snap.error_msg or "ERR")
            size_text = t("—")
        else:
            row_count_text = t(_fmt_row_count(snap.row_count))
            size_text = t(_fmt_size(snap.size_mb))

        return (
            status_text,
            t(snap.source_name),
            t(snap.target),
            row_count_text,
            size_text,
            t(_fmt_updated(snap.collected_at)),
        )

    @staticmethod
    def _build_alert_map(config: "AppConfig") -> dict[str, "AlertLevel"]:
        from ..config import AlertLevel

        result: dict[str, AlertLevel] = {}
        for rule in sorted(
            config.alerts,
            key=lambda r: 0 if r.level == AlertLevel.CRITICAL else 1,
        ):
            key = f"{rule.source}:{rule.target}"
            if key not in result:
                result[key] = rule.level
        return result
