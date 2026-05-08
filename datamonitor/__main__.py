from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="datamonitor",
        description="콘솔 기반 실시간 데이터 상태 조회 관리자 도구",
    )
    p.add_argument("--config", "-c", metavar="PATH", help="설정 파일 경로 (기본: ./config.yaml)")
    p.add_argument("--source", "-s", metavar="NAME", help="특정 소스만 표시")
    p.add_argument("--interval", "-i", type=int, metavar="SEC", help="갱신 주기 오버라이드 (초)")
    p.add_argument(
        "--snapshot",
        action="store_true",
        help="비대화형 스냅샷 모드 (TUI 없이 한 번만 조회 후 출력)",
    )
    p.add_argument(
        "--format",
        choices=["json", "csv", "text"],
        default="json",
        help="스냅샷 출력 포맷 (기본: json)",
    )
    p.add_argument("--output", "-o", metavar="PATH", help="스냅샷 저장 경로 (미지정 시 stdout)")
    p.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    from .config import load_config

    config = load_config(args.config)

    if args.interval is not None:
        if args.interval < 1:
            parser.error("--interval 은 1 이상이어야 합니다.")
        config.refresh_interval = args.interval

    if args.source:
        names = {s.name for s in config.sources}
        if args.source not in names:
            sys.exit(f"오류: 소스 '{args.source}'를 찾을 수 없습니다.\n  등록된 소스: {', '.join(names)}")
        config.sources = [s for s in config.sources if s.name == args.source]

    if args.snapshot:
        _run_snapshot(config, fmt=args.format, output=args.output)
    else:
        _run_tui(config)


def _run_tui(config: object) -> None:
    from .app import DataMonitorApp

    app = DataMonitorApp(config)  # type: ignore[arg-type]
    app.run()


def _run_snapshot(config: object, fmt: str, output: str | None) -> None:
    import asyncio
    from datetime import datetime

    from .config import AppConfig
    from .sources import create_source
    from .sources.base import MetricSnapshot

    cfg: AppConfig = config  # type: ignore[assignment]
    sources = [create_source(s) for s in cfg.sources]

    async def _collect() -> list[MetricSnapshot]:
        snapshots: list[MetricSnapshot] = []
        for source in sources:
            try:
                await source.connect()
                snapshots.extend(await source.fetch_metrics())
            finally:
                await source.disconnect()
        return snapshots

    snapshots = asyncio.run(_collect())

    if fmt == "json":
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
        content = json.dumps(data, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        lines = ["source,target,status,row_count,size_mb,collected_at"]
        for s in snapshots:
            lines.append(
                f"{s.source_name},{s.target},{s.status.value},"
                f"{s.metrics.get('row_count', '')},"
                f"{s.metrics.get('size_mb', '')},"
                f"{s.collected_at.isoformat()}"
            )
        content = "\n".join(lines)
    else:
        lines = [f"{'Source':<14} {'Target':<18} {'Row Count':>12} {'Size':>9} {'Status':<12}"]
        lines.append("-" * 70)
        for s in snapshots:
            lines.append(
                f"{s.source_name:<14} {s.target:<18}"
                f" {s.metrics.get('row_count', '—'):>12}"
                f" {s.metrics.get('size_mb', '—'):>9}"
                f" {s.status.value:<12}"
            )
        content = "\n".join(lines)

    if output:
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        print(f"저장 완료: {p}")
    else:
        print(content)


if __name__ == "__main__":
    main()
