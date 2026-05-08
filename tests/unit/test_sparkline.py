from __future__ import annotations

import pytest

from datamonitor.widgets.sparkline import _render_sparkline

_BLOCKS = "▁▂▃▄▅▆▇█"


def test_empty_samples_returns_spaces() -> None:
    result = _render_sparkline([], width=10)
    assert result == " " * 10


def test_zero_width_returns_empty() -> None:
    result = _render_sparkline([1, 2, 3], width=0)
    assert result == ""


def test_single_sample_renders_lowest_block() -> None:
    result = _render_sparkline([100], width=5)
    assert result.replace(" ", "") == _BLOCKS[0] * len(result.strip())


def test_all_equal_values_lowest_block() -> None:
    result = _render_sparkline([42] * 8, width=8)
    assert all(c == _BLOCKS[0] for c in result)


def test_ascending_values_ascending_blocks() -> None:
    samples = list(range(8))
    result = _render_sparkline(samples, width=8)
    # 첫 번째 문자 < 마지막 문자 (블록 높이 기준)
    assert result[0] <= result[-1]


def test_width_limits_output_length() -> None:
    samples = list(range(100))
    result = _render_sparkline(samples, width=20)
    assert len(result) == 20


def test_more_samples_than_width_uses_latest() -> None:
    # 80개 샘플, width=10 → 최신 10개만 표시
    # 최신 10개: 100, 90, 80 … 10 (내림차순) → 앞이 높고 뒤가 낮아야 함
    samples = [0] * 70 + [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]
    result = _render_sparkline(samples, width=10)
    assert result[0] > result[-1], "최신 샘플(높은값)이 앞에 와야 합니다"


def test_output_only_block_characters() -> None:
    samples = [10, 20, 30, 40, 50]
    result = _render_sparkline(samples, width=5)
    assert all(c in _BLOCKS for c in result)


@pytest.mark.parametrize("width", [1, 5, 20, 60])
def test_output_length_matches_width(width: int) -> None:
    samples = [i * 10 for i in range(80)]
    result = _render_sparkline(samples, width=width)
    assert len(result) == width
