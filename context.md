# Project Context: Herbal Almanac

## 1. Domain & Purpose
Herbal Almanac catalogs Ayurvedic herbs, illnesses, and their therapeutic relationships[cite: 1]. It ingests botanical and clinical data from the CCRAS DRAVYA portal into a relational SQLite database and exposes both a Python API and a Typer CLI[cite: 1].

*Disclaimer: For research and software evaluation only, not medical advice[cite: 1].*

## 2. Repository Structure
- `src/herbal_almanac/` — Main package source (`src/` layout)[cite: 1].
  - `cleaning.py` — `PlantRecord` data model, `clean_text`, Unicode normalization, Harvard-Kyoto ASCII transliteration[cite: 1].
  - `database_operator.py` — `AyurvedicAlmanac` class, SQLite schema, migrations, fuzzy search, and transactional upserts[cite: 1].
- `tests/test_scrapper.py` — Offline regression test suite[cite: 1].
- `documentations/` — Detailed module docs (`cli.md`, `scrapper.md`, `cleaning.md`, `database_operator.md`, `translation.md`, `plan.md`, `learnings.md`)[cite: 1].
- `sample.html` — Saved DRAVYA HTML fixture for offline parser development[cite: 1].
- `data.txt` — Sanskrit terminology/reference sample[cite: 1].

## 3. Data Model & Attributes
- **Primary Herb Name:** Derived from the source title's Ayurvedic/Sanskrit name when present[cite: 1].
- **Vernacular Names:** Stored in `herb_attributes` as `Vernacular Names.<Language>` (e.g., `Vernacular Names.Hindi`)[cite: 1].
- **Translated Names:** Generated via `deep-translator` only when `--translate` is passed; stored as `Translated Names.<Language>` and flagged as machine-generated/unverified[cite: 1].
- **Illness & Treatment Links:** Normalized from `Therapeutic Usage` fields into `Illnesses` and `Treatment` join tables[cite: 1]. Manual treatment links are preserved across scrapes[cite: 1].
- **Dosha Expressions:** The cleaning layer now provides deterministic source-preserving normalization for documented Doshakarma expressions; database persistence and scraper integration remain planned.

## 4. Key Commands
- **Install (Dev):** `pip install -e ".[dev]"` (add `".[translate]"` for translation support)[cite: 1]
- **Initialize DB:** `herbal-almanac setup --database /tmp/ayurvedic.db`[cite: 1]
- **Dev Scrape:** `herbal-almanac scrape dravya --max-pages 1 --max-plants 5 --database /tmp/ayurvedic.db`[cite: 1]
- **Run Tests:** `python -m pytest tests/test_scrapper.py -q`[cite: 1]

## 5. Upcoming Roadmap
- Upload release candidate to TestPyPI[cite: 1].
- Normalize Dosha attributes[cite: 1].
- Build adapters for additional external herbal sources beyond CCRAS DRAVYA[cite: 1].
- Dedicated public Python search API[cite: 1].