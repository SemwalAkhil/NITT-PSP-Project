# Project Context: Herbal Almanac

## 1. Domain & Purpose
Herbal Almanac catalogs Ayurvedic herbs, illnesses, and their therapeutic relationships. It ingests botanical and clinical data from the CCRAS DRAVYA portal into a relational SQLite database and exposes both a Python API and a Typer CLI.

*Disclaimer: For research and software evaluation only, not medical advice.*

## 2. Repository Structure
- `src/herbal_almanac/` — Main package source (`src/` layout).
  - `cleaning.py` — `PlantRecord` data model, `clean_text`, Unicode normalization, and Harvard-Kyoto ASCII transliteration.
  - `database_operator.py` — `AyurvedicAlmanac` class, SQLite schema, migrations, fuzzy search, and transactional upserts.
- `tests/test_scrapper.py` — Offline regression test suite.
- `documentations/` — Detailed module docs (`cli.md`, `scrapper.md`, `cleaning.md`, `database_operator.md`, `translation.md`, `plan.md`, `learnings.md`).
- `sample.html` — Saved DRAVYA HTML fixture for offline parser development.
- `data.txt` — Sanskrit terminology/reference sample.

## 3. Data Model & Attributes
- **Primary Herb Name:** Derived from the source title's Ayurvedic/Sanskrit name when present.
- **Vernacular Names:** Stored in `herb_attributes` as `Vernacular Names.<Language>` (for example, `Vernacular Names.Hindi`).
- **Translated Names:** Generated via `deep-translator` only when `--translate` is passed; stored as `Translated Names.<Language>` and flagged as machine-generated and unverified.
- **Illness & Treatment Links:** Normalized from `Therapeutic Usage` fields into `Illnesses` and `Treatment` join tables. Manual treatment links are preserved across scrapes.
- **Dosha Expressions:** Doshakarma expressions are parsed independently by Dosha/effect group; mixed, unknown, and conflicting expressions are handled conservatively, then persisted with their original source expressions in `herb_doshas`.

## 4. Key Commands
- **Install (Dev):** `pip install -e ".[dev]"` (add `".[translate]"` for translation support).
- **Initialize DB:** `herbal-almanac setup --database /tmp/ayurvedic.db`
- **Dev Scrape:** `herbal-almanac scrape dravya --max-pages 1 --max-plants 5 --database /tmp/ayurvedic.db`
- **Run Tests:** `python -m pytest tests/test_scrapper.py -q`

## 5. Upcoming Roadmap
- Upload release candidate to TestPyPI.
- Expand documented Dosha terminology and query capabilities.
- Build adapters for additional external herbal sources beyond CCRAS DRAVYA.
- Provide a dedicated public Python search API.