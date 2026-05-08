from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

from .sources.base import MetricSnapshot


class Exporter:
    def __init__(self, snapshot_dir: str) -> None:
        self._dir = Path(snapshot_dir)

    def export(
        self,
        snapshots: list[MetricSnapshot],
        fmt: str = "json",
        output: str | None = None,
    ) -> Path:
        content = self._render(snapshots, fmt)
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._dir.mkdir(parents=True, exist_ok=True)
            ext = {"json": "json", "csv": "csv", "text": "txt"}.get(fmt, fmt)
            path = self._dir / f"snapshot_{ts}.{ext}"
        path.write_text(content, encoding="utf-8")
        return path

    def _render(self, snapshots: list[MetricSnapshot], fmt: str) -> str:
        if fmt == "json":
            return self._to_json(snapshots)
        if fmt == "csv":
            return self._to_csv(snapshots)
        return self._to_text(snapshots)

    @staticmethod
    def _to_json(snapshots: list[MetricSnapshot]) -> str:
        data = [
            {
                "source": s.source_name,
                "target": s.target,
                "status": s.status.value,
                "collected_at": s.collected_at.isoformat(),
                "metrics": s.metrics,
                "error": s.error_msg,
            }
            for s in snapshots
        ]
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def _to_csv(snapshots: list[MetricSnapshot]) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["source", "target", "status", "row_count", "size_mb", "collected_at"])
        for s in snapshots:
            w.writerow([
                s.source_name,
                s.target,
                s.status.value,
                s.metrics.get("row_count", s.metrics.get("key_count", "")),
                s.metrics.get("size_mb", s.metrics.get("memory_usage_mb", "")),
                s.collected_at.isoformat(),
            ])
        return buf.getvalue()

    @staticmethod
    def _to_text(snapshots: list[MetricSnapshot]) -> str:
        hdr = (
            f"{'Source':<16} {'Target':<20} {'Row Count':>12}"
            f" {'Size':>10} {'Status':<12} {'Collected At'}"
        )
        sep = "─" * 86
        lines = [hdr, sep]
        for s in snapshots:
            rc = s.metrics.get("row_count", s.metrics.get("key_count", "—"))
            sz = s.metrics.get("size_mb", s.metrics.get("memory_usage_mb", "—"))
            lines.append(
                f"{s.source_name:<16} {s.target:<20}"
                f" {str(rc):>12} {str(sz):>10} {s.status.value:<12}"
                f" {s.collected_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        return "\n".join(lines)
