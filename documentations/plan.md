# Herbal Almanac – Project Plan and SDLC

## 1. Project Overview

Herbal Almanac is a Python-based research system designed to collect, structure, and explore Ayurvedic medicinal plant information.

The project focuses on the relationship between:

- Ayurvedic plant identity.
- Botanical taxonomy.
- Vernacular plant names.
- Dravyaguna properties.
- Dosha effects.
- Plant parts and preparations.
- Therapeutic indications.
- Source evidence and provenance.

The primary source adapter currently targets the CCRAS DRAVYA portal.

The long-term objective is to develop a structured, provenance-aware knowledge base in which traditional terminology, botanical information, and modern research evidence can be connected without losing their original source context.

### 1.1 Core principle

The system must distinguish three different things:

1. **Source evidence:** What the original source actually states.
2. **Normalization:** A standardized representation of the source statement.
3. **Interpretation:** A mapping or inference that connects the source statement to a broader knowledge model.

These must never be treated as interchangeable.

For example:

```text
Original source expression:
    KaphaVātahara

Normalized interpretation:
    Kapha -> decrease
    Vata  -> decrease
    Pitta -> unspecified

Semantic representation:
    Mapping to canonical Dosha and effect concepts
```

The original expression must remain traceable even after semantic mapping.

---

## 2. Overall System Architecture

```text
                  EXTERNAL DATA SOURCES
                           |
                           v
                 SOURCE-SPECIFIC ADAPTERS
                           |
                           v
                  RAW SOURCE EXTRACTION
                           |
                           v
                   CLEANING & VALIDATION
                           |
                           v
                     PlantRecord
                           |
                           v
                    SQLITE DATABASE
                           |
                           v
                 STAGE B: PROVENANCE
                           |
                           v
                STAGE C: SEMANTIC MODEL
                           |
                           v
                  REPOSITORY / VIEW MODEL
                           |
                 +---------+---------+
                 |                   |
                 v                   v
              TYPER CLI          FASTAPI WEB APP
                 |                   |
                 +---------+---------+
                           |
                           v
                         USERS
```

The architecture separates source acquisition, normalization, persistence, semantic interpretation, and presentation.

This makes it possible to introduce additional sources without rewriting the existing database and presentation layers.

---

## 3. Development History and Milestones

### Milestone A – Initial Core Implementation

**Objective:** Establish a reliable pipeline for collecting CCRAS DRAVYA plant records.

The initial implementation concentrated on getting source data into a usable relational database.

#### Implemented functionality

- Plant directory discovery.
- Pagination through the DRAVYA directory.
- Plant detail-page retrieval.
- HTTP retries and request timeouts.
- HTML parsing using BeautifulSoup.
- Section-qualified attribute extraction.
- Vernacular-name extraction.
- Botanical name and family extraction.
- Unicode normalization.
- ASCII transliteration.
- PlantRecord creation and validation.
- Optional translation enrichment.
- Dosha expression normalization.
- SQLite persistence.
- CLI-based database inspection.

#### Main modules

| Module | Responsibility |
|---|---|
| `scrapper.py` | Source discovery and extraction |
| `cleaning.py` | Text normalization and record validation |
| `translation.py` | Optional machine translation |
| `database_operator.py` | SQLite persistence |
| `cli.py` | Command-line interface |

The initial architecture established the principle that scraping, cleaning, and database operations should be separate responsibilities.

### Milestone B – Operational Provenance

**Objective:** Preserve the origin and history of every important source assertion.

The initial database stored plant information, but a research-oriented application also needs to answer:

- Which source supplied this information?
- Which source record did it come from?
- What exactly did the source say?
- Has the source changed its assertion?
- Is the assertion verified or still unverified?
- Which botanical taxon is associated with the plant?

Stage B introduces a provenance layer to answer these questions.

#### Migration 1 – Core identity and provenance

Introduces the source identity and claim-tracking infrastructure.

Important entities:

- `sources`
- `source_records`
- `source_claims`
- `legacy_herb_map`

The legacy herb table is retained, while new source identity and provenance records are added.

The migration includes duplicate-identity preflight and integrity checks.

#### Migration 2 – Botanical taxonomy

Introduces normalized botanical taxonomy relationships.

