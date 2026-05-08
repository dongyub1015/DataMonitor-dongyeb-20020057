from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Static

from ..sources.base import RowPreview

Fetcher = Callable[[int], Coroutine[Any, Any, RowPreview]]

_MAX_CELL_WIDTH = 30


class DetailScreen(Screen):
    """선택된 테이블/키의 row 미리보기 화면."""

    DEFAULT_CSS = """
    DetailScreen { background: $background; }
    #detail-header {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    #detail-table { height: 1fr; }
    #detail-status {
        height: 1;
        background: $primary-darken-2;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "돌아가기", show=False),
        Binding("q", "go_back", "돌아가기", show=False),
        Binding("page_up", "prev_page", "이전 페이지", show=False),
        Binding("page_down", "next_page", "다음 페이지", show=False),
    ]

    def __init__(
        self,
        source_name: str,
        target: str,
        fetcher: Fetcher,
        max_rows: int,
    ) -> None:
        super().__init__()
        self._source_name = source_name
        self._target = target
        self._fetcher = fetcher
        self._max_rows = max_rows
        self._page = 0
        self._total_fetched = 0

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="detail-header")
        yield DataTable(id="detail-table", cursor_type="row")
        yield Static(
            "[b]Esc/q[/b] 돌아가기  [b]PgUp[/b] 이전  [b]PgDn[/b] 다음",
            markup=True,
            id="detail-status",
        )

    async def on_mount(self) -> None:
        await self._load_page(0)

    # ── 액션 ─────────────────────────────────────────────────────────────

    def action_go_back(self) -> None:
        self.app.pop_screen()

    async def action_prev_page(self) -> None:
        if self._page > 0:
            await self._load_page(self._page - 1)

    async def action_next_page(self) -> None:
        if self._total_fetched == self._max_rows:
            await self._load_page(self._page + 1)

    # ── 내부 ─────────────────────────────────────────────────────────────

    async def _load_page(self, page: int) -> None:
        self.query_one("#detail-status", Static).update("로딩 중...")
        try:
            preview = await self._fetcher(page)
        except Exception as exc:
            self.query_one("#detail-status", Static).update(f"오류: {exc}")
            return

        self._page = preview.page
        self._total_fetched = preview.total_fetched
        self._render_preview(preview)
        self.query_one("#detail-header", Static).update(self._header_text())
        self.query_one("#detail-status", Static).update(
            f"[b]Esc/q[/b] 돌아가기  [b]PgUp[/b] 이전  [b]PgDn[/b] 다음"
            f"  ({preview.total_fetched}행)"
        )

    def _render_preview(self, preview: RowPreview) -> None:
        table = self.query_one("#detail-table", DataTable)
        table.clear(columns=True)

        if not preview.columns:
            return

        for col in preview.columns:
            table.add_column(col)

        for row in preview.rows:
            cells = []
            for cell in row:
                val = "NULL" if cell is None else str(cell)
                if len(val) > _MAX_CELL_WIDTH:
                    val = val[: _MAX_CELL_WIDTH - 1] + "…"
                cells.append(val)
            table.add_row(*cells)

    def _header_text(self) -> str:
        return (
            f" {self._source_name} › {self._target}"
            f"    Page {self._page + 1}"
        )
