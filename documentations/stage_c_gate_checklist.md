# Stage C Gate Verification Checklist

## Executive Summary & Milestone Status

This document provides the formal architectural verification and gate closure audit for **Stage C (Semantic Dravyaguna Architecture & Provenance Integration)** of the Herbal Almanac repository.

- **Milestone Scope:** Stage C.1 (Schema, DDL, 44 Triggers, Migration 3) and Stage C.2 (Work Packages WP-0 through WP-7: Catalog, Gating, Claim Lifecycle, Semantic Backfill, Repository API, Web Presentation, Package Promotion & CLI Tooling).
- **Gate Recommendation:** **CLOSED & READY FOR DEPLOYMENT / STAGE D AUTHORIZATION**.
- **Active Production Baseline:** Schema Version 2 (`[1, 2]`), strictly unmutated.
- **Upgrade Pathway:** Fully tested, reversible, and available on demand via `upgrade_to_stage_c()` / `herbal-almanac upgrade-stage-c`.

---

## 1. Schema, Code, and Documentation Agreement Matrix

Every Stage C database entity, constraint, and lifecycle contract was audited across the DDL, migration module, Python services, CLI, Web GUI, and documentation:

| Component | Canonical Artifact | Verification Status | Notes |
| :--- | :--- | :--- | :--- |
| **Stage C DDL & Triggers** | `src/herbal_almanac/migrations/stage_c_ddl_and_triggers.sql` | **VERIFIED** | 11 tables, 2 views, 44 triggers, 2 partial unique indexes. |
| **Migration 3 Module** | `src/herbal_almanac/migrations/migration_0003_semantic_dravyaguna.py` | **VERIFIED** | Atomic `apply_migration` / `rollback_migration` under `BEGIN IMMEDIATE` write lock. |
| **Reconciliation SQL** | `src/herbal_almanac/migrations/virya_reconciliation.sql` | **VERIFIED** | 4 audit queries with exact multi-tier classification and same-claim ambiguity audit. |
| **Concept Catalog** | `src/herbal_almanac/concept_catalog.py` | **VERIFIED** | 136 canonical concepts across 11 domains; 649 multilingual labels. |
| **Capability Gate** | `src/herbal_almanac/schema_capability_gate.py` | **VERIFIED** | Validates exact ledger sequence `[1, 2]` or `[1, 2, 3]`; raises `FeatureUnavailableError` (v2) or `MigrationError` (corrupt). |
| **Claim Lifecycle Engine** | `src/herbal_almanac/claim_lifecycle.py` | **VERIFIED** | Dual-pathway transitions (routine vs. administrative adjudication); selective child reopening; section-level omission engine. |
| **Semantic Backfill Engine** | `src/herbal_almanac/backfill_engine.py` | **VERIFIED** | Ruleset-driven extraction; SHA-256 legacy row invariance checks; compound Doshakarma decomposition. |
| **Repository API** | `src/herbal_almanac/repository_api.py` | **VERIFIED** | Localized profile aggregator (`herb_dravyaguna_profile`) and Virya reconciliation executor (`reconcile_herb_virya`). |
| **Web Presentation** | `src/herbal_almanac/web_app.py` | **VERIFIED** | Version-aware FastAPI presentation with HTTP 501 capability degradation on v2, full semantic cards on v3. |
| **CLI Tooling** | `src/herbal_almanac/cli.py` | **VERIFIED** | Interactive/safe `upgrade-stage-c` with mandatory `--database` and `--yes` confirmation; `stage-c-status` inspection. |
| **Documentation** | `context.md`, `documentations/database_schema.md` | **VERIFIED** | Consistent implementation status: Migrations 1-3 active/promoted; Stage D marked as proposals. |

---

## 2. Legacy Migration Safety & Database Invariance Checklist