Important entities:

- `taxa`
- `taxon_relationships`
- `herb_taxa`

The taxonomy layer allows botanical names and their relationships to be represented independently of the legacy herb table.

Taxonomic relationships should not be inferred without supporting evidence.

#### Operational provenance integration

The database insertion process synchronizes the legacy data model with the provenance model.

Important capabilities:

- Idempotent source ingestion.
- Source-record identification.
- Source-claim creation.
- Claim deduplication.
- Claim supersession lineage.
- Vernacular name tracking.
- Botanical taxonomy claim tracking.
- Source expression preservation.

The same source record can be scraped again without creating unnecessary duplicate identities.

When the source changes, the system can preserve the earlier claim and link the new assertion through supersession lineage.

### Milestone C – Semantic Dravyaguna Architecture

**Objective:** Transform source-specific attributes into a controlled, queryable semantic model.

A source may express the same traditional concept using different spellings, languages, or terminology.

Simply storing those strings as attributes is insufficient for advanced research queries.

Stage C introduces a canonical concept system.

#### 3.3.1 Canonical concept catalog

Implemented in:

`concept_catalog.py`

Provides canonical Dravyaguna concepts and their multilingual labels.

The catalog includes concepts across domains such as:

- Rasa.
- Guna.
- Virya.
- Vipaka.
- Prabhava.
- Karma.
- Dosha.
- Plant parts.
- Preparations.
- Indications.
- Related semantic categories.

The project documentation describes a curated catalog containing 136 concepts and more than 640 multilingual labels.

The catalog provides standardized identifiers while retaining source-language expressions.

#### 3.3.2 Semantic database migration

Implemented through:

- `migration_0003_semantic_dravyaguna.py`
- `stage_c_ddl_and_triggers.sql`
- `virya_reconciliation.sql`

The semantic model introduces:

| Entity | Responsibility |
|---|---|
| `dravyaguna_concepts` | Canonical concept definitions |
| `concept_labels` | Multilingual concept labels |
| `concept_label_sources` | Classical textual citations for labels |
| `concept_claim_mappings` | Mapping between source claims and canonical concepts |
| `herb_dravyaguna_properties` | Herb-to-property semantic relationships |
| `dosha_claim_assertions` | Dosha assertions grounded in source claims |
| `herb_dosha_effects` | Structured herb Dosha effects |
| `herb_plant_parts` | Structured plant-part relationships |
| `herb_preparations` | Structured preparation relationships |
| `herb_indications` | Structured therapeutic indication relationships |

The migration uses database integrity constraints and triggers to protect important semantic relationships.

#### 3.3.3 Schema capability gate

Implemented in:

`schema_capability_gate.py`

The capability gate checks the actual database schema and migration state before Stage C functionality is used.

Its purpose is to avoid assuming that every database has already been upgraded.

This is particularly important because the project must retain compatibility with databases created under earlier schema versions.

#### 3.3.4 Claim lifecycle

Implemented in:

`claim_lifecycle.py`

Manages the review and lifecycle of source claims.

The implementation exposes 5 verified public functions for claim and interpretation lifecycle management:

- `transition_claim_status(connection, source_claim_id, new_status, ...)`: Enforces routine review status transitions (`unreviewed` -> `reviewed` -> `verified`, `rejected`, `superseded`).
- `adjudicate_claim_status_override(connection, source_claim_id, new_status, ...)`: Administrative override and reopening with mandatory audit justification logging.
- `transition_interpretation_status(connection, domain, record_id, new_status, ...)`: Independent review status transitions for semantic mappings and assertions.
- `validate_calibrated_mapping_confidence(confidence, review_status, ...)`: Validates confidence thresholds against review status requirements.
- `reconcile_section_omissions(connection, source_id, ...)`: Audits unextracted fields and flags omissions without destructive updates.

The lifecycle system ensures that changes to an assertion are auditable rather than destructive.

#### 3.3.5 Semantic backfill

Implemented in:

`backfill_engine.py`

The backfill engine migrates eligible Stage B claims into Stage C semantic representations.

Its conceptual workflow is:

