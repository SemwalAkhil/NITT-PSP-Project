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

## 3. Immediate next priority: operational provenance integration

Do not begin side-effect extraction, medical-history functionality, symptom matching, or treatment recommendation logic yet.

### Task 0 — Re-establish repository state
- Inspect branch, working tree, latest commit, open PRs, and PR-specific CI.
- Check whether previously mentioned stylesheet PR remains open, merged, or superseded.
- Run tests before changes and record baseline.
- Confirm referenced docs and paths exist.
- Do not overwrite unrelated work.

### Task 1 — Trace DRAVYA ingestion end-to-end
Trace discovery/fetch -> PlantRecord -> cleaning -> optional translation -> insert_record().
Document:
- Source metadata captured.
- Values stored in flexible attributes.
- Normalized Dosha/treatment rows written.
- Whether source, source_record, and source_claim are created/reused.
- Whether names/taxa/attributes link to correct claims.
- Re-scrape behavior when page is unchanged or changed.
- Behavior for parser failure and partial data.

Confirm each behavior in code/tests, not docs alone.

### Task 2 — Design provenance integration before coding
Document:
- Stable source key and source-record identity.
- Source record version/retrieval metadata.
- Claim granularity (field/value or justified grouped assertion).
- Exact source expression and section/field path.
- Review/verification status.
- Links to herbs, names, taxonomy, Dosha, properties, indications, and future safety/preparation claims.
- Correction/supersession without history loss.
- Idempotency rules.
- Transaction and partial-failure behavior.
- Legacy migration/backfill treatment.

Every claim-bearing normalized domain row must have a valid source_claim_id. Manual curation must create a manual source record and claim.

### Task 3 — Implement the smallest safe vertical slice
Start with DRAVYA identity and names:
1. Ensure DRAVYA source row exists.
2. Upsert source_record using stable DRAVYA record identity.
3. Create/reuse claims for source-authored names and extracted attributes.
4. Connect herb_names and herb_taxa to valid claims where schema supports it.
5. Preserve legacy herbs, herb_attributes, herb_doshas, illness, and treatment behavior.
6. Add raw-page hash/artifact metadata only after selecting cache location and retention policy.
7. Make repeated ingestion idempotent.
8. Preserve manual records, links, and claim correction history.
9. Add migration and regression tests.

Avoid a broad rewrite. Each slice must be reviewable and tested.

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

## 8. Definition of done for the next task

- Provenance integration design documented.
- Tested DRAVYA vertical slice creates/reuses source records and claims.
- Existing behavior and legacy databases remain compatible.
- Re-ingestion is idempotent and source updates preserve correction history.
- Failure/partial-data and manual-curation tests exist.
- Full offline test suite passes.
- README, plan, schema, scraper, and database docs accurately describe implementation.
