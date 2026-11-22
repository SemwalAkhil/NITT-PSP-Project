r"""scripts/px_to_rem.py

Converts font-size px values to rem (base 14px = 1rem) in static/styles.css
and across Jinja templates in src/herbal_almanac/templates/.

Rules:
- Base size: 14px = 1rem (round(N / 14, 3)rem).
- Convert `font-size: <N>px` to `font-size: <rem>`.
- Convert `clamp(<min>px, <val>, <max>px)` to rem.
- Convert `font: ... <N>px ...` shorthand if present.
- Convert root `html[data-font-size="..."]` to percentage values so that:
    - sm (13px) -> 81.25%
    - md (14px) -> 87.5%
    - lg (16px) -> 100%
    - xl (18px) -> 112.5%
  and root html font-size default -> 87.5% (14px).
  This eliminates all `font-size: \d+px` patterns.
- Convert inline `style="...font-size:\s*\d+px..."` in templates.
- Update sidebar width from 252px to 18rem and main-area margin-left to 18rem.
- Keep media query breakpoints untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

BASE_PX = 14.0


def px_to_rem_str(px_val: float) -> str:
    rem = round(px_val / BASE_PX, 3)
    # Format cleanly (e.g. 1.0 -> 1rem, 0.857 -> 0.857rem)
    formatted = f"{rem:.3f}".rstrip("0").rstrip(".")
    return f"{formatted}rem"


def convert_css_content(css: str) -> str:
    # 1. Update root html data-font-size rules
    css = re.sub(
        r'html\[data-font-size="sm"\]\s*\{\s*font-size:\s*13px;\s*\}',
        'html[data-font-size="sm"] { font-size: 81.25%; }',
        css,
    )
    css = re.sub(
        r'html\[data-font-size="md"\]\s*\{\s*font-size:\s*14px;\s*\}',
        'html[data-font-size="md"] { font-size: 87.5%; }',
        css,
    )
    css = re.sub(
        r'html\[data-font-size="lg"\]\s*\{\s*font-size:\s*16px;\s*\}',
        'html[data-font-size="lg"] { font-size: 100%; }',
        css,
    )
    css = re.sub(
        r'html\[data-font-size="xl"\]\s*\{\s*font-size:\s*18px;\s*\}',
        'html[data-font-size="xl"] { font-size: 112.5%; }',
        css,
    )

    # 2. Add root html default if not present
    if "html { font-size: 87.5%;" not in css and "html{font-size:87.5%;" not in css:
        css = "html{font-size:87.5%}" + css

    # 3. Convert clamp expressions in font-size, e.g. clamp(32px, 3.3vw, 43px)
    def _replace_clamp(match: re.Match) -> str:
        prefix = match.group(1)  # e.g. "font-size:" or "font-size: "
        min_px = float(match.group(2))
        mid = match.group(3)
        max_px = float(match.group(4))
        return f"{prefix}clamp({px_to_rem_str(min_px)},{mid},{px_to_rem_str(max_px)})"

    css = re.sub(
        r"(font-size:\s*)clamp\((\d+(?:\.\d+)?)px\s*,\s*([^,]+)\s*,\s*(\d+(?:\.\d+)?)px\)",
        _replace_clamp,
        css,
    )

    # 4. Convert font-size: <N>px
    def _replace_font_size(match: re.Match) -> str:
        prefix = match.group(1)  # e.g. "font-size:"
        val = float(match.group(2))
        return f"{prefix}{px_to_rem_str(val)}"

    css = re.sub(r"(font-size:\s*)(\d+(?:\.\d+)?)px", _replace_font_size, css)

    # 5. Convert font: shorthand with px (e.g. font:600 11px "DM Sans",sans-serif;)
    def _replace_font_shorthand(match: re.Match) -> str:
        before = match.group(1)
        val = float(match.group(2))
        after = match.group(3)
        return f"{before}{px_to_rem_str(val)}{after}"

    css = re.sub(r"(font:\s*(?:[^;{}]*?\s+)?)(\d+(?:\.\d+)?)px(\s+[^;{}]+)", _replace_font_shorthand, css)

    # 6. Adjust sidebar and main-area width/margin to rem
    # 252px / 14 = 18rem
    css = re.sub(r"\.sidebar\{width:252px;", ".sidebar{width:18rem;", css)
    css = re.sub(r"\.main-area\{margin-left:252px;", ".main-area{margin-left:18rem;", css)
    # media query: 215px / 14 = 15.357rem
    css = re.sub(r"\.sidebar\{width:215px\}", ".sidebar{width:15.357rem}", css)
    css = re.sub(r"\.main-area\{margin-left:215px\}", ".main-area{margin-left:15.357rem}", css)

    return css


def convert_template_inline_styles(html: str) -> str:
    # Match inline styles with font-size: <N>px
    def _replace_inline(match: re.Match) -> str:
        prefix = match.group(1)
        val = float(match.group(2))
        suffix = match.group(3)
        return f"{prefix}{px_to_rem_str(val)}{suffix}"

    return re.sub(r'(font-size:\s*)(\d+(?:\.\d+)?)px([^";]*)', _replace_inline, html)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    css_path = repo_root / "src" / "herbal_almanac" / "static" / "styles.css"
    templates_dir = repo_root / "src" / "herbal_almanac" / "templates"

    print(f"Converting {css_path}...")
    original_css = css_path.read_text(encoding="utf-8")
    converted_css = convert_css_content(original_css)
    css_path.write_text(converted_css, encoding="utf-8")
    print(f"Updated {css_path}")

    # Check remaining px font-size
    remaining = re.findall(r"font-size:\s*\d+(?:\.\d+)?px", converted_css)
    print(f"Remaining 'font-size: Npx' in styles.css: {len(remaining)} {remaining}")

    print(f"Scanning templates in {templates_dir}...")
    template_count = 0
    replacement_count = 0
    for template_file in templates_dir.glob("*.html"):
        content = template_file.read_text(encoding="utf-8")
        matches = re.findall(r"font-size:\s*\d+(?:\.\d+)?px", content)
        if matches:
            converted = convert_template_inline_styles(content)
            template_file.write_text(converted, encoding="utf-8")
            template_count += 1
            replacement_count += len(matches)
            print(f"  {template_file.name}: replaced {len(matches)} inline font-size: {matches}")

    print(f"Templates updated: {template_count} ({replacement_count} replacements)")


if __name__ == "__main__":
    main()
