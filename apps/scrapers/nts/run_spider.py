"""Run the NTS spider once and write its items to a JSON-lines file.

Scrapy's Twisted reactor cannot be restarted inside a long-lived process (such as a
Celery worker), so the pipeline always runs the spider in a fresh subprocess via
`crawl_nts()`. This module is also runnable directly:

    uv run python -m nts.run_spider --output data/runs/listings.jsonl
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import config


def _run(output: Path, include_closed_details: bool = True) -> dict:
    from scrapy.crawler import CrawlerProcess

    from nts.spider import NtsSpider

    process = CrawlerProcess(
        settings={
            "FEEDS": {str(output): {"format": "jsonlines", "encoding": "utf8", "overwrite": True}},
        }
    )
    crawler = process.create_crawler(NtsSpider)
    process.crawl(crawler, include_closed_details=str(include_closed_details))
    process.start()
    return crawler.stats.get_stats()


def crawl_nts(output: Path, include_closed_details: bool = True, timeout: int = 900) -> tuple[list[dict], dict]:
    """Run the spider in a subprocess; return (items, stats)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "nts.run_spider", "--output", str(output)]
    if not include_closed_details:
        cmd.append("--open-only")
    proc = subprocess.run(cmd, cwd=config.BASE_DIR, capture_output=True, text=True, timeout=timeout)

    stats: dict = {}
    for line in proc.stdout.splitlines():
        if line.startswith("NTS_STATS="):
            stats = json.loads(line.removeprefix("NTS_STATS="))
    if proc.returncode != 0:
        raise RuntimeError(f"NTS spider exited with {proc.returncode}:\n{proc.stderr[-3000:]}")

    items = []
    if output.exists():
        with output.open(encoding="utf8") as f:
            items = [json.loads(line) for line in f if line.strip()]
    return items, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--open-only", action="store_true", help="skip detail pages of closed listings")
    args = parser.parse_args()

    stats = _run(args.output, not args.open_only)
    print("NTS_STATS=" + json.dumps(stats, default=str))


if __name__ == "__main__":
    main()
