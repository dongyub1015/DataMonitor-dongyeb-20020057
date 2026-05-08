from __future__ import annotations

from textual.widgets import Static

_DEFAULT_HINTS = (
    "[b]q[/b] 종료  "
    "[b]r[/b] 갱신  "
    "[b]+/-[/b] 주기  "
    "[b]Enter[/b] 상세  "
    "[b]f[/b] 필터  "
    "[b]g[/b] 그래프  "
    "[b]e[/b] 내보내기  "
    "[b]?[/b] 도움말"
)


class StatusBar(Static):
    """하단 상태바 — 키 힌트 및 알림 메시지 표시."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(_DEFAULT_HINTS, markup=True, **kwargs)
        self._alert_timer = None

    def update_status(self, message: str | None, *, timeout: float = 10.0) -> None:
        if self._alert_timer is not None:
            self._alert_timer.stop()
            self._alert_timer = None

        if message is None:
            self.update(_DEFAULT_HINTS)
            return

        self.update(message)
        self._alert_timer = self.set_timer(timeout, self._restore_hints)

    def _restore_hints(self) -> None:
        self.update(_DEFAULT_HINTS)
        self._alert_timer = None