```text
EXISTING SOURCE CLAIMS
          |
          v
    CLAIM RETRIEVAL
          |
          v
  SOURCE FIELD CLASSIFICATION
          |
          v
   TERMINOLOGY RESOLUTION
          |
          v
   CANONICAL CONCEPT MAPPING
          |
          v
   SEMANTIC RELATIONSHIP CREATION
          |
          v
   STAGE C DATABASE TABLES
```

The original Stage B claim remains available.

The semantic representation is linked back to the claim that supports it.

#### 3.3.6 Repository and presentation layers

Implemented through:

- `repository_api.py`
- `herb_view.py`
- `illness_glossary.py`
- `web_app.py`

These modules separate database operations from presentation.

The repository API supplies structured information.

The view-model layer organizes that information for display.

The web application provides pages and REST endpoints.

The illness glossary supplies multilingual condition labels and search support.

#### 3.3.7 Stage C web interface

The web application includes:

- Dashboard.
- Herb catalog.
- Herb detail pages.
- Illness explorer.
- Illness detail pages.
- Semantic herb profiles.
- Virya reconciliation dashboard.
- REST JSON endpoints.

The semantic herb profile presents the six principal Dravyaguna property domains in a unified structure, along with Dosha effects and other structured information.

### Milestone E – Full Web Parity, Multilingual Discovery, and Accessibility Overhaul

**Objective:** Bring complete feature parity between the CLI and the Web GUI, enable multilingual Indic herb discovery, integrate botanical imagery with offline fallbacks, provide audit data exports (CSV/JSON), and implement full WCAG 2.1 AA accessibility.

#### Implemented Functionality & Completed Checklist

- [x] **Web Data Entry Forms (CLI Parity):**
  - `GET /herbs/add` and `POST /herbs/add`: Form to insert new herbs with field validation (`english_name`, `botanical_name`, `family`, `source`, `source_record_id`, `source_url`).
  - `GET /illnesses/add` and `POST /illnesses/add`: Form to insert new illnesses/indications with unique constraint enforcement and friendly error messages.
  - `GET /treatments/add` and `POST /treatments/add`: Form with searchable select menus to link herbs to illnesses.
  - Same-origin CSRF validation (`verify_same_origin`) for all state-mutating POST endpoints.
- [x] **Explorer Views (CLI Parity):**
  - `GET /treatments`: Web interface for searching, browsing, and paginating treatment associations.
  - `GET /attributes` & `GET /herbs/{id}/attributes`: Web view for source attributes across herbs and per-herb with provenance and verification status.
  - `GET /records`: Web hub for inspecting record groups (`herbs`, `illnesses`, `treatments`, `attributes`, `doshas`) with live database counts and export actions.
  - `GET /stage-c/status` & `POST /stage-c/upgrade`: Web GUI dashboard for Stage C migration status and safe one-click transaction migration.
  - Explanatory UI documenting that live web scraping (`herbal-almanac scrape`) is a long-running batch operation reserved for the CLI to avoid web worker exhaustion.
- [x] **Botanical Plant Imagery (CCRAS Integration):**
  - Dynamic image URL resolution (`herb_image_url`) based on CCRAS plant ID (`https://dravya.ccras.org.in/resources/views/admin/required/upload/<plant_id>.jpg`).
  - Client-side hotlinking only; no live downloads in tests or committed image assets.
  - Responsive thumbnail display on herb explorer cards with `loading="lazy"`.
  - Graceful `onerror` fallback to local packaged SVG (`static/placeholder-herb.svg`).
  - Featured plant image card with CCRAS DRAVYA attribution on herb detail pages.
- [x] **Multilingual Indic Herb Search & Glossary:**
  - Packaged `src/herbal_almanac/data/herb_names.csv` (347 herbs across English + 14 Indian languages).
  - Implementation of `src/herbal_almanac/herb_glossary.py` with `tolerant_herb_key`, `ResolvedHerb`, `HerbGlossaryStore`, `resolve_herb`, and `search_herb_glossary`.
  - Integration into `search_herbs` in `database_operator.py` allowing searches in Devanagari, Tamil, Bengali, etc., to resolve database herbs.
  - CLI `herbal-almanac herbs --language <lang>` option to display vernacular names.
  - Vernacular Names table on herb detail page displaying regional plant names.
  - Coverage auditor script: `scripts/herb_name_coverage.py`.
