# Dravyaguna Data Mapping Project — SDLC Plan (`plan.md`)

## 1. Project Overview & Core Principles

Herbal Almanac maps classical Ayurvedic pharmacology (**Dravyaguna**) to botanical taxonomy, officinal plant parts, pharmacological properties (Rasa, Guna, Virya, Vipaka, Prabhava), therapeutic actions (Karma), and clinical indications.

The architecture enforces a strict epistemic boundary:
```text
SOURCE DATA (CCRAS DRAVYA / Manual)
    ↓
RAW & PARSED DATA (PlantRecord, Section Attributes)
    ↓
STAGE B PROVENANCE (source_records, source_claims, legacy_herb_map, herb_names, taxa)
    ↓
STAGE C SEMANTIC KNOWLEDGE GRAPH (dravyaguna_concepts, concept_claim_mappings, properties)
    ↓
CONSUMPTION INTERFACES (Typer CLI, Read-Only FastAPI Web GUI, REST API)
```
Original source terminology is never overwritten. Interpretations and normalized concepts exist alongside source claims, linked through calibrated mappings and immutable audit lineage.

---

## 2. Milestone Snapshot

- **Legacy Core (Milestone A):** Scraper discovery and parsing, text cleanup, Unicode NFC normalization, conservative Dosha normalization, SQLite transactions, and Typer CLI.
- **Stage B (Milestone B):** Operational provenance integration (Migration 1 and Migration 2). Idempotent ingestion, immutable `source_claims`, claim supersession lineage, duplicate identity preflight, and conservative botanical taxonomy.
- **Stage C.1 & C.2 (Milestone C):** Normalized Dravyaguna semantic architecture.
  - Migration 3 DDL with partial unique indexes and 44 database integrity triggers.
  - Curated Canonical Concept Catalog (`concept_catalog.py`, 136 concepts, 640+ labels across Sanskrit Devanagari/IAST, Hindi, and English).
  - Schema Capability Gate (`schema_capability_gate.py`) ensuring backward compatibility with Schema Version 2.
  - Claim Lifecycle & Review Engine (`claim_lifecycle.py`).
  - Semantic Backfill Engine (`backfill_engine.py`) migrating legacy claims without dropping Stage B rows.
  - Repository API (`repository_api.py`) with localized profiles and Virya reconciliation query.
  - Presentation View-Model Layer (`herb_view.py`) and Web GUI (`web_app.py`) with single 6-column property table, 3-row Dosha matrix, and grouped attribute cards.
  - Multilingual Illness Glossary (`illness_glossary.py`, 227 conditions across 15 Indian languages).
  - CLI commands (`upgrade-stage-c`, `stage-c-status`) and offline demo database generator (`make_demo_db.py`).

---

## 3. Future Roadmap

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

## 4. Verification Checklist (Pre-Push & Release Protocol)

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
