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

1. Choose the next concrete task and identify the module, test, or documentation file that owns it.
2. Implement the task using the existing coding style and conventions, then run the narrowest relevant test or verification command.
3. If verification succeeds, commit the completed task with a focused commit message. If verification fails, return the actual errors and do not claim the task is complete.
4. After each cycle, update `context.md` and all relevant files under `documentations/`. If a new documentation heading is introduced, add the corresponding learning to `documentations/learnings.md`.

Keep cycles focused and keep commits limited to the task. Do not overwrite unrelated user changes. Every new Python file must have a corresponding Markdown file explaining the script's purpose, inputs, outputs, control flow, and verification steps, following the documentation style already used in this repository.