- [x] **Safe Default Initialization:** Calling `AyurvedicAlmanac.create_database()` initializes an empty database strictly to Schema Version 2 (`[1, 2]`), creating legacy application tables and Migrations 1 and 2 provenance tables without auto-applying Migration 3.
- [x] **Production Database Protection:** Production database (`data/inspection.db`) remains strictly at Schema Version 2 (`[1, 2]`) and is never committed to Git (gitignored per project rules).
- [x] **Two-Step Upgrade Preflight:** Migration 3 acquires `BEGIN IMMEDIATE` before evaluating `MAX(version) == 2` in `schema_migrations`. Stale-version execution, mid-execution failure, and sequence gaps are safely rejected and rolled back.
- [x] **Cryptographic Legacy Row Invariance:** The backfill engine captures pre- and post-migration SHA-256 digests across all 13 Stage B legacy tables (`herbs`, `illness`, `treatment`, `herb_attributes`, `herb_doshas`, `sources`, `source_records`, `source_claims`, `legacy_herb_map`, `herb_names`, `herb_taxa`, `taxa`, `taxon_relationships`). Zero rows are mutated, deleted, or inserted in legacy tables during Stage C upgrades.
- [x] **Reversible Rollback:** `rollback_stage_c()` drops Stage C views, partial unique indexes, triggers, and tables in reverse dependency order, reverting the migration ledger back to `[1, 2]` idempotently without affecting legacy data.

---

## 3. Linguistic and Epistemic Model Checklist

- [x] **First-Class Multilingual Support:**
  - All 136 canonical concepts provide first-class Hindi (`hi`, Devanagari script) and English (`en`, Latin script) preferred display labels.
  - Sanskrit roots are cataloged across both Devanagari script (`sa`, `Deva`) and International Alphabet of Sanskrit Transliteration (`sa`, `Latn` / IAST).
- [x] **Single Preferred Label Invariant:** Enforced programmatically and verified across all 136 concepts: at most one label per `(concept_id, language_code, script_code)` has `is_preferred = 1`.
- [x] **Calibrated Mapping Epistemology:**
  - Lexicon-exact matches assign `mapping_method = 'lexicon_exact'`, `mapping_confidence = NULL`, and `verification_status = 'unreviewed'`. No artificial 1.0 probability is assigned to exact string matches.
  - Directional Dosha assertions decompose compound expressions (*Tridoshahara*, *Kaphavatahara*) into discrete directional effects (`EFFECT_DECREASE` / `EFFECT_INCREASE`) for specific Dosha concepts (`DOSHA_VATA`, `DOSHA_PITTA`, `DOSHA_KAPHA`).
- [x] **Label Verification Rigor:** Database triggers (`trg_check_label_verification_insert`, `trg_check_label_verification_update`) strictly enforce that any label marked `verified` must supply a non-null `reviewer_id` and have matching authoritative treatise citations in `concept_label_sources`.
- [x] **Transparent Display Label Fallback:** If all candidate labels for an active concept are disputed or rejected, `resolve_concept_display_label` falls back to `concept_code` with `display_label_status = 'unreviewed'` and `is_fallback = True`, preventing silent failures.
- [x] **Strict Ethical Boundaries:**
  - **No medical advice or clinical claims:** The package remains strictly an academic research and software evaluation tool.
  - **No recommendation engine or symptom matcher:** No clinical diagnostic or prescriptive algorithms are implemented.
  - **No side-effect extraction:** Unverified therapeutic or adverse effects are never inferred or synthesized.

---

## 4. Test Suite and Verification Parity

- **Total Test Count:** 192 tests passing locally (100% green).
- **CI Test Count:** 189 passing, 3 cleanly skipped in headless CI runner without `data/inspection.db`.
- **Mandatory Scraper Regression:** 57 tests passing in 0.8s (`tests/test_scrapper.py`).
- **Comprehensive Stage C Harness:** 6 suites passing in 6.3s (`tests/test_stage_c_comprehensive.py`).
- **Package Wheel Smoke Test:** Passing (`tests/smoke_installed_package.py`) with all SQL migrations, Jinja2 templates, and CSS stylesheets bundled.
- **Python Compatibility:** Tested locally on Python 3.14; CI workflow validates across Python 3.10, 3.11, 3.12, 3.13, and 3.14.

---

## 5. Identified Gaps and Transition Notes for Stage D

1. **Active Database Upgrade Execution:** The production database (`data/inspection.db`) was deliberately kept at Schema Version 2 throughout Stage C. An explicit operator migration (`herbal-almanac upgrade-stage-c --database data/inspection.db --yes`) should be executed when live semantic features are desired in production.
2. **Reviewer Promotion Pipeline:** While catalog seeders populate authoritative treatise citations in `concept_label_sources`, labels are initially seeded with `unreviewed` status to comply with trigger constraints. Formal promotion to `verified` requires an authenticated curation turn.
3. **Multi-Source Ingestion Preparation:** Stage C established the normalized schema for multiple sources. Stage D will introduce additional source extractors (Ayurvedic Pharmacopoeia of India, WHO monographs, scientific literature) with evidence scoring and mirror-source deduplication.