- [x] **Data Export Endpoints (JSON & CSV):**
  - Endpoints: `/export/herbs.{csv,json}`, `/export/illnesses.{csv,json}`, `/export/treatments.{csv,json}`, and `/herbs/{id}/export.{csv,json}`.
  - Formula injection sanitization (`sanitize_csv_cell`): cells starting with `=`, `+`, `-`, or `@` prepended with `'`.
  - UTF-8 with BOM (`\ufeff`) encoding for instant Indic script rendering in Microsoft Excel.
  - Standards-compliant `Content-Disposition: attachment; filename=...` headers.
- [x] **UI & Accessibility (WCAG 2.1 AA Compliance):**
  - Semantic HTML5 landmarks: `<header role="banner">`, `<nav aria-label="Main navigation">`, `<main id="main-content" role="main">`, `<footer role="contentinfo">`.
  - Visible keyboard skip-to-content link: `<a href="#main-content" class="skip-link">`.
  - Interactive Accessibility Panel with persistent `localStorage` synchronization:
    - Text size scaling (`sm`, `md`, `lg`, `xl`).
    - Font family selection: Default, Clean Sans-Serif, OpenDyslexic / Dyslexia-friendly.
    - Contrast modes: Normal, High Contrast.
    - Theme switching: Light, Dark, System/Auto.
    - `prefers-reduced-motion` compliance.
  - Flash-of-unstyled-content (FOUC) prevention script in `<head>`.
- [x] **Hermetic Testing:**
  - 18 new automated offline tests in `tests/test_web_parity_and_features.py`.
  - Complete packaging verification in `tests/test_packaging_and_guards.py`.

### Milestone D – Multi-source Evidence Integration

**Status: Design proposal, not completed implementation.**

The current ingestion system primarily uses CCRAS DRAVYA.

A future research-oriented system should be capable of incorporating information from independent authoritative sources.

Potential sources include:

- Ayurvedic Pharmacopoeia of India.
- NAMASTE terminology resources.
- Botanical taxonomy repositories.
- Scientific research databases.
- Pharmacological literature.
- Other licensed medicinal plant datasets.

The purpose is not merely to combine data, but to distinguish independent evidence.

For example:

```text
Source A:
    Herb X has a particular property.

Source B:
    Herb X has the same property.

Question:
    Are these independent observations?

Possibilities:
    1. Both sources cite the same classical text.
    2. One source copied the other.
    3. They represent independent research.
```

This distinction is important when assessing evidence strength.

Potential future components:

- Additional source adapters.
- Evidence identity and citation resolution.
- Cross-source claim deduplication.
- Evidence independence classification.
- Authority-specific metadata.
- Confidence and concordance models.

These components require their own feasibility study and should not be treated as existing features.

---

## 4. Data Model Principles

### 4.1 Preserve original source expressions

The source expression must remain available even when a normalized value exists.

### 4.2 Separate identity from terminology

A botanical taxon, an Ayurvedic name, and a vernacular name are not interchangeable.

The database must be capable of representing them independently.

### 4.3 Separate source claims from semantic concepts

A source claim records what a source says.

A canonical concept records the standardized meaning assigned by the system.

A mapping connects the two.

### 4.4 Do not infer missing information

If the source does not specify a Dosha effect, it must remain unspecified.

If a semantic mapping is ambiguous, the system must not silently choose an interpretation.

### 4.5 Maintain historical information

Superseded claims should remain auditable.

Database migrations should be additive wherever possible.

### 4.6 Make ingestion repeatable

Reprocessing the same source record should not create duplicate source identities or unnecessary duplicate claims.

---

## 5. Development Workflow

The project follows a modular development process.

### Step 1 – Source feasibility

Before integrating a source:

- Inspect its HTML, PDF, or spreadsheet structure.
- Identify stable record identifiers.
- Determine the extraction method.
- Identify data licensing and attribution requirements.
- Define which fields can be extracted reliably.

### Step 2 – Data contract

Define a structured representation for extracted records.

For the current DRAVYA adapter, this is `PlantRecord`.

### Step 3 – Extraction

Implement source-specific parsing separately from database operations.

### Step 4 – Cleaning and validation

Normalize text, preserve original expressions, classify attributes conservatively, and validate required fields.

