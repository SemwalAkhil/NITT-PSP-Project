# Stage D Multi-Source Architecture: Feasibility Analysis, Epistemic Deduplication, and Evidence Schema Proposal

> **ARCHITECTURAL STATUS: DESIGN PROPOSAL ONLY — NOT IMPLEMENTED**  
> This document specifies the architectural design, source feasibility assessments, deduplication algorithms, and proposed relational schema for **Stage D (Multi-Source Ingestion & Scientific Evidence Integration)**.  
> No tables, models, or algorithms described herein are active application storage in the current release. All active storage remains governed by Stage B (Migrations 1 & 2) and Stage C (Migration 3).

---

## 1. Objectives and Scope

Stage C established a unified, 3-layer semantic architecture (Concepts, Mappings, Domain Assertions) and proved zero-data-loss backfill from the baseline CCRAS DRAVYA source. However, an Ayurvedic and botanical knowledge graph cannot rely on a single institutional source without epistemic vulnerability.

The goal of Stage D is to extend Herbal Almanac into a **multi-source, evidence-anchored repository** that synthesizes:
1. **Statutory Pharmacopoeias:** Official government standards establishing identity, purity, and classical properties.
2. **International Regulatory Compendia:** Standardized global botanical monographs.
3. **Biomedical & Pharmacological Literature:** Peer-reviewed preclinical and clinical studies indexed in biomedical repositories.

### Strict Epistemic & Ethical Boundaries
- **Academic & Research Scope Only:** The system is an academic research platform and software evaluation tool, **not** a clinical decision support system, diagnostic tool, or prescribing guide.
- **No Recommendation Engine:** No algorithms will suggest or prioritize herbs for human ailments.
- **No Symptom Matching:** No features will accept patient symptoms and match them to candidate treatments.
- **No Side-Effect Extraction:** Unverified clinical or adverse reactions will not be extracted from literature without validated systematic review provenance.
- **No Overwriting of Classical Texts:** Biomedical findings will exist side-by-side with classical Dravyaguna assertions as distinct provenance-backed claims, never overwriting or mutating classical concepts.

---

## 2. Feasibility and Licensing Review of Candidate Sources

| Candidate Source | Category | Accessibility / Format | Licensing / Terms of Use | Technical Feasibility | Epistemic Utility |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CCRAS DRAVYA Portal** | Classical / Institutional | Public HTTP Web (HTML tables) | Ministry of Ayush, Govt. of India. Research and educational access. | **High** (Active scraper in `scrapper.py`). | Baseline single-source Ayurvedic taxonomy, Dravyaguna properties, vernacular names. |
| **Ayurvedic Pharmacopoeia of India (API)** | Statutory Pharmacopoeia | Gazette PDF Monographs (PCIM&H) | Pharmacopoeia Commission for Indian Medicine & Homoeopathy. Public statutory standard. | **Medium-High** (Requires PDF text extraction, layout parsing, OCR validation). | Authoritative legal standard for identity, purity, Rasapanchaka, officinal parts, and formulations. |
| **WHO Monographs on Selected Medicinal Plants** | International Compendium | Digital PDF & HTML Monographs (Vols 1–4) | World Health Organization. Open access for non-commercial research with attribution. | **High** (Structured sections, international botanical nomenclature, well-defined headings). | Globally recognized botanical identity, validated medicinal uses, chemical constituents, and contraindications. |
| **PubMed / PMC Open Access Subset** | Scientific Literature | REST API (NCBI Entrez E-Utilities: `esearch`, `efetch`) & JATS XML | National Library of Medicine (NIH). Free public API (3–10 req/s with API key). CC BY / CC BY-NC. | **High** (Well-documented XML schema, stable REST endpoints, standard PMIDs and DOIs). | Contemporary in vitro, in vivo, and clinical research data anchoring pharmacology to modern science. |

---

## 3. The False Corroboration Hazard & Epistemic Deduplication Rules

### The Problem: Circular and Derivative Corroboration
In botanical and traditional medicine informatics, a common failure mode is **false corroboration**. For example, a single statement from the *Charaka Samhita* or an early 1970s laboratory report may be repeated across dozens of secondary websites, student blogs, commercial portals, and review articles. If an automated scraper treats every occurrence as an independent "source", the database will report overwhelming consensus (e.g., "confirmed by 45 sources") when only a single primary observation actually exists.

### Proposed Deduplication and Provenance Rules

```
                      [Primary Authority / Treatise / Study]
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
      [Statutory Monograph (API)]                 [Clinical Trial (PubMed)]
                 │                                           │
        (Primary Citation)                          (Primary Citation)
                 │                                           │
                 ▼                                           ▼
         [Source Record A]                           [Source Record B]
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       │
                                       ▼
                       [Derived Secondary Aggregator]
                          (Flagged: mirror_citation)
                       *Zero Independent Epistemic Weight*
```

1. **Canonical Primary Anchor (`primary_reference_id`):**
   - Every extracted claim must record whether it is a primary observation or a citation of an earlier work.
   - If Source B quotes Source A, Source B's claim is linked to Source A's claim via `citation_role = 'derivative_citation'`.
2. **DOI and PMID Canonicalization:**
   - External scientific literature claims must mandate normalized DOI (`10.xxxx/...`) and/or PubMed ID (`pmid`) keys.
   - Duplicate ingests of the same publication from different aggregators are unified under a single primary `evidence_records` row.
