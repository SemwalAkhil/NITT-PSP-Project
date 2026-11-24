"""
Herbal Almanac — Image Cache Warmer.

Pre-fetches and caches plant photographs from the CCRAS DRAVYA portal into the
local disk cache directory to enable offline browsing and fast image loading.

Usage:
    python scripts/warm_image_cache.py [--database path/to/database.db] [--delay 0.3]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

from herbal_almanac.database_operator import default_database_path
from herbal_almanac.herb_glossary import is_ccras_source


def detect_image_type(data: bytes) -> str | None:
    """Detect image MIME type from initial bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def get_cache_dir(db_path: Path) -> Path:
    env_dir = os.environ.get("HERBAL_ALMANAC_CACHE_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = db_path.parent / "herbal_almanac_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def warm_cache(
    database_path: Path | str | None = None,
    delay: float = 0.3,
    max_herbs: int | None = None,
) -> dict[str, int]:
    """Warms the image cache for all herbs with a valid source_record_id."""
    db_path = Path(database_path) if database_path else Path(default_database_path())
    if not db_path.is_file():
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        return {"total": 0, "cached": 0, "skipped": 0, "failed": 0}

    cache_dir = get_cache_dir(db_path)
    print(f"Database: {db_path}")
    print(f"Cache directory: {cache_dir}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = (
            "SELECT id, source_record_id, source, english_name, original_name "
            "FROM herbs WHERE source_record_id IS NOT NULL ORDER BY id"
        )
        if max_herbs:
            query += f" LIMIT {int(max_herbs)}"
        rows = [r for r in conn.execute(query).fetchall() if is_ccras_source(r["source"])]
    finally:
        conn.close()

    total = len(rows)
    print(f"Found {total} herbs with CCRAS source record IDs.\n")

    stats = {"total": total, "cached": 0, "skipped": 0, "failed": 0}

    for i, row in enumerate(rows, start=1):
        herb_id = row["id"]
        source_rid = row["source_record_id"]
        name = row["original_name"] or row["english_name"] or f"Herb {herb_id}"
        cache_file = cache_dir / f"{herb_id}.jpg"

        if cache_file.is_file() and cache_file.stat().st_size > 0:
            print(f"[{i}/{total}] SKIP (cached): #{herb_id} {name}")
            stats["skipped"] += 1
            continue

        url = f"https://dravya.ccras.org.in/resources/views/admin/required/upload/{source_rid}.jpg"
        print(f"[{i}/{total}] FETCH: #{herb_id} {name} (record {source_rid})...", end=" ", flush=True)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Herbal Almanac; image cache warmer)"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read(5 * 1024 * 1024)

            mime = detect_image_type(data[:12])
            if mime:
                cache_file.write_bytes(data)
                print(f"OK ({len(data):,} bytes, {mime})")
                stats["cached"] += 1
            else:
                print("FAIL (invalid image format / magic bytes)")
                stats["failed"] += 1
        except Exception as e:
            print(f"FAIL ({e})")
            stats["failed"] += 1

        if delay > 0 and i < total:
            time.sleep(delay)

    print("\n--- Summary ---")
    print(f"Total checked: {stats['total']}")
    print(f"Newly cached:  {stats['cached']}")
    print(f"Already cached:{stats['skipped']}")
    print(f"Failed:        {stats['failed']}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-warm the Herbal Almanac local image cache.")
    parser.add_argument("--database", "-d", type=str, default=None, help="Path to SQLite database file.")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay in seconds between requests (default: 0.3s).")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of herbs to process.")
    args = parser.parse_args()

    warm_cache(database_path=args.database, delay=args.delay, max_herbs=args.limit)


if __name__ == "__main__":
    main()
