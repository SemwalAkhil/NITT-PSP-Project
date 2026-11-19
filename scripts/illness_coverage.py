"""Herbal Almanac — Illness Glossary Coverage and Catalog Conflict Auditor.

Inspects an existing Herbal Almanac database and reports:
1. Distinct illnesses in the database and their glossary resolution status.
2. Resolution percentage and any unresolved illness terms.
3. If --conflicts is requested, detailed catalog-vs-CSV disagreements for Stage C concepts.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from herbal_almanac.database_operator import default_database_path
from herbal_almanac.illness_glossary import (
    get_catalog_csv_conflicts,
    resolve_illness,
)


def audit_illness_coverage(database_path: Path | str, print_conflicts: bool = False) -> dict[str, Any]:
    """Audits distinct illnesses in a SQLite database against the illness glossary."""
    db_file = Path(database_path)
    if not db_file.is_file():
        raise FileNotFoundError(f"Database not found at: {db_file}")

    conn = sqlite3.connect(f"file:{db_file.resolve()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT id, english_name FROM illness ORDER BY english_name").fetchall()
    finally:
        conn.close()

    total = len(rows)
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []
    kind_counts: dict[str, int] = {"standard": 0, "procedure": 0, "non-disease concept": 0}

    for row_id, name in rows:
        res = resolve_illness(name)
        if res.matched:
            resolved.append({"id": row_id, "name": name, "resolved": res})
            if res.kind in kind_counts:
                kind_counts[res.kind] += 1
            else:
                kind_counts["standard"] += 1
        else:
            unresolved.append(name)

    conflicts = get_catalog_csv_conflicts()

    return {
        "database_path": str(db_file.resolve()),
        "total_illnesses": total,
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "resolved_percentage": (len(resolved) / total * 100.0) if total > 0 else 100.0,
        "resolved": resolved,
        "unresolved": unresolved,
        "kind_counts": kind_counts,
        "conflicts": conflicts,
    }


def print_coverage_report(audit_result: dict[str, Any], show_conflicts: bool = False) -> None:
    """Prints a formatted terminal audit report."""
    print("=" * 70)
    print("Herbal Almanac — Illness Glossary Coverage Audit")
    print("=" * 70)
    print(f"Database: {audit_result['database_path']}")
    print(f"Total distinct illnesses: {audit_result['total_illnesses']}")
    pct = audit_result["resolved_percentage"]
    print(f"Resolved: {audit_result['resolved_count']} / {audit_result['total_illnesses']} ({pct:.1f}%)")
    print(f"Unresolved: {audit_result['unresolved_count']}")

    print("\nConcept Kind Breakdown:")
    for kind, count in audit_result["kind_counts"].items():
        print(f"  • {kind:20}: {count}")

    if audit_result["unresolved"]:
        print("\nUnresolved Illness Terms:")
        for name in audit_result["unresolved"]:
            print(f"  - {name}")
    else:
        print("\nUnresolved Illness Terms: None (100% resolved)")

    if show_conflicts:
        conflicts = audit_result["conflicts"]
        print("\n" + "=" * 70)
        print(f"Stage C Catalog vs. CSV Disagreements ({len(conflicts)} concepts)")
        print("Note: Curated Stage C catalog labels WIN as primary; CSV labels preserved.")
        print("=" * 70)
        for idx, conf in enumerate(conflicts, 1):
            print(f"\n[{idx:02d}] Concept: {conf['catalog_code']} (Term: '{conf['original_term']}')")
            for lang, values in conf["disagreements"].items():
                print(f"     Language [{lang}]:")
                print(f"       - Curated Catalog (Primary): {values['catalog']}")
                print(f"       - Machine CSV (Gemini):      {values['csv']}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit illness glossary coverage on a Herbal Almanac SQLite database."
    )
    parser.add_argument(
        "--database",
        "-d",
        type=str,
        default=None,
        help="Target SQLite database path (defaults to data/demo.db or platform default).",
    )
    parser.add_argument(
        "--conflicts",
        "-c",
        action="store_true",
        help="Print Stage C catalog vs CSV translation disagreements.",
    )
    args = parser.parse_args()

    # Determine default path if not explicitly provided
    target_path = args.database
    if target_path is None:
        local_demo = PROJECT_ROOT / "data" / "demo.db"
        if local_demo.is_file():
            target_path = local_demo
        else:
            target_path = default_database_path()

    audit_result = audit_illness_coverage(target_path, print_conflicts=args.conflicts)
    print_coverage_report(audit_result, show_conflicts=args.conflicts)


if __name__ == "__main__":
    main()