### Step 5 – Persistence

Insert or update the record through the database operator.

Maintain source identity and provenance.

### Step 6 – Semantic mapping

Map eligible claims to the canonical concept catalog.

Keep the original claim available.

### Step 7 – Presentation

Expose the resulting information through the CLI, repository API, and web interface.

### Step 8 – Testing

Test individual functions, database operations, migrations, and end-to-end workflows.

---

## 6. Testing Strategy

### Scraper regression

```bash
python -m pytest tests/test_scrapper.py -q
```

Test cases should cover:

- Plant directory discovery.
- Pagination termination.
- Duplicate plant IDs.
- HTTP failures.
- Request timeouts.
- Section-qualified HTML tables.
- Vernacular-name extraction.
- Scientific profile extraction.
- PlantRecord construction.
- Dosha expression extraction.
- Record persistence.
- Failed-record recovery.

### Database tests

```bash
python -m pytest tests/test_database_connections.py -q
python -m pytest tests/test_database_initialization.py -q
```

Test:

- Connection lifecycle.
- Transaction handling.
- Schema initialization.
- Migration behavior.
- Database concurrency.

### Stage C tests

```bash
python -m pytest tests/test_stage_c_lifecycle.py -q
python -m pytest tests/test_stage_c_migration.py -q
python -m pytest tests/test_stage_c_web.py -q
```

Test:

- Claim lifecycle operations.
- Semantic migration.
- Database constraints.
- Semantic repository output.
- Web presentation.

### Full test suite

```bash
python -m pytest -q
```

### Packaging verification

```bash
python -m build --wheel --no-isolation
```

The installed distribution should also be smoke-tested both with and without optional web dependencies.

---

## 7. Future Roadmap

The following future milestones represent architectural designs and proposals:

1. **Stage D Multi-Source Evidence Integration (Design Only):**
   - Ingestion adapters for statutory pharmacopoeias (Ayurvedic Pharmacopoeia of India — API) and scientific repositories.
   - Cross-source epistemic deduplication algorithms distinguishing identical citations from independent experimental replications.
   - Probabilistic evidence weighting and multi-authority concordance scoring.

2. **Clinical Safety Requirements:**
   - Strict medical disclaimer persistence: this software is an academic research platform, not medical advice.
   - Clear visual differentiation between statutory pharmacopoeial standards and unverified web extractions.
   - Systematic auditing of toxicity data, dosage limits, contraindications, and herb-drug interactions.

3. **Translation Verification:**
   - Expansion of machine-generated regional translations toward clinical expert review.
   - Multi-clinician consensus workflow for dialectical vernacular terms and classical Sanskrit polysemy.

---

## 8. Verification Checklist (Pre-Push & Release Protocol)

Before committing fixes, declaring check failures resolved, or pushing to `main`:

1. **Mandatory Scraper Regression:**
   ```bash
   python -m pytest tests/test_scrapper.py -q
   ```
2. **Full Test Runner Pass:**
   ```bash
   python -m pytest -q
   ```
3. **Build Distribution Wheel:**
   ```bash
   python -m build --wheel --no-isolation
   ```
4. **Smoke Test Wheel Installation (With and Without `[web]`):**
   - Install the built `.whl` into a clean virtual environment without extras and verify CLI entry point:
     ```bash
     herbal-almanac --help
     ```
   - Install with `[web]` extra (`pip install "dist/<wheel>[web]"`) and run package smoke tests:
     ```bash
     python tests/smoke_installed_package.py
     ```
5. **No Committed Databases or Build Artifacts:**
   Verify `git status` shows no `*.db`, `dist/`, `build/`, or `*.egg-info/` files.
6. **Strict Verification Truthfulness:**
   Never declare tests passed or checks resolved without having executed them locally.

## 9. Milestone F – Pre-submission Stabilization

Prior to final demonstration, a stabilization pass resolves operational and UI constraints identified during user evaluations:

1. **Sidebar Navigation Scroll (`styles.css`):**
   - Converted `.sidebar` to a scrollable container (`height: 100vh; overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain; scrollbar-width: thin`).
   - Adjusted top margin of `.nav-label` from 58px to 28px to eliminate viewport cutoffs on screens <= 650px high.
   - Added dark theme scrollbar styling.

