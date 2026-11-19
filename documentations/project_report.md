# Project Report: Herbal Almanac

**Project Title:** Herbal Almanac: Provenance-Anchored Semantic Knowledge Architecture for Ayurvedic Botanical Medicine  
**Repository:** `SemwalAkhil/NITT-PSP-Project`  
**License:** MIT (Application Code)  
**Academic Scope:** Research, Software Engineering Evaluation, and Botanical Knowledge Organization  

---

## 1. Problem Statement & Motivation

Ayurvedic pharmacology (*Dravyaguna Vijnana*) represents a millennia-old corpus of empirical botanical and clinical observations cataloged across foundational treatises (*Charaka Samhita*, *Sushruta Samhita*, *Astanga Hridaya*, *Bhavaprakasha*) and statutory compendia (*Ayurvedic Pharmacopoeia of India*). However, existing digital repositories face three critical structural failures:

1. **Loss of Epistemic Provenance:** Automated scrapers and digital aggregators routinely flatten nuanced classical statements into unstructured key-value strings or discard attribution, making it impossible to determine whether a claim derives from a primary treatise, a statutory monograph, or an unverified student blog.
2. **The "False Corroboration" Hazard:** Digital aggregators frequently quote identical primary statements without citing the underlying authority. Naive multi-source aggregators treat these duplicate mentions as independent consensus (e.g., claiming "confirmed by 20 sources" when only a single historical observation exists).
3. **Lexical Ambiguity and Linguistic Divergence:** Crucial pharmacological concepts (*Rasa*, *Guna*, *Virya*, *Vipaka*, *Prabhava*, *Doshakarma*) are expressed across regional scripts, classical Sanskrit, and modern vernaculars. Uncontrolled translation algorithms introduce hallucinated or conflicting translations, and compound terms (such as *Tridoshahara* or *Kaphavatahara*) are left un-decomposed.

**Herbal Almanac** resolves these challenges by constructing a relational knowledge graph anchored by immutable source-claim provenance, dual-pathway lifecycle auditing, multilingual concept catalogs, and multi-tier reconciliation.

---

## 2. System Architecture

Herbal Almanac employs an offline-first, 4-tier modular architecture built with Python 3.10+, SQLite, Typer, and FastAPI:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. INGESTION & EXTRACTION                       │
│  CCRAS DRAVYA Portal ──► HTTP Scraper ──► Parser ──► PlantRecord       │
│  - Robust retries, exponential backoff, timeout handling               │
│  - Text cleanup & Unicode NFC normalization (cleaning.py)              │
│  - Optional translation tracking (translation.py)                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  2. STORAGE & OPERATIONAL PROVENANCE                   │
│  SQLite Relational Database (database_operator.py)                     │
│  - Legacy baseline: herbs, illness, treatment, attributes, doshas      │
│  - Stage B Provenance: sources, source_records, source_claims,         │
│    legacy_herb_map, taxa, taxon_relationships, herb_taxa               │
│  - Stage C Semantic Dravyaguna: 11 tables, 2 views, 44 triggers,       │
│    canonical concept catalog (concept_catalog.py)                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                3. CAPABILITY GATING & PRESENTATION LOGIC               │
│  - Exact Ledger Capability Gate: [1, 2] vs [1, 2, 3]                   │
│  - Claim Lifecycle & Adjudication Engine (claim_lifecycle.py)          │
│  - Semantic Backfill Engine with Row Invariance (backfill_engine.py)   │
│  - Localized Repository API & Virya Reconciliation (repository_api.py) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ├──────────────────────────┐
                                    ▼                          ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│          4A. TYPER CLI               │  │    4B. FASTAPI WEB GUI       │
