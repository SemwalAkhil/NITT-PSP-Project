# GitHub Copilot Instructions — Herbal Almanac

## Project Overview
Herbal Almanac (`herbal_almanac`) is a Python 3.10–3.14 library and Typer/Rich CLI (`herbal-almanac`) that scrapes Ayurvedic plant data from the CCRAS DRAVYA portal, cleans/validates records, optionally translates vernacular names, and persists herbs, attributes, illnesses, and treatments into SQLite.

## Core Architecture & Separation of Concerns
Follow the strict pipeline boundary:
`discover → fetch → parse → clean/validate → translate → SQLite transaction`

1. **Scraper Layer (`src/herbal_almanac/`):** Handles URL discovery, retries/timeouts (`requests`, `urllib3`), and HTML parsing (`BeautifulSoup`). Never write raw SQL in the scraper.
2. **Cleaning & Validation (`src/herbal_almanac/cleaning.py`):** Owns `PlantRecord` validation, deterministic Unicode cleanup (`clean_text`), value splitting, and Harvard-Kyoto-style ASCII transliteration for English-facing text while preserving original regional scripts.
3. **Database Layer (`src/herbal_almanac/database_operator.py`):** `AyurvedicAlmanac` owns all SQLite schema creation, in-place migrations, provenance tracking, and transactional upserts across `Herbs`, `herb_attributes`, `Illnesses`, and `Treatment`.
4. **Translation Layer:** Uses `deep-translator` (Google Translator) only when `--translate` is explicitly enabled. Translated attributes must be stored as `Translated Names.<Language>` and marked unverified.

## Strict Coding Rules
- **No Committed Databases:** SQLite `.db` files and translation caches are runtime artifacts stored in the user data directory or `/tmp/`. Never hardcode paths inside the repo or commit `.db` files.
- **Preserve Manual Links:** When updating or refreshing treatment links from `Therapeutic Usage`, ensure manually inserted treatment relationships survive subsequent scrapes.
- **Offline Testing Only:** All pytest suites (`tests/test_scrapper.py`) must remain 100% offline using local fixtures (`sample.html`, `data.txt`) and fake translators/mocks. Never make live network requests in tests.
- **Python Compatibility:** Maintain compatibility across Python 3.10 through 3.14. Use standard type hints.

## Required Work Cycle
For every requested change, follow this numbered cycle:

1. **Select & Scope:** Choose the next concrete task and identify the module, test, and documentation files (`context.md` and `documentations/*.md`) that own it.
2. **Implement:** Implement the task using the existing coding style and conventions. Every new Python file must have a corresponding Markdown file in `documentations/` explaining the script's purpose, inputs, outputs, control flow, and verification steps.
3. **Sync Context & Docs:** Update `context.md` and all relevant files under `documentations/` (`cli.md`, `scrapper.md`, `cleaning.md`, `database_operator.md`, `translation.md`, `plan.md`). If a new documentation heading is introduced, add the corresponding learning to `documentations/learnings.md`.
4. **Verify:** Run the narrowest relevant test or verification command, followed by `python -m pytest tests/test_scrapper.py -q` if any Python or test file changed. If verification fails, return the actual errors and do not claim the task is complete.
5. **Commit Together:** Once verification succeeds, stage the code, tests, `context.md`, and `documentations/` updates together and commit them in a single focused commit.

Keep cycles focused and keep commits limited to the task. Do not overwrite unrelated user changes.