3. **Verbatim Text Hashing & Near-Duplicate Shingling:**
   - Sections containing descriptive text (such as action descriptions or historical notes) generate normalized SHA-256 text hashes and 3-word shingle fingerprints.
   - If an incoming source has >85% text overlap with an existing primary record, it is automatically flagged as a mirror (`is_mirror = 1`) and quarantined from independent consensus scoring.
4. **Hierarchical Source Weighting (Epistemic Tiers):**
   - **Tier 1 (Statutory & Systematic):** Pharmacopoeial monographs (API) and peer-reviewed systematic reviews / double-blind RCTs (PubMed).
   - **Tier 2 (Scholarly & Traditional Corpora):** Classical Samhitas, peer-reviewed in vivo pharmacology, academic institutional databases (CCRAS).
   - **Tier 3 (Observational & Preclinical):** In vitro cell assays, open-label observational studies.
   - **Tier 4 (Secondary / Derivative):** Commercial herbal portals, unrefereed encyclopedias. Tier 4 sources are strictly marked `read_only_reference` and cannot corroborate higher-tier assertions.

---

## 4. Proposed Evidence-Record Schema (`evidence_records` Proposal)

The proposed schema links contemporary biomedical literature and pharmacopoeial monographs directly to canonical Stage C concepts and Stage B source claims without altering existing tables.

```sql
-- PROPOSAL: Migration 0004 (Stage D Multi-Source & Evidence Integration)
-- NOT CURRENTLY IMPLEMENTED

CREATE TABLE IF NOT EXISTS evidence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    source_record_id INTEGER NOT NULL REFERENCES source_records(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    source_claim_id INTEGER NOT NULL REFERENCES source_claims(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    
    -- Epistemic Classification
    publication_type TEXT NOT NULL CHECK (
        publication_type IN (
            'statutory_monograph',
            'regulatory_compendium',
            'classical_treatise',
            'systematic_review',
            'randomized_controlled_trial',
            'cohort_study',
            'preclinical_in_vivo',
            'in_vitro_assay',
            'narrative_review'
        )
    ),
    study_type TEXT NULL CHECK (
        study_type IS NULL OR study_type IN (
            'double_blind_rct',
            'open_label_rct',
            'prospective_cohort',
            'retrospective_cohort',
            'in_vivo_animal_model',
            'cell_culture_assay',
            'phytochemical_analysis',
            'meta_analysis'
        )
    ),
    species_population TEXT NULL CHECK (
        species_population IS NULL OR species_population IN (
            'human_adult',
            'human_pediatric',
            'human_geriatric',
            'rodent_murine',
            'rodent_rat',
            'rabbit_lagomorph',
            'cell_line_in_vitro',
            'bacterial_culture'
        )
    ),
    
    -- Botanical & Pharmacological Context (Anchored to Stage C Concepts)
    plant_part_concept_id INTEGER NULL REFERENCES dravyaguna_concepts(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    preparation_concept_id INTEGER NULL REFERENCES dravyaguna_concepts(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    administration_route TEXT NULL CHECK (
        administration_route IS NULL OR administration_route IN (
            'oral',
            'topical',
            'inhalation',
            'sublingual',
            'intraperitoneal_animal',
            'intravenous_animal',
            'other'
        )
    ),
    
    -- Methodological Observation & Limitations
    exposure_dosage_text TEXT NULL,
    measured_outcome TEXT NULL,
    sample_size INTEGER NULL CHECK (sample_size IS NULL OR sample_size > 0),
    methodological_limitations TEXT NULL,
    
    -- Persistent Identifiers & Provenance
    doi TEXT NULL,
    pmid TEXT NULL,
    pmcid TEXT NULL,
    citation_text TEXT NOT NULL,
    external_url TEXT NULL,
    
    -- Mirror & Derivative Tracking
    is_mirror_source INTEGER NOT NULL DEFAULT 0 CHECK (is_mirror_source IN (0, 1)),
    primary_evidence_id INTEGER NULL REFERENCES evidence_records(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    
    created_at TEXT NOT NULL CHECK (length(created_at) >= 20)
);

-- Partial Unique Indexes for Persistent Identifiers (Permitting NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_records_doi 
ON evidence_records(doi) WHERE doi IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_records_pmid 
ON evidence_records(pmid) WHERE pmid IS NOT NULL;

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_evidence_records_claim 
ON evidence_records(source_claim_id);

CREATE INDEX IF NOT EXISTS idx_evidence_records_source_record 
ON evidence_records(source_record_id);

CREATE INDEX IF NOT EXISTS idx_evidence_records_concepts 
ON evidence_records(plant_part_concept_id, preparation_concept_id);
```

---

## 5. Implementation Roadmap and Verification Strategy

When Stage D execution is authorized by project governance:

1. **Step D.1 (Source Extractors):**
   - Implement standalone, offline-testable parsers for API monographs (PDF-to-text with fixture samples) and PubMed E-Utilities XML (mocked HTTP/XML responses).
   - Enforce standard offline testing rules: zero live HTTP calls; all fixtures local.
2. **Step D.2 (Schema Migration 4):**
   - Add Migration 4 (`migration_0004_evidence_records.py`) with atomic forward upgrade, rollback, write-lock acquisition (`BEGIN IMMEDIATE`), and capability gating (`require_stage_d_schema_v4`).
3. **Step D.3 (Epistemic Deduplication Engine):**
   - Implement DOI/PMID canonicalization, text shingle comparison, and mirror quarantine logic.
4. **Step D.4 (Verification Protocol):**
   - Mirror Stage C verification rigor: table snapshot invariance, foreign-key cascade prevention, and regression testing across Python 3.10 through 3.14.