2. **Server-Side Image Proxy and Local Cache (`web_app.py`, `warm_image_cache.py`):**
   - Added `GET /herbs/{herb_id}/image` endpoint serving images with priority: user-uploaded photo -> disk-cached CCRAS image -> live CCRAS fetch with magic-byte validation -> fallback SVG placeholder.
   - Guarded against network failures, timeouts, and non-image payload responses (never raises 500).
   - Created `scripts/warm_image_cache.py` for rate-limited, sequential pre-fetching into `HERBAL_ALMANAC_CACHE_DIR`.

3. **Reusable Language Bar Partial (`_language_bar.html`):**
   - Extracted shared multilingual selector into Jinja2 macro `language_bar(endpoint, path_params, current_language, extra_params)`.
   - Propagated language parameter across herb detail, illness detail, herb list, and associated record navigation.

4. **Herb Photo Contributions (`web_app.py`, `herb_detail_semantic.html`, `herb_form.html`):**
   - Enabled local photo upload (`POST /herbs/{herb_id}/photo`) and removal (`POST /herbs/{herb_id}/photo/delete`) stored strictly on the filesystem (zero database schema migrations).
   - Enforced 5 MB size limit and magic-byte inspection (JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `RIFF...WEBP`).

5. **Accessibility Drawer & Table Overflow Polish (`base.html`, `styles.css`):**
   - Added `max-height: calc(100vh - 105px)` with `overflow-y: auto` to prevent drawer clipping on short screens.
   - Updated vanilla JavaScript to synchronize `aria-expanded` across sidebar and topbar toggles.
   - Added Escape key and outside-click dismissal with focus return to the triggering control.
   - Wrapped wide data tables with horizontal scroll containers for mobile viewports (< 480px).

## 10. Architectural Summary

The project evolves through three major architectural transformations:

```text
STAGE A
Raw web information
        |
        v
Structured plant records
        |
        v
SQLite database

STAGE B
Structured plant records
        |
        v
Source identity and claims
        |
        v
Auditable provenance

STAGE C
Source claims
        |
        v
Canonical Dravyaguna concepts
        |
        v
Semantic knowledge graph
        |
        v
Research-oriented presentation

STAGE D (PROPOSED)
Independent evidence sources
        |
        v
Evidence reconciliation
        |
        v
Multi-source research platform
```

The long-term objective is to build a system where Ayurvedic knowledge can be explored through standardized concepts while retaining the original evidence, terminology, and source history behind every assertion.

---

## 11. Milestone G – UI/CSS Polish & Accessibility Correctness

Completed ahead of final evaluation to deliver a polished, accessible, and responsive user experience across desktop and mobile devices:

- [x] **Task 1: Navigation & Route Cleanup:** Removed legacy `/stage-c/status` HTML template/route to prevent user confusion, redirected `POST /stage-c/upgrade` to `/` with 303, pointed topbar link to `records_view`, and ensured Stage C status reporting remains strictly via JSON API (`/api/stage-c/status`) and Typer CLI (`herbal-almanac stage-c-status`).
- [x] **Task 2: Brand Favicon & Dynamic Cache-Busting:** Created standalone brand SVG favicon (`static/favicon.svg`), registered `/favicon.ico` route with HTTP 200/204 response, and added dynamic `css_version()` cache-busting timestamp query parameter (`styles.css?v=...`).
- [x] **Task 3: Automated CSS Class Audit:** Created `scripts/audit_css_classes.py` to audit all template HTML class tokens against stylesheet selectors; added comprehensive base styling and component rules for all 24 previously unstyled template classes (0 unstyled classes).
- [x] **Task 4: Herb List Thumbnail Grid:** Refactored `.herb-row` into a canonical 4-column CSS grid (`64px minmax(0, 1fr) minmax(0, 1fr) 20px`) with a fixed 56x56 thumbnail container, responsive wrapping, and `.herb-row--symbol` modifier for illness list views.
- [x] **Task 5: Multilingual Herb Names & Script Support:** Added `herb_name(herb, lang)` helper in `herb_view.py` backed by `HerbGlossaryStore` with Indic script support (Devanagari, Tamil, Urdu `dir="rtl"`, etc.) and graceful non-availability indicators. Integrated `_language_bar.html` on `/herbs` preserving search filters and pagination params.
- [x] **Task 6: Accessible Text Scaling (`rem` conversion):** Developed `scripts/px_to_rem.py` to convert all font-size declarations from `px` to `rem` (base 14px = 1rem), updated root `html` font size to percentage scale (`sm`: 81.25%, `md`: 87.5%, `lg`: 100%, `xl`: 112.5%), and expanded sidebar width to `18rem` for proportional scaling.
- [x] **Task 7: Offline Inline SVG Icon Set:** Created `templates/_icons.html` defining a pure SVG `icon(name, size=18)` macro with 14 core Lucide/Feather stroke geometry icons, replacing all emojis and inconsistent Unicode symbols.
- [x] **Task 8: Verification & Documentation:** Validated 0 unstyled CSS classes, achieved 261 passing hermetic offline tests, performed visual inspection across 1440px/1024px/390px viewports, and synchronized all project documentation.

