"""
Herbal Almanac — Offline Demo Database Generator.

Builds a self-contained SQLite demo database strictly offline:
1. Initializes Schema Version 2 ([1, 2]) database.
2. Ingests a validated CCRAS DRAVYA plant record from local sample.html.
3. Adds 2 manual illnesses and manual treatment relationships.
4. Upgrades to Stage C (Schema Version 3: [1, 2, 3]), seeding canonical concept catalog.
5. Runs Stage C semantic backfill to populate concept mappings and properties.
6. Outputs the database path and GUI launch command.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.scrapper import parse_plant

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_demo_database(
    database_path: Path | str | None = None,
    sample_path: Path | str | None = None,
) -> Path:
    """Builds and returns the path to a fully populated, Stage C upgraded demo database."""
    if database_path is None:
        db_path = PROJECT_ROOT / "data" / "demo.db"
    else:
        db_path = Path(database_path)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing demo DB file if present to guarantee deterministic state
    if db_path.exists():
        db_path.unlink()

    # Step 1: Initialize database to Schema Version 2
    almanac = AyurvedicAlmanac(db_path)
    almanac.create_database()

    # Step 2: Ingest plant record from sample.html fixture
    if sample_path is None:
        sample_path = PROJECT_ROOT / "sample.html"
    sample_file = Path(sample_path)
    if not sample_file.is_file():
        raise FileNotFoundError(f"Fixture sample.html not found at: {sample_file}")

    html_content = sample_file.read_text(encoding="utf-8")
    record = parse_plant(plant_id=1, url="https://example.com/plant/1", html=html_content)
    almanac.insert_record(record)

    herbs = almanac.search_herbs("")
    if not herbs:
        raise RuntimeError("Failed to insert plant record from sample.html")
    herb_id = herbs[0]["id"]

    # Step 3: Add 2 manual illnesses and treatment links
    illness_1 = almanac.add_illness("Digestive Weakness")
    illness_2 = almanac.add_illness("Chronic Fatigue")
    almanac.add_treatment(herb_id=herb_id, illness_id=illness_1)
    almanac.add_treatment(herb_id=herb_id, illness_id=illness_2)

    # Step 4: Upgrade to Stage C (Schema v3) and seed canonical concept catalog
    almanac.upgrade_to_stage_c()

    # Step 5: Run Stage C semantic backfill to populate concept mappings & properties
    almanac.run_stage_c_backfill()

    return db_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an offline Herbal Almanac demo SQLite database from sample.html."
    )
    parser.add_argument(
        "--database",
        "-d",
        type=str,
        default=None,
        help="Target SQLite database path (defaults to gitignored 'data/demo.db').",
    )
    args = parser.parse_args()

    db_path = build_demo_database(args.database)

    # Print required information and launch commands
    abs_db_path = db_path.resolve()
    print("=" * 70)
    print("Herbal Almanac — Demo Database Generator")
    print("=" * 70)
    print(f"Database Path: {abs_db_path}")
    print("\nLaunch the Web GUI with this demo database:")
    print(f"HERBAL_ALMANAC_DATABASE={abs_db_path} uvicorn herbal_almanac.web_app:app")
    print("\nWindows PowerShell Alternative:")
    print(f'$env:HERBAL_ALMANAC_DATABASE="{abs_db_path}"; uvicorn herbal_almanac.web_app:app')
    print("=" * 70)


if __name__ == "__main__":
    main()
