"""Herbal Almanac — Template HTML Attribute Linter.

Renders key web application pages and checks for duplicated HTML attributes
on any single tag (e.g. duplicate style= or class= attributes).
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import sys
from typing import Any
import tempfile

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient
from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.web_app import create_app


class DuplicateAttributeDetector(HTMLParser):
    """HTML parser that detects duplicate attributes on start and void tags."""

    def __init__(self) -> None:
        super().__init__()
        self.duplicates: list[tuple[str, str, int, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        seen: set[str] = set()
        for name, _ in attrs:
            name_lower = name.lower()
            if name_lower in seen:
                line, col = self.getpos()
                self.duplicates.append((tag, name, line, col))
            seen.add(name_lower)


def lint_html(html_text: str, source_name: str) -> list[str]:
    """Check a single HTML string for duplicate attributes."""
    detector = DuplicateAttributeDetector()
    detector.feed(html_text)
    errors: list[str] = []
    for tag, attr_name, line, col in detector.duplicates:
        errors.append(
            f"[{source_name}:{line}:{col}] Duplicate attribute '{attr_name}' on <{tag}> tag."
        )
    return errors


def lint_all_pages(client: TestClient, herb_id: int, illness_id: int) -> list[str]:
    """Render all key routes and check for duplicated HTML attributes."""
    routes_to_check = [
        "/",
        "/herbs",
        "/herbs?language=ur",
        f"/herbs/{herb_id}",
        f"/herbs/{herb_id}?language=ur",
        f"/herbs/{herb_id}?language=hi",
        f"/herbs/{herb_id}?language=sa",
        "/illnesses",
        f"/illnesses/{illness_id}",
        f"/illnesses/{illness_id}?language=hi",
        f"/illnesses/{illness_id}?language=sa",
        "/treatments",
        "/treatments?language=hi",
        "/attributes",
        "/records",
        "/herbs/add",
        "/illnesses/add",
        "/treatments/add",
        "/guide",
    ]

    all_errors: list[str] = []
    for path in routes_to_check:
        res = client.get(path)
        if res.status_code != 200:
            all_errors.append(f"HTTP {res.status_code} while requesting {path}")
            continue
        errors = lint_html(res.text, path)
        all_errors.extend(errors)

    return all_errors


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "lint_check.db"
        db = AyurvedicAlmanac(db_path)
        db.create_database()
        # Seed at least 1 herb, 1 illness, and 1 treatment
        herb_id = db.add_herb("Bilva", botanical_name="Aegle marmelos", source_record_id=16)
        illness_id = db.add_illness("KAsa")
        db.add_treatment(herb_id, illness_id)

        app = create_app(db_path)
        client = TestClient(app)

        errors = lint_all_pages(client, herb_id, illness_id)
        if errors:
            print(f"FAIL: Found {len(errors)} duplicate attribute issues:")
            for err in errors:
                print(f"  • {err}")
            return 1

        print("PASS: Zero duplicate HTML attributes found across all key rendered pages.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