│  - setup, scrape, search, inspect    │  │  - Overview Dashboard (/)    │
│  - upgrade-stage-c, stage-c-status   │  │  - Herb Explorer (/herbs)    │
│  - JSON / CSV export streams         │  │  - Semantic Detail (/herbs/1)│
│                                      │  │  - Virya Recon (/stage-c/..) │
└──────────────────────────────────────┘  └──────────────────────────────┘
```

---

## 3. Implemented Capabilities vs. Design Proposals

To maintain strict scientific and engineering integrity, the repository maintains an explicit demarcation between verified, production-promoted features and architectural design proposals:

| Module / Layer | Status | Implementation Details |
| :--- | :--- | :--- |
| **DRAVYA Scraper & Ingestion** | **IMPLEMENTED** | Robust HTTP scraper (`scrapper.py`), HTML table parsing, NFC Unicode normalization, and `PlantRecord` validation (`cleaning.py`). |
| **Optional Translation Adapter** | **IMPLEMENTED** | Google Translate integration (`translation.py`), caching, rate-limiting, and explicit `machine_generated` / `unverified` metadata tagging. |
| **Legacy Storage & Manual Curation** | **IMPLEMENTED** | SQLite persistence (`database_operator.py`) for herbs, illnesses, attributes, and treatments; supports manual curation survival across re-scraping. |
| **Stage B Operational Provenance** | **IMPLEMENTED** | Schema Migrations 1 & 2: `sources`, `source_records`, atomic `source_claims`, supersession lineage (`supersedes_claim_id`), and botanical taxonomy tables. |
| **Stage C Semantic Dravyaguna** | **IMPLEMENTED** | Migration 3 (`migration_0003_semantic_dravyaguna.py`): 11 normalized tables, 2 views, 44 triggers, and 2 partial unique indexes. |
| **Canonical Concept Catalog** | **IMPLEMENTED** | 136 canonical concepts across 11 domains; 649 multilingual labels covering Hindi (Devanagari), English (Latin), and Sanskrit (Devanagari & IAST). |
| **Claim Lifecycle Engine** | **IMPLEMENTED** | Dual-pathway transitions (routine progression vs. administrative adjudication), trigger hazard defense, selective child reopening, and section omission detection. |
| **Semantic Backfill Engine** | **IMPLEMENTED** | Automated ruleset extraction mapping Stage B claims to Stage C concepts with SHA-256 legacy row invariance checks and compound Dosha decomposition. |
| **Repository API & Reconciliation** | **IMPLEMENTED** | Localized multi-concept profile queries (`herb_dravyaguna_profile`) and 4-tier Virya reconciliation executor (`reconcile_herb_virya`). |
| **Version-Aware Web GUI** | **IMPLEMENTED** | FastAPI/Jinja2 presentation (`web_app.py`) with HTTP 501 capability degradation on Schema v2 and full semantic property cards on Schema v3. |
| **CLI Management & Migration Tooling** | **IMPLEMENTED** | Interactive `upgrade-stage-c` with `--yes` confirmation and `stage-c-status` capability inspection. |
| **Stage D Multi-Source & Evidence** | **PROPOSED ONLY** | Formal architecture proposal in `stage_d_feasibility_and_schema.md`. **Not implemented in active storage.** No `evidence_records` table exists in runtime schemas. |
| **Stages E–I (Descriptions, Safety, Clinical Matching)** | **PROPOSED ONLY** | Future roadmap milestones (clinical matching, symptom search, medical-history screening) reserved for later stages per `roadmap_addendum.md`. |

---

## 4. Testing, Verification & CI/CD Protocol

The codebase enforces strict verification protocols to prevent regressions:

1. **Offline Testing Mandate:** Unit tests never make live network calls to CCRAS or translation APIs. Tests utilize local HTML fixtures (`sample.html`), Sanskrit reference data (`data.txt`), mocked HTTP responses, and temporary SQLite databases (`tmp_path`).
2. **Hermetic CI Environment:** Local databases (`data/inspection.db`) are gitignored and never committed. Hermetic tests synthesize realistic Schema v2 databases dynamically via `hermetic_v2_db_path` in `tests/conftest.py`.
3. **AST-Based Skip Guards:** Static AST analysis in `tests/test_packaging_and_guards.py` scans test modules to ensure any test referencing local database paths contains explicit `pytest.skip` guards, preventing false CI failures.
4. **CI Matrix Coverage:** GitHub Actions (`.github/workflows/tests.yml`) executes against Python 3.10, 3.11, 3.12, 3.13, and 3.14 with `fail-fast: false`.
5. **Multi-Tier Packaging Verification:** Automated smoke tests build the binary distribution wheel (`python -m build`), verify non-Python asset bundling (SQL scripts, templates, CSS), and smoke-test clean virtual environments in both core-only and `[web]` configurations.
6. **Pre-Push Checklist:** Mandatory 6-step verification codified in `agents.md` ensures no code is pushed without scraper regression (57 tests) and full test runner passes.

---

## 5. Limitations, Epistemic Boundaries & Ethical Safeguards

1. **Academic and Research Use Only:** Herbal Almanac is explicitly an academic research and software engineering evaluation platform. It is **not** a clinical decision support system, diagnostic engine, or medical prescribing tool.
2. **No Symptom Matching or Recommendation Algorithms:** The system contains zero clinical diagnostic or treatment recommendation logic. No algorithms match patient symptoms to herbs.
3. **Unverified Machine Translations:** All machine-translated terms are permanently tagged with `machine_generated = 1` and `verification_status = 'unverified'` until reviewed by certified domain experts.
4. **Source Attribution & Copyright:** Ingested textual data originates from the CCRAS DRAVYA portal (Ministry of Ayush, Govt. of India). While the software engine is licensed under the MIT License, primary classical and statutory source texts retain their respective institutional copyright and terms of use.
5. **No Synthetic Clinical Claims:** Automated backfill algorithms strictly assign `mapping_method = 'lexicon_exact'`, `mapping_confidence = NULL`, and `verification_status = 'unreviewed'`, avoiding artificial probability inflation.

---

## 6. Future Work

Following project submission and review:
1. **Stage D Implementation:** Authoring offline-testable parsers for the *Ayurvedic Pharmacopoeia of India* (API) and WHO monographs; implementing DOI/PMID canonicalization and shingle-based mirror deduplication.
2. **Production Upgrade Authorization:** Performing the operator-authorized CLI upgrade (`herbal-almanac upgrade-stage-c --database data/inspection.db --yes`) on live production data.
3. **Authenticated Reviewer Pipeline:** Implementing role-based authentication to promote `unreviewed` claims and labels to `verified` status backed by authoritative treatise citations.
