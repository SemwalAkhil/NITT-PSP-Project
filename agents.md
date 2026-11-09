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
3. AGENTS.md (Root Agent Workflow & Guardrails)
Place AGENTS.md in the root directory. GitHub Copilot Coding Agent, Copilot Edits (Agent Mode in VS Code), and CLI agents automatically read AGENTS.md to know how to build, test, and verify changes.

Markdown
# AI Agent Operating Guide (`AGENTS.md`)

## Environment Setup
Before running commands or tests, ensure the package is installed in editable mode:
```bash
pip install -e ".[dev]"
```

## Agent Work Cycle
For each requested change, follow this sequence:

1. Choose the next concrete task to perform and identify its owning module or documentation file.
2. Work on that task using the existing project style and conventions, then run the narrowest relevant test or verification command.
3. If the test succeeds, commit the completed task with a focused commit message. If the test fails, do not claim completion; return the errors and the affected task clearly.
4. After each cycle, update `context.md` and every relevant file under `documentations/` so the recorded architecture and behavior remain current.

Keep each cycle focused. Do not mix unrelated refactors into the task or its commit. Never remove or overwrite user changes that are unrelated to the current task.

## Verification & Testing Protocol

After modifying any Python file under src/herbal_almanac/ or tests/, you must run the regression suite before concluding your task:

```bash
python -m pytest tests/test_scrapper.py -q
```

## Testing Rules for Agents

**Zero Network Calls in Tests:** Never write tests that hit the live CCRAS DRAVYA website or live Google Translate APIs. Always use sample.html, data.txt, mocked HTTP responses, or a fake translator class.

**Temporary Databases:** When testing CLI commands or AyurvedicAlmanac methods, always pass --database /tmp/ayurvedic-test.db or use pytest tmp_path fixtures. Clean up any temporary files created.

**Documentation Sync:** After every task cycle, update `context.md` and the relevant Markdown documentation. If you add or modify CLI flags, database tables, or cleaning rules, update the corresponding file in `documentations/` (`cli.md`, `scrapper.md`, `cleaning.md`, `database_operator.md`, or `translation.md`). If a new heading is added to any documentation file, add a matching heading or learning entry in `documentations/learnings.md`.

**Python Module Documentation:** Every new Python file must have a matching Markdown file explaining the script's purpose, inputs, outputs, main control flow, and verification steps. Place the explanation with the existing documentation conventions and update `context.md` and `documentations/learnings.md` when the new module introduces a new concept or heading.

## Module Boundaries
**Adding a New Scraper Source:** Keep source-specific HTML selectors isolated from cleaning.py and database_operator.py. Output validated PlantRecord objects so the downstream SQLite transaction layer remains source-agnostic.

**Modifying Schema:** Any change to SQLite tables in database_operator.py must support in-place migration for existing local databases without wiping manual treatment links or provenance records.


---

### 4. `.vscode/settings.json` (VS Code Workspace Configuration)
Create or update `.vscode/settings.json` so VS Code automatically points to `pytest` and feeds your documentation files into GitHub Copilot's context window.

```json
{
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": [
    "tests"
  ],
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "github.copilot.chat.codeGeneration.instructions": [
    {
      "file": ".github/copilot-instructions.md"
    },
    {
      "file": "CONTEXT.md"
    },
    {
      "file": "AGENTS.md"
    }
  ],
  "github.copilot.chat.testGeneration.instructions": [
    {
      "text": "Write offline pytest tests in tests/test_scrapper.py using local fixtures (sample.html, data.txt) and tmp_path for SQLite databases. Never make live network or live translator calls."
    }
  ]
}