"""Herbal Almanac — Herb Name Glossary Coverage Auditor.

Inspects an existing Herbal Almanac database and reports:
1. Distinct herbs in the database and their multilingual glossary resolution status.
2. Resolution percentage and any unresolved herb terms.
3. Vernacular language coverage statistics across Indian languages.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import Any

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from herbal_almanac.database_operator import default_database_path
from herbal_almanac.herb_glossary import (
    HERB_LANGUAGE_COLUMNS,
    get_herb_glossary_store,
)


def audit_herb_coverage(database_path: Path | str) -> dict[str, Any]:
    """Audits distinct herbs in a SQLite database against the herb names glossary."""
    db_file = Path(database_path)
    if not db_file.is_file():
        raise FileNotFoundError(f"Database not found at: {db_file}")

    conn = sqlite3.connect(f"file:{db_file.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, english_name, original_name, botanical_name, source_record_id FROM herbs ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()

    store = get_herb_glossary_store()
    total = len(rows)
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    lang_counts: dict[str, int] = {lang: 0 for lang in HERB_LANGUAGE_COLUMNS.values()}

    for herb in rows:
        plant_id = store.get_plant_id(herb)
        res = store.resolve_by_id(plant_id) if plant_id else None

        if res:
            resolved.append({"herb": herb, "resolved": res, "plant_id": plant_id})
            for col in HERB_LANGUAGE_COLUMNS.values():
                val = res.vernacular_names.get(col)
                if val and val != "N/A":
                    lang_counts[col] += 1
        else:
            unresolved.append(herb)

    return {
        "database_path": str(db_file.resolve()),
        "total_herbs": total,
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "resolved_percentage": (len(resolved) / total * 100.0) if total > 0 else 100.0,
        "resolved": resolved,
        "unresolved": unresolved,
        "lang_counts": lang_counts,
    }


def print_herb_coverage_report(audit_result: dict[str, Any]) -> None:
    """Prints a formatted terminal audit report."""
    print("=" * 70)
    print("Herbal Almanac — Herb Name Glossary Coverage Audit")
    print("=" * 70)
    print(f"Database: {audit_result['database_path']}")
    print(f"Total distinct herbs: {audit_result['total_herbs']}")
    pct = audit_result["resolved_percentage"]
    print(f"Resolved: {audit_result['resolved_count']} / {audit_result['total_herbs']} ({pct:.1f}%)")
    print(f"Unresolved: {audit_result['unresolved_count']}")

    print("\nVernacular Language Availability for Resolved Herbs:")
    for lang, count in audit_result["lang_counts"].items():
        res_total = audit_result["resolved_count"]
        lang_pct = (count / res_total * 100.0) if res_total > 0 else 0.0
        print(f"  • {lang:15}: {count:4d} / {res_total} ({lang_pct:.1f}%)")

    if audit_result["unresolved"]:
        print("\nUnresolved Herb Records:")
        for h in audit_result["unresolved"]:
            name = h.get("english_name") or h.get("original_name") or f"Herb #{h.get('id')}"
            bot = h.get("botanical_name") or "no botanical name"
            print(f"  - [{h.get('id')}] {name} ({bot})")
    else:
        print("\nUnresolved Herb Records: None (100% matched)")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit herb name glossary coverage against a database."
    )
    parser.add_argument(
        "database",
        nargs="?",
        default=str(default_database_path()),
        help="Path to Herbal Almanac SQLite database file.",
    )
    args = parser.parse_args()

    try:
        report = audit_herb_coverage(args.database)
        print_herb_coverage_report(report)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