---

## 12. Milestone H – Final Polish & Clean-Install Integrity

Executed as the final pre-submission verification and stabilization pass to guarantee rock-solid usability, safe URL encoding, accessibility, and zero-defect installation across modern Python environments:

- [x] **Task 1: Safe URL Building with `qs` Helper:** Implemented `qs(**params)` template global in `herb_view.py` and `web_app.py` using `urllib.parse.urlencode`, automatically omitting empty string and `None` parameters while safely encoding query parameters and non-ASCII Unicode strings across `/herbs`, `/illnesses`, `/treatments`, `/attributes`, and `/records`. Clear search links properly retain active language choices.
- [x] **Task 2: Duplicate HTML Attribute Elimination:** Fixed duplicate inline style attribute on Urdu localized herb names in `herb_detail_semantic.html`, moving styling into canonical CSS rules `.localized-herb-name[dir="rtl"]`. Implemented automated HTML parser linter `scripts/lint_templates.py` and hermetic test `test_template_duplicate_attributes_linter` to permanently prevent attribute duplication.
- [x] **Task 3: Mobile Accessibility Indicator & 360px Topbar Fit:** Replaced all colloquial and internal "A11y" user-facing labels with standard "Accessibility" or SVG iconography. Adjusted mobile responsive rules so that the brand mark and accessibility pill fit comfortably on a single line at 360px viewport width without horizontal wrapping or clipping.
- [x] **Task 4: Full Lucide SVG Icon Migration:** Replaced all remaining raw emojis and pictographs (`📷`, `📂`, `✿`, `⚖`) across all templates with inline SVG geometry (`camera`, `upload`, `scale`, `leaf`) from `_icons.html`. Added `test_no_emojis_in_any_templates` enforcing 100% pure SVG presentation.
- [x] **Task 5: Visual Verification & RTL Alignment:** Verified responsive layouts across 1440px desktop and 390px/360px mobile viewports. Aligned Urdu herb names (`dir="rtl"`) with full-width right alignment (`.localized-herb-name[dir="rtl"]` and `.herb-main strong[dir="rtl"]`) with protective padding. Styled "Clear search" text links with dark-mode and high-contrast theme overrides.
- [x] **Task 6: Regression & Integrity Test Suite:** Added comprehensive regression tests in `tests/test_stage_c_web.py` covering multilingual search (Bael / Bilva in Hindi, Tamil, Telugu), URL encoding round-tripping for special characters, localized herb display in treatment explorer, absence of raw emojis, and absence of user-visible "A11y" strings.
- [x] **Task 7: Clean-Install Smoke Test:** Promoted web runtime requirements (`fastapi`, `jinja2`, `python-multipart`, `uvicorn[standard]`) to core `project.dependencies` in `pyproject.toml` and created `MANIFEST.in` ensuring all HTML templates, static assets, migrations, and glossary CSVs package into wheels and sdists. Executed complete non-editable `pip install .` and automated HTTP endpoint smoke test in an isolated virtual environment.
- [x] **Task 8: Documentation & Release Tagging:** Synchronized SDLC plan and web application reference manuals, confirmed zero unstyled CSS classes and clean test suite passing, tagged release as `demo-ready`, and pushed to `origin/main`.


