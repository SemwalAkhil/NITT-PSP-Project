"""
Audit CSS Classes across Jinja templates against static/styles.css.

Extracts all class names referenced in HTML templates, checks for corresponding
CSS selectors in styles.css, and reports missing / unstyled classes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "src" / "herbal_almanac" / "templates"
STYLESHEET_PATH = PROJECT_ROOT / "src" / "herbal_almanac" / "static" / "styles.css"

# Semantic or JS-only hooks that do not strictly require a direct standalone CSS class
# or are dynamic pseudo-states handled specifically:
ALLOWLIST = {
    "active",
    "disabled",
    "hidden",
    "required",
}


def extract_template_classes(templates_dir: Path) -> dict[str, set[str]]:
    """Scan all HTML templates and extract class names per file."""
    classes_by_file: dict[str, set[str]] = {}

    for html_file in sorted(templates_dir.glob("*.html")):
        content = html_file.read_text(encoding="utf-8")
        classes_found: set[str] = set()

        # Handle class="..."
        for m in re.finditer(r'class="([^"]*)"', content):
            raw = m.group(1)
            raw = re.sub(r"\{%.*?%\}", " ", raw, flags=re.DOTALL)
            raw = re.sub(r"\{\{.*?\}\}", " ", raw, flags=re.DOTALL)
            for token in raw.split():
                token = token.strip().rstrip("-")
                if token and re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", token):
                    classes_found.add(token)

        # Handle class='...'
        for m in re.finditer(r"class='([^']*)'", content):
            raw = m.group(1)
            raw = re.sub(r"\{%.*?%\}", " ", raw, flags=re.DOTALL)
            raw = re.sub(r"\{\{.*?\}\}", " ", raw, flags=re.DOTALL)
            for token in raw.split():
                token = token.strip().rstrip("-")
                if token and re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", token):
                    classes_found.add(token)

        classes_by_file[html_file.name] = classes_found

    return classes_by_file


def extract_css_classes(css_path: Path) -> set[str]:
    """Extract all CSS class selectors from stylesheet."""
    if not css_path.is_file():
        return set()
    content = css_path.read_text(encoding="utf-8")
    # Matches class selectors like .btn, .page-header, .table-container
    matches = re.findall(r"\.([a-zA-Z_][a-zA-Z0-9_-]*)", content)
    return set(matches)


def audit_classes() -> tuple[set[str], dict[str, list[str]]]:
    """Run audit and return (all_missing_classes, missing_by_file)."""
    classes_by_file = extract_template_classes(TEMPLATES_DIR)
    css_classes = extract_css_classes(STYLESHEET_PATH)

    all_template_classes: set[str] = set()
    for cls_set in classes_by_file.values():
        all_template_classes.update(cls_set)

    missing_classes = sorted(
        cls for cls in all_template_classes
        if cls not in css_classes and cls not in ALLOWLIST
    )

    missing_by_file: dict[str, list[str]] = {}
    for filename, cls_set in classes_by_file.items():
        file_missing = sorted(cls for cls in cls_set if cls in missing_classes)
        if file_missing:
            missing_by_file[filename] = file_missing

    return set(missing_classes), missing_by_file


def main() -> int:
    print(f"Auditing templates in: {TEMPLATES_DIR}")
    print(f"Against stylesheet:   {STYLESHEET_PATH}\n")

    missing, missing_by_file = audit_classes()

    if not missing:
        print("PASS: Zero unstyled template classes found! All classes defined in styles.css.")
        return 0

    print(f"FAIL: Found {len(missing)} unstyled CSS class(es) across templates:\n")
    for cls in sorted(missing):
        print(f"  - {cls}")

    print("\nBreakdown by template file:")
    for filename, classes in sorted(missing_by_file.items()):
        print(f"  {filename}: {', '.join(classes)}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
