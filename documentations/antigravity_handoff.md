# Antigravity Handoff — What to Do Next

**Purpose:** Execution brief for Antigravity or another coding agent. Read before changing code.  
**Repository:** SemwalAkhil/NITT-PSP-Project  
**Roadmap:** plan.md  
**Requirements:** roadmap_addendum.md and clinical_data_requirements.md

## 1. Read these files first

1. README.md
2. documentations/plan.md
3. documentations/database_schema.md
4. documentations/database_operator.md
5. documentations/scrapper.md
6. documentations/cleaning.md
7. documentations/translation.md
8. documentations/roadmap_addendum.md
9. documentations/clinical_data_requirements.md
10. This file.

Verify current source code and migrations. Documentation describes intended/current state but may become stale.

## 2. Known architecture and constraints

- Python package in src/herbal_almanac; Python 3.10+.
- Current source adapter: CCRAS DRAVYA.
- Main modules include scrapper.py, cleaning.py, translation.py, database_operator.py, cli.py, and optional web_app.py.
- SQLite is the persistence layer. Migrations 1 and 2 add provenance/identity and taxonomy foundations; they do not complete the normalized Dravyaguna schema.
- Web GUI is read-only and reuses the database operator.
- Tests must be offline with fixtures/mocks. Never call live source or translation services in unit tests.
- Preserve Unicode, original source wording, and manual curation.
- Do not introduce a new ORM, framework, or migration system without documenting rationale.
- A proposed table in documentation is not an implemented feature.

## 3. Current status: Stage B and Stage C complete; Stage D preparation

Stage B (operational provenance integration) and Stage C (normalized semantic Dravyaguna architecture & multilingual catalog) are complete, fully verified, and promoted into `src/herbal_almanac/`:
- **Stage B Baseline:** Provenance-tracked source records, source claims, supersession lineage, manual curation survival, and public claim inspection APIs.
- **Stage C Architecture:** 11 tables, 2 views, 44 triggers, Migration 3 (`migration_0003_semantic_dravyaguna.py`), 136 canonical concepts with 649 multilingual labels (`concept_catalog.py`), deterministic capability gating (`schema_capability_gate.py`), claim lifecycle engine (`claim_lifecycle.py`), semantic backfill engine (`backfill_engine.py`), localized repository API (`repository_api.py`), version-aware web presentation (`web_app.py`), and CLI upgrade tools (`cli.py`).
- **Production Baseline:** Production database (`data/inspection.db`) remains unmutated at Schema Version 2 (`[1, 2]`), with an explicit on-demand upgrade pathway (`upgrade-stage-c`).
- **Test Suite Health:** All 190 tests pass locally (187 pass / 3 skip cleanly in CI without uncommitted databases), including the mandatory scraper regression (57 tests).

### Immediate next priority: Stage D — Multi-source scientific evidence and independent corroboration

Do not begin side-effect extraction, medical-history functionality, symptom matching, or treatment recommendation logic yet.

The next engineering priority is Stage D (Step 5 in dependency order):
1. Complete source licensing, copyright, and feasibility reviews before authoring any source adapter.
2. Implement standalone, offline-testable parsers for statutory pharmacopoeias (e.g. Ayurvedic Pharmacopoeia of India) and regulatory compendia (e.g. WHO monographs) using local fixtures.
3. Design and implement epistemic deduplication to prevent false corroboration from secondary mirrors and derivative citations.
4. Integrate peer-reviewed scientific literature (e.g. PubMed/PMC) using persistent identifiers (`doi`, `pmid`) side-by-side with classical Dravyaguna assertions without overwriting classical concepts.

## 4. Required tests

At minimum:
- Source and source_record creation/reuse.
- Distinct claims for distinct assertions.
- Claim-to-subject validation.
- Source URL, timestamp, section/field path, and raw wording preservation.
- Idempotent repeated ingestion.
- Source changes create version/claim or correction lineage per design.
- Parser failure does not erase previously valid data.
- Partial page data is not treated as authoritative deletion.
- Manual treatment links and claims survive scraper updates.
- Transaction rollback leaves no orphan claims/domain rows.
- Migration from populated legacy databases.
- Existing CLI, scraper, database, and GUI tests still pass.

Run:
    python -m pytest tests/test_scrapper.py -q
    python -m pytest tests/test_database_initialization.py -q
    python -m pytest tests/test_database_connections.py -q
    python -m pytest -q

If paths differ, inspect the test tree and use actual names. Never claim tests passed unless executed.

## 5. Execute later work in this dependency order

1. Stabilize current application and CI.
2. Complete source provenance and reproducible ingestion.
3. Finish normalized domain schema (parts, Rasa/Guna/Virya/Vipaka, Karma, Dosha, indications/conditions, preparations).
4. Make Hindi and English first-class, preserving Sanskrit and source scripts.
5. Add licensed authoritative source adapters and independent corroboration.
6. Build cited herb descriptions and source-backed preparation records.
7. Build side-effect, contraindication, precaution, and interaction evidence.
8. Only then consider privacy-controlled medical-history caution.
9. Only after terminology validation, implement multi-symptom retrieval with abstention.
10. Complete public API, versioned datasets, quality reports, and maintenance.

Do not reorder because a later feature seems easier. Prerequisite gates are intentional.

## 6. Safety and product rules

- Herbal Almanac is research/education, not diagnosis or prescribing.
- Never recommend a herb for an individual's symptoms or medical history as clinically validated.
- Never infer dose, duration, preparation, route, contraindication, interaction, or side-effect frequency.
- “No adverse effect found” is not “no side effects.”
- Separate traditional, preclinical, clinical, and regulatory evidence.
- Do not equate Ayurvedic terms to modern diseases using string similarity alone.
- Multi-symptom search returns terminology candidates, not diagnoses. Show matched/unmatched symptoms, alternatives, evidence, and uncertainty; abstain when weak.
- Do not persist personal medical history in the shared herb database. Any future feature requires consent, minimization, separate storage, retention/deletion rules, and privacy/security review.
- Hindi and English are primary user-facing languages; preserve Sanskrit/source terms.
- Machine translation remains unverified until reviewed.

## 7. Working protocol

For every task:
1. Inspect actual code/tests first.
2. State scope, files affected, and acceptance criteria.
3. Propose schema changes before coding.
4. Keep changes narrow.
5. Add tests with every behavior change.
6. Update docs/schema status after implementation.
7. Run targeted tests, then full suite.
8. Review for destructive migrations, data loss, privacy leaks, fabricated evidence, and loss of manual curation.
9. Report exact changes, tests run, failures, limitations, and next dependency.
10. Never mark a feature complete because a table, placeholder, or mockup exists.

## 8. Status of definition of done for Stage B

- [x] Provenance integration design documented.
- [x] Tested DRAVYA vertical slice creates/reuses source records and claims.
- [x] Existing behavior and legacy databases remain compatible.
- [x] Re-ingestion is idempotent and source updates preserve correction history.
- [x] Failure/partial-data and manual-curation tests exist.
- [x] Full offline test suite passes (88 tests).
- [x] README, plan, schema, scraper, and database docs accurately describe implementation.
