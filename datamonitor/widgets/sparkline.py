from __future__ import annotations

from collections import deque

from rich.text import Text
from textual.widget import Widget
from textual.app import RenderResult

_BLOCKS = "▁▂▃▄▅▆▇█"


def _render_sparkline(samples: list[float | int], width: int) -> str:
    if not samples or width < 1:
        return " " * max(width, 0)
    display = samples[-width:]
    min_v = min(display)
    max_v = max(display)
    span = max_v - min_v or 1
    return "".join(_BLOCKS[min(int((v - min_v) / span * 7), 7)] for v in display)


class SparklinePanel(Widget):
    """선택된 지표의 실시간 추이를 ASCII 스파크라인으로 표시하는 패널."""

    DEFAULT_CSS = """
    SparklinePanel {
        height: 3;
        border-top: solid $primary;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._label: str = "—"
        self._samples: deque[float | int] = deque(maxlen=60)
        self._latest: float | int | None = None
        self._prev: float | int | None = None

    def push_sample(self, label: str, value: float | int) -> None:
        self._prev = self._latest
        self._latest = value
        self._label = label
        self._samples.append(value)
        self.refresh()

    def render(self) -> RenderResult:
        width = max(self.size.width - 4, 0)
        spark = _render_sparkline(list(self._samples), width)

        delta_str = ""
        if self._prev is not None and self._latest is not None:
            delta = self._latest - self._prev
            sign = "+" if delta >= 0 else ""
            delta_str = f"  ({sign}{delta:,})"

        latest_str = f"{self._latest:,}" if self._latest is not None else "—"

        t = Text()
        t.append(f"{self._label}\n", style="bold")
        t.append(spark, style="green")
        t.append(f"  {latest_str}{delta_str}")
        return t
