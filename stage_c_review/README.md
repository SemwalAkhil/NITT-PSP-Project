# Stage C Semantic Dravyaguna Architecture — Independent Review Package

## Overview

This directory (`stage_c_review/`) contains the complete, self-contained implementation artifacts for the **Herbal Almanac Stage C Semantic Dravyaguna Architecture** and **Migration 3 SQL Design**.

Stage C introduces a normalized, 3-layer semantic architecture:
1. **Semantic Concept Taxonomy Layer:** `dravyaguna_concepts`, `concept_labels`, and `concept_label_sources`.
2. **Standardized Lexicon Mapping Layer:** `concept_claim_mappings` and `dosha_claim_assertions`.
3. **Canonical Botanical Formulation & Domain Assertion Layer:** `herb_dravyaguna_properties`, `herb_dosha_effects`, `herb_plant_parts`, `herb_preparations`, and `herb_indications`.

Stage C operates strictly additively on top of Stage B (Migration 1: Base Provenance & Clean Architecture; Migration 2: Classical Taxon Hierarchy). All Stage B legacy tables (`herbs`, `sources`, `source_records`, `source_claims`, `legacy_herb_map`, `herb_attributes`, `herb_doshas`, `taxa`, `taxon_relationships`, `herb_taxa`, and `schema_migrations`) remain intact and unaltered.

> **CRITICAL ARCHITECTURAL CONSTRAINTS:**
> 1. Migration 3 is **NOT** executed against the working project database.
> 2. Application code under `src/herbal_almanac/` and tests under `tests/` remain untouched.
> 3. This directory provides the exact files, queries, schema, and standalone verification suite for independent architectural sign-off.

---

## Deliverable File Manifest

| File | SHA-256 Checksum | Purpose |
| :--- | :--- | :--- |
| `stage_c_ddl_and_triggers.sql` | `8061a0d37024194a135c6e8f133adfb7097c422d55ae930a1e047ef113e094cd` | Complete DDL for the 11 Stage C tables, 2 reporting views, performance indexes, partial unique indexes (`uq_herb_dravyaguna_prop_null_part`, `uq_herb_preparations_null_part`), and 44 integrity triggers enforcing concept hierarchy, domain invariants, cross-herb foreign keys, label verification, snapshot integrity, and source-claim assertion immutability. |
| `virya_reconciliation.sql` | `02f83f50228216114ef52b3ccb6bad5d9a7b2b97b29b9b1878f8c428403cb842` | Four audit queries: Tier 1 (Unreviewed Candidate Divergence), Tier 2 (Reviewed Candidate Divergence), Tier 3 (Verified Source Disagreement), and Query 4 (Same Source Claim Mapping Ambiguity Audit with conservative `h1.id = h2.id` and identical plant-part rule `p1.part_concept_id IS p2.part_concept_id`). Implements mutual exclusivity, plant-part matrix, and 3-way herb identity matching with reviewed vs verified taxonomic claim provenance. |
| `migration_0003_semantic_dravyaguna.py` | `22d013c407ce83230796019be08bfdd5d62d560e79773cbcdc6daab3de76ec86` | Standalone Python migration module providing atomic forward migration (`apply_migration`) with dynamic UTC ISO-8601 timestamp generation, complete rollback (`rollback_migration`), transaction safety checks against `schema_migrations` under write lock (`BEGIN IMMEDIATE` acquired before evaluating prerequisite version: version 2 forward prerequisite, version 3 rollback prerequisite), and split SQL execution with incomplete statement detection. |
| `test_stage_c_comprehensive.py` | `8cbd70e989b47aa17126aa55cc0fa37d44374ef5db7db71cdabfffaa6316292e` | Complete, portable 6-suite verification harness running on an isolated, temporary Stage B database. Dynamically derives paths from `Path(__file__).resolve()`. Validates all DDL, 44 triggers, partial unique indexes, mid-execution failure trace & atomicity rollback, write-lock acquisition and serialization across two connections, transactional version prerequisite validation under write-lock, reconciliation tiers, complete 8x3 identity & taxonomic provenance regression matrix, mapping ambiguity with plant-part scope regression tests, performance indexes, transaction semantics, and rollback. |
| `tests/test_stage_c_migration.py` | `71abda3b540290e7ff30c23cf4fda3b2a2755c66a25861d7ad9bcda2de3c2a3e` | Executable pytest suite validating 23 Stage C requirements: exact object set verification, foreign-key enforcement, cycle prevention, domain consistency, cross-herb contamination prevention, dosha composite pairing, strengthened label verification, citation safeguards, status validation, event ledger integrity, source-claim assertion immutability (all 6 fields for concept mappings and dosha assertions), mid-execution migration failure trace & rollback atomicity, successful version 3 upgrade with dynamic UTC timestamp, rollback/reapplication idempotence, deterministic table snapshot Stage B preservation, nullable composite uniqueness, transactional forward version prerequisite validation under write-lock, transactional rollback version prerequisite validation under write-lock, genuine two-connection write-lock acquisition and serialization (8-step protocol), sequential migration prerequisite rejection on already-upgraded database, and synchronized multi-threaded concurrent write-lock serialization. |
| `README.md` | *(This file)* | Technical manual, schema documentation, and independent review guide. |

---

## Standalone Execution Instructions

The test harness is fully portable and can be executed from any directory within the repository checkout:

```bash
# From repository root:
python stage_c_review/test_stage_c_comprehensive.py
```

The harness dynamically derives the repository root and review directory via `Path(__file__).resolve().parent`, adds `src/` to `sys.path`, and executes against an isolated temporary SQLite database initialized with genuine Stage B schema via `AyurvedicAlmanac`.

---

## Migration Execution & Rollback Protocol

### Forward Migration Contract (`apply_migration`)
- **Connection Safety:** Enforces `if conn.in_transaction: raise RuntimeError(...)` to guarantee the migration runner supplies an unreserved connection with no active transaction.
- **Write Lock & Prerequisite Version Check:** Acquires a write lock immediately via `conn.execute("BEGIN IMMEDIATE;")` *before* querying `schema_migrations`. Evaluates `MAX(version)` under the write lock and requires `MAX(version) == 2`. If the prerequisite check fails, executes `conn.rollback()` and raises `RuntimeError`.
- **Atomicity:** Wraps all DDL, trigger definitions, and the version recording statement inside the same `BEGIN IMMEDIATE; ... COMMIT;` transaction block. Any exception triggers `conn.rollback()` before re-raising.
- **Parsing Integrity:** `execute_statements()` uses `sqlite3.complete_statement()` and raises a `RuntimeError` if incomplete trailing statements or unbalanced tokens exist.
- **Version Ledger:** Inserts `(3, 'semantic_dravyaguna', applied_at)` into `schema_migrations`.

### Rollback Contract (`rollback_migration`)
- **Connection Safety:** Enforces `if conn.in_transaction: raise RuntimeError(...)` to guarantee the migration runner supplies an unreserved connection with no active transaction.
- **Write Lock & Prerequisite Version Check:** Acquires a write lock immediately via `conn.execute("BEGIN IMMEDIATE;")` *before* querying `schema_migrations`. Evaluates `MAX(version)` under the write lock and requires `MAX(version) == 3`. If current schema version is not 3, executes `conn.rollback()` and raises `RuntimeError`.
- **Clean Teardown:** Drops both reporting views, Stage C partial unique indexes (`uq_herb_preparations_null_part`, `uq_herb_dravyaguna_prop_null_part`), all 44 Stage C triggers, and all 11 Stage C tables in reverse dependency order:
  1. `source_reconciliation_events`
  2. `herb_indications`
  3. `herb_preparations`
  4. `herb_plant_parts`
  5. `herb_dosha_effects`
  6. `herb_dravyaguna_properties`
  7. `dosha_claim_assertions`
  8. `concept_claim_mappings`
  9. `concept_label_sources`
  10. `concept_labels`
  11. `dravyaguna_concepts`
- **Version Ledger Update:** Executes `DELETE FROM schema_migrations WHERE version = 3;`.
- **Stage B Preservation Guarantee:** Rollback touches **only Stage C tables, views, and triggers**. All Stage B provenance records, source claims, classical taxon relationships, legacy attributes, and illness/treatment records remain 100% intact.

---

## The Actual 11 Stage C Tables & Schema Relationships

Stage C defines exactly 11 relational tables and 2 reporting views:

```
[dravyaguna_concepts] <────┐ (self-referential hierarchy: parent_concept_id)
        ▲                  │
        │                  ├─────────────────────────────────────────────┐
        │                  │                                             │
 [concept_labels]          │                                             │
        ▲                  │                                             │
        │                  ▼                                             ▼
 [concept_label_sources] [concept_claim_mappings] <── [source_claims] ──> [dosha_claim_assertions]
                                   ▲                                             ▲
           ┌───────────────────────┼────────────────────────┐                    │
           │                       │                        │                    │
           ▼                       ▼                        ▼                    ▼
[herb_dravyaguna_properties] [herb_plant_parts]   [herb_preparations]   [herb_dosha_effects]
        │                                                                        │
        ▼                                                                        ▼
[v_active_herb_dravyaguna_properties]                          [v_active_herb_dosha_effects]
                                   │
                                   ▼
                          [herb_indications]

[source_reconciliation_events] <── [sources]
```

### Table Definitions

1. **`dravyaguna_concepts`**
   - **Primary Key:** `concept_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Columns:** `concept_code TEXT UNIQUE NOT NULL`, `concept_domain TEXT NOT NULL`, `parent_concept_id INTEGER REFERENCES dravyaguna_concepts(concept_id) ON DELETE RESTRICT`, `status TEXT NOT NULL DEFAULT 'active'`, `created_at TEXT NOT NULL`.
   - **Check Constraints:** Domain restricted to `('rasa', 'guna', 'virya', 'vipaka', 'prabhava', 'karma', 'dosha', 'dosha_effect', 'plant_part', 'preparation_form', 'indication')`. Status restricted to `('active', 'deprecated', 'provisional')`. Self-parenting prevented (`parent_concept_id != concept_id`).

2. **`concept_labels`**
   - **Primary Key:** `concept_label_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `concept_id REFERENCES dravyaguna_concepts(concept_id) ON DELETE RESTRICT`
   - **Columns:** `language_code TEXT NOT NULL`, `script_code TEXT NOT NULL`, `label_text TEXT NOT NULL`, `normalized_label TEXT NOT NULL`, `label_type TEXT NOT NULL`, `translation_origin TEXT NOT NULL`, `verification_status TEXT NOT NULL DEFAULT 'unreviewed'`, `reviewed_by TEXT`, `reviewed_at TEXT`, `verified_by TEXT`, `verified_at TEXT`, `reviewer_notes TEXT`, `is_preferred INTEGER NOT NULL DEFAULT 0`, `created_at TEXT NOT NULL`.
   - **Unique Constraint:** `UNIQUE(concept_id, language_code, script_code, normalized_label)`

3. **`concept_label_sources`**
   - **Primary Key:** `label_source_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `concept_label_id REFERENCES concept_labels(concept_label_id) ON DELETE RESTRICT`, `source_id REFERENCES sources(source_id) ON DELETE RESTRICT`
   - **Columns:** `authority_citation TEXT NOT NULL`, `citation_type TEXT NOT NULL`, `verified_by TEXT`, `verified_at TEXT`, `citation_notes TEXT`, `created_at TEXT NOT NULL`.
   - **Check Constraint:** Citation type in `('classical_text', 'statutory_pharmacopoeia', 'multilateral_standard', 'academic_lexicon', 'source_document')`.

4. **`concept_claim_mappings`**
   - **Primary Key:** `mapping_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `source_claim_id REFERENCES source_claims(source_claim_id) ON DELETE RESTRICT`, `concept_id REFERENCES dravyaguna_concepts(concept_id) ON DELETE RESTRICT`
   - **Columns:** `mapping_type TEXT NOT NULL DEFAULT 'exact'`, `mapping_confidence REAL`, `mapping_method TEXT NOT NULL`, `verification_status TEXT NOT NULL DEFAULT 'unreviewed'`, `reviewed_by TEXT`, `reviewed_at TEXT`, `reviewer_notes TEXT`, `created_at TEXT NOT NULL`.
   - **Unique Constraint:** `UNIQUE(source_claim_id, concept_id)`

5. **`dosha_claim_assertions`**
   - **Primary Key:** `dosha_assertion_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `source_claim_id REFERENCES source_claims(source_claim_id) ON DELETE RESTRICT`, `dosha_concept_id REFERENCES dravyaguna_concepts(concept_id) ON DELETE RESTRICT`, `effect_concept_id REFERENCES dravyaguna_concepts(concept_id) ON DELETE RESTRICT`
   - **Columns:** `clause_expression TEXT`, `mapping_confidence REAL`, `mapping_method TEXT NOT NULL`, `verification_status TEXT NOT NULL DEFAULT 'unreviewed'`, `reviewed_by TEXT`, `reviewed_at TEXT`, `reviewer_notes TEXT`, `created_at TEXT NOT NULL`.
   - **Unique Constraint:** `UNIQUE(source_claim_id, dosha_concept_id, effect_concept_id)`

6. **`herb_dravyaguna_properties`**
   - **Primary Key:** `herb_property_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `herb_id REFERENCES herbs(id) ON DELETE RESTRICT`, `mapping_id REFERENCES concept_claim_mappings(mapping_id) ON DELETE RESTRICT`, `part_concept_id REFERENCES dravyaguna_concepts(concept_id) ON DELETE RESTRICT`
   - **Columns:** `qualifier TEXT`, `source_presence_status TEXT NOT NULL DEFAULT 'active'`, `created_at TEXT NOT NULL`.
   - **Unique Constraints & Indexes:** `UNIQUE(herb_id, mapping_id, part_concept_id)` for specified plant parts; partial unique index `uq_herb_dravyaguna_prop_null_part` on `(herb_id, mapping_id) WHERE part_concept_id IS NULL` ensuring duplicate unspecified-part relationships are strictly rejected.

7. **`herb_dosha_effects`**
   - **Primary Key:** `herb_dosha_effect_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `herb_id REFERENCES herbs(id) ON DELETE RESTRICT`, `dosha_assertion_id REFERENCES dosha_claim_assertions(dosha_assertion_id) ON DELETE RESTRICT`
   - **Columns:** `source_presence_status TEXT NOT NULL DEFAULT 'active'`, `created_at TEXT NOT NULL`.
   - **Unique Constraint:** `UNIQUE(herb_id, dosha_assertion_id)`

8. **`herb_plant_parts`**
   - **Primary Key:** `herb_part_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `herb_id REFERENCES herbs(id) ON DELETE RESTRICT`, `mapping_id REFERENCES concept_claim_mappings(mapping_id) ON DELETE RESTRICT`
   - **Columns:** `context_notes TEXT`, `source_presence_status TEXT NOT NULL DEFAULT 'active'`, `created_at TEXT NOT NULL`.
   - **Unique Constraint:** `UNIQUE(herb_id, mapping_id)`

9. **`herb_preparations`**
   - **Primary Key:** `herb_preparation_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - **Foreign Keys:** `herb_id REFERENCES herbs(id) ON DELETE RESTRICT`, `prep_mapping_id REFERENCES concept_claim_mappings(mapping_id) ON DELETE RESTRICT`, `part_mapping_id REFERENCES concept_claim_mappings(mapping_id) ON DELETE RESTRICT`
   - **Columns:** `context_notes TEXT`, `source_presence_status TEXT NOT NULL DEFAULT 'active'`, `created_at TEXT NOT NULL`.
   - **Unique Constraints & Indexes:** `UNIQUE(herb_id, prep_mapping_id, part_mapping_id)` for specified plant parts; partial unique index `uq_herb_preparations_null_part` on `(herb_id, prep_mapping_id) WHERE part_mapping_id IS NULL` ensuring duplicate unspecified-part preparation relationships are strictly rejected.

10. **`herb_indications`**
    - **Primary Key:** `herb_indication_id INTEGER PRIMARY KEY AUTOINCREMENT`
    - **Foreign Keys:** `herb_id REFERENCES herbs(id) ON DELETE RESTRICT`, `mapping_id REFERENCES concept_claim_mappings(mapping_id) ON DELETE RESTRICT`
    - **Columns:** `context_notes TEXT`, `source_presence_status TEXT NOT NULL DEFAULT 'active'`, `created_at TEXT NOT NULL`.
    - **Unique Constraint:** `UNIQUE(herb_id, mapping_id)`

11. **`source_reconciliation_events`**
    - **Primary Key:** `event_id INTEGER PRIMARY KEY AUTOINCREMENT`
    - **Foreign Keys:** `source_id REFERENCES sources(source_id) ON DELETE RESTRICT`
    - **Columns:** `event_type TEXT NOT NULL`, `snapshot_timestamp TEXT NOT NULL`, `extraction_status TEXT NOT NULL DEFAULT 'in_progress'`, `is_complete_snapshot INTEGER NOT NULL DEFAULT 0`, `divergence_count INTEGER NOT NULL DEFAULT 0`, `reconciled_count INTEGER NOT NULL DEFAULT 0`, `initiated_by TEXT NOT NULL`, `notes TEXT`, `created_at TEXT NOT NULL`.
    - **Check Constraint:** `CHECK (is_complete_snapshot = 0 OR extraction_status = 'completed')`

### Reporting Views
- `v_active_herb_dravyaguna_properties`: Joins active herb properties to herbs, mappings, source claims, and concepts.
- `v_active_herb_dosha_effects`: Joins active herb dosha effects to herbs, assertions, source claims, and concepts.

---

## The Actual 44 Integrity Triggers

The schema enforces data integrity through 44 deterministic SQLite triggers categorized into 12 operational domains:

### 1. Source & Record Provenance Protection (5 Triggers)
- `trg_protect_source_key_mutation`: Prohibits mutating `sources.source_key` when dependent records exist.
- `trg_protect_sources_delete`: Prohibits deleting `sources` rows when dependent source records exist.
- `trg_protect_source_record_mutation`: Prohibits reassigning `source_records.source_id` or `external_record_key` when referenced by mapped claims.
- `trg_protect_source_claim_mutation`: Protects original assertion-defining fields (`source_record_id`, `claim_type`, `source_field`, `source_expression`, `language_code`, `normalization_method`) against in-place modification once referenced by Stage C mappings or assertions, while preserving review status transitions, reviewer metadata updates, and supersession lineage.
- `trg_cascade_claim_supersession`: Automatically cascades `superseded` status from a source claim to all child `concept_claim_mappings`.

### 2. Reviewer Metadata & Claim Workflow (2 Triggers)
- `trg_validate_source_claim_review_metadata_insert`: Rejects inserts of `reviewed` or `verified` claims lacking reviewer identity or timestamp.
- `trg_validate_source_claim_review_metadata_update`: Rejects promoting claims to `reviewed`/`verified` without metadata, or clearing reviewer info on reviewed claims.

### 3. Concept Hierarchy & Domain Validation (4 Triggers)
- `trg_prevent_concept_cycle_update`: Recursive CTE preventing hierarchy cycles (`parent_concept_id`).
- `trg_validate_concept_parent_domain_insert`: Enforces that parent and child concepts belong to identical domains.
- `trg_validate_concept_parent_domain_update`: Enforces domain matching when updating concept parentage.
- `trg_prevent_parent_domain_mutation_with_children`: Prohibits altering a concept's domain if child concepts currently exist under it.

### 4. Concept Label & Citation Protection (6 Triggers)
- `trg_validate_label_verification_insert`: Enforces reviewer metadata on newly inserted reviewed/verified labels.
- `trg_validate_label_verification_update`: Enforces strengthened verification rules: rejects `machine_generated` origin; requires `verified_by`/`verified_at` (or reviewer metadata); requires qualifying citation with non-empty citation text, verified reviewer, and verification timestamp.
- `trg_protect_verified_label_identity_mutation`: Prohibits mutating `concept_id`, `label_text`, or verified metadata on verified labels without explicit demotion to `unreviewed`.
- `trg_protect_verified_label_delete`: Prohibits deleting verified labels.
- `trg_protect_verified_label_citation_delete`: Prohibits removing the last verified citation source from a verified label.
- `trg_protect_verified_label_citation_update`: Protects verified citation links against modification or clearing citation text.

### 5. Mapping & Assertion Mutation Protection (2 Triggers)
- `trg_protect_claim_mapping_mutation`: Prohibits mutating `source_claim_id` or `concept_id` on mappings active in herb property relationships.
- `trg_protect_dosha_assertion_mutation`: Prohibits mutating `source_claim_id`, `dosha_concept_id`, or `effect_concept_id` on assertions active in herb dosha effects.

### 6. Legacy & Base Identity Protection (3 Triggers)
- `trg_protect_legacy_herb_map_mutation`: Prohibits modifying active `legacy_herb_map` rows.
- `trg_protect_legacy_herb_map_delete`: Prohibits deleting active `legacy_herb_map` rows.
- `trg_protect_herb_identity_mutation`: Prohibits reassigning `herbs.source` or `herbs.source_record_id` when active Stage C property relationships exist.

### 7. Herb Property Domain & Provenance Validation (4 Triggers)
- `trg_validate_herb_prop_domain_insert`: Enforces domain matching for property mapping (`rasa`, `guna`, `virya`, `vipaka`, `prabhava`, `karma`) and plant part (`plant_part`).
- `trg_validate_herb_prop_domain_update`: Enforces domain matching on property updates.
- `trg_validate_herb_prop_mapping_insert`: Enforces that the mapping's underlying source record matches the herb's provenance `source_record_id`.
- `trg_validate_herb_prop_mapping_update`: Enforces provenance matching on property updates.

### 8. Herb Plant Parts Domain & Provenance Validation (4 Triggers)
- `trg_validate_herb_parts_domain_insert`: Validates `concept_domain = 'plant_part'`.
- `trg_validate_herb_parts_domain_update`: Validates domain on plant part updates.
- `trg_validate_herb_parts_mapping_insert`: Enforces mapping matches the herb's provenance record.
- `trg_validate_herb_parts_mapping_update`: Enforces provenance matching on update.

### 9. Herb Preparations Domain & Cross-Herb Validation (4 Triggers)
- `trg_validate_herb_prep_domains_insert`: Validates `prep_mapping` is `'preparation_form'` and `part_mapping` is `'plant_part'`.
- `trg_validate_herb_prep_domains_update`: Validates preparation domains on update.
- `trg_validate_herb_prep_cross_herb_insert`: Enforces that preparation mapping and optional part mapping belong to the exact same herb record.
- `trg_validate_herb_prep_cross_herb_update`: Enforces same-herb consistency on preparation update.

### 10. Herb Indications Domain & Provenance Validation (4 Triggers)
- `trg_validate_herb_indications_domain_insert`: Validates `concept_domain = 'indication'`.
- `trg_validate_herb_indications_domain_update`: Validates indication domain on update.
- `trg_validate_herb_indications_mapping_insert`: Enforces indication mapping matches the herb's provenance record.
- `trg_validate_herb_indications_mapping_update`: Enforces provenance matching on update.

### 11. Dosha Assertions & Effects Validation (4 Triggers)
- `trg_validate_dosha_assertion_domains_insert`: Enforces `dosha_concept_id` is `'dosha'` and `effect_concept_id` is `'dosha_effect'`.
- `trg_validate_dosha_assertion_domains_update`: Enforces dosha domains on assertion update.
- `trg_validate_herb_dosha_assertion_insert`: Enforces that the assertion's underlying source record matches the herb's provenance `source_record_id`.
- `trg_validate_herb_dosha_assertion_update`: Enforces provenance matching on dosha effect update.

### 12. Source Reconciliation Event Integrity (2 Triggers)
- `trg_protect_reconciliation_snapshot_integrity_insert`: Enforces that incomplete or failed extractions cannot have `is_complete_snapshot = 1`.
- `trg_protect_reconciliation_snapshot_integrity_update`: Enforces that incomplete or failed extractions cannot be updated to `is_complete_snapshot = 1`.

---

## Herb Identity Predicate Specification

In `virya_reconciliation.sql`, property pairs `(p1, p2)` are generated by joining on ordered property IDs:

```sql
FROM herb_dravyaguna_properties p1
...
JOIN herb_dravyaguna_properties p2 ON p2.herb_property_id > p1.herb_property_id
JOIN herbs h1 ON h1.id = p1.herb_id
JOIN herbs h2 ON h2.id = p2.herb_id
```

Because property comparison is ordered by `p2.herb_property_id > p1.herb_property_id`, the comparison pair can evaluate properties from the **same herb record** (`h1.id = h2.id`) or from **distinct herb records** (`h1.id != h2.id`). The candidate herb identity predicate is defined as:

```sql
WHERE (
    -- Condition 1: Same herb record
    h1.id = h2.id
    -- Condition 2: Same non-empty botanical-name string
    OR (
        h1.botanical_name IS NOT NULL 
        AND trim(h1.botanical_name) != '' 
        AND h1.botanical_name = h2.botanical_name
    )
    -- Condition 3: Shared accepted taxon verified via herb_taxa with reviewed/verified claim provenance
    OR EXISTS (
        SELECT 1 FROM herb_taxa ht1
        JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
        JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
        JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
        WHERE ht1.herb_id = h1.id 
          AND ht2.herb_id = h2.id
          AND ht1.relationship_type = 'accepted' 
          AND ht2.relationship_type = 'accepted'
          AND sc_taxa1.verification_status IN ('reviewed', 'verified')
          AND sc_taxa2.verification_status IN ('reviewed', 'verified')
    )
)
```

> **NOTE ON NON-CONTRADICTION:**
> Earlier draft documentation erroneously described this as `WHERE h1.id < h2.id AND h1.id = h2.id`. In the actual SQL, pair ordering is strictly enforced on property records (`p2.herb_property_id > p1.herb_property_id`), allowing `h1.id = h2.id` to be evaluated cleanly without contradiction.

### Identity Basis Transparency
All queries project an explicit `identity_basis` column:
- `'same_herb_record'`: When `h1.id = h2.id`.
- `'taxonomically_verified_shared_accepted_taxon'`: When both herb records share an accepted taxon (`relationship_type = 'accepted'`) where **both** underlying taxon source claims have `verification_status = 'verified'`.
- `'taxonomically_reviewed_shared_accepted_taxon'`: When both herb records share an accepted taxon backed by claims in `('reviewed', 'verified')`, but at least one claim is `'reviewed'`.
- `'candidate_match_botanical_string_equality'`: Pure lexical string equality on non-empty botanical names.
- `'unmatched'`: Fallback condition.

### Comprehensive 8x3 Identity Matching & Taxonomic Provenance Regression Matrix:
The test harness explicitly executes and proves the identity conditions across all three tiers:

| Identity Condition | Tier 1 (Unreviewed Mapping) | Tier 2 (Reviewed Broader Mapping) | Tier 3 (Verified Exact Mapping) |
| :--- | :---: | :---: | :---: |
| **1. Shared accepted taxon with verified provenance** | **INCLUDED** (`taxonomically_verified_shared_accepted_taxon`) | **INCLUDED** (`taxonomically_verified_shared_accepted_taxon`) | **INCLUDED** (`taxonomically_verified_shared_accepted_taxon`) |
| **2. Shared accepted taxon with reviewed provenance** | **INCLUDED** (`taxonomically_reviewed_shared_accepted_taxon`) | **INCLUDED** (`taxonomically_reviewed_shared_accepted_taxon`) | **INCLUDED** (`taxonomically_reviewed_shared_accepted_taxon`) |
| **3. Shared accepted taxon with unreviewed provenance** | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) |
| **4. Shared synonym relationship only** | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) |
| **5. Shared source-identification relationship only** | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) |
| **6. Same non-empty botanical name** | **INCLUDED** (`candidate_match_botanical_string_equality`) | **INCLUDED** (`candidate_match_botanical_string_equality`) | **INCLUDED** (`candidate_match_botanical_string_equality`) |
| **7. Same herb record (`h1.id = h2.id`)** | **INCLUDED** (`same_herb_record`) | **INCLUDED** (`same_herb_record`) | **EXCLUDED from Tier 3 by `s1.source_id != s2.source_id` (Routes to Tier 2 Case C)** |
| **8. Unrelated herbs** | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) | **EXCLUDED** (0 rows) |

---

## Plant-Part Comparison Matrix & Rules

Virya (potency) is physiologically and therapeutically linked to the morphological part of the plant used (e.g., fruit vs root). The reconciliation logic enforces the following comparison matrix:

| Part Configuration | Eligibility | Tier Placement | Rationale |
| :--- | :--- | :--- | :--- |
| **Same Specified Part** (`p1.part = p2.part`) | Eligible | **Tier 3** (if exact & verified) | Direct comparable observation; true source disagreement. |
| **Both Unspecified** (`p1.part IS NULL AND p2.part IS NULL`) | Eligible | **Tier 3** (if exact & verified) | General/whole-herb attribution divergence. |
| **One Specified, One Unspecified** (`p1 IS NULL XOR p2 IS NULL`) | Eligible | **Tier 2** (Never Tier 3) | Morphological approximation gap; not confirmed conflict. |
| **Different Specified Parts** (`p1.part != p2.part`) | **Ineligible** | **Excluded from all tiers** | Different anatomical parts naturally possess different Virya. |

### SQL Filter Implementation:
1. **Common Exclusion Filter** across all candidate generation:
   ```sql
   AND NOT (p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NOT NULL AND p1.part_concept_id != p2.part_concept_id)
   ```
2. **Tier 2 Complement:**
   ```sql
   OR ((p1.part_concept_id IS NULL AND p2.part_concept_id IS NOT NULL)
       OR (p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NULL))
   ```
3. **Tier 3 Strict Part Scope:**
   ```sql
   AND (p1.part_concept_id IS p2.part_concept_id)
   ```

---

## Virya Reconciliation Tiers & Mutual Exclusivity

The three reconciliation queries are mutually exclusive:

| Tier | Name | Defining Criteria | Exclusions |
| :---: | :--- | :--- | :--- |
| **1** | Unreviewed Candidate Divergence | At least one mapping OR source claim has `verification_status = 'unreviewed'`. | Rejected/superseded claims/mappings; partial/disputed mapping types; different specified parts. |
| **2** | Reviewed Candidate Divergence | All claims and mappings are `reviewed` or `verified`. At least one mapping is `broader`/`narrower`, OR exactly one part is unspecified, OR mappings are exact but intra-source or cross-source reviewed (not verified). | Any unreviewed claim or mapping; rejected/superseded mappings; partial/disputed types. |
| **3** | Verified Source Disagreement | Both mappings are `verified` AND `exact`. Both source claims are `reviewed` or `verified`. Distinct sources (`s1.source_id != s2.source_id`). Parts identical or both unspecified (`p1.part_concept_id IS p2.part_concept_id`). | Any unreviewed claim/mapping; broader/narrower mappings; mismatched parts; same source authority. |

---

## Query 4: Same Source Claim Mapping Ambiguity Audit (Conservative Same-Herb & Identical Plant-Part Rule)

Query 4 detects lexical mapping ambiguities where a single underlying source claim has been mapped to multiple conflicting Virya concepts.

### Conservative Same-Herb & Identical Plant-Part Rule:
1. In Stage B, `UNIQUE(source, source_record_id)` exists on `herbs`. Each source record corresponds to exactly one herb record.
2. In Stage C, the trigger `trg_validate_herb_prop_mapping_insert` enforces that any mapped property attached to an herb must share that herb's exact `source_record_id`.
3. Consequently, valid data model semantics dictate that two property records sharing the exact same `source_claim_id` belong to the same source record, and therefore must belong to the **same herb record** (`h1.id = h2.id`).
4. **Identical Plant-Part Scope Requirement (`p1.part_concept_id IS p2.part_concept_id`):** A single source claim could legitimately record distinct Virya attributes for different anatomical plant parts (e.g. root vs leaf). To prevent reporting false ambiguity across distinct parts, Query 4 strictly requires identical plant-part scope:
   ```sql
   WHERE h1.id = h2.id
     AND m1.source_claim_id = m2.source_claim_id
     AND (p1.part_concept_id IS p2.part_concept_id)
     AND c1.concept_domain = 'virya' AND c2.concept_domain = 'virya'
     AND c1.concept_id != c2.concept_id
     AND p1.source_presence_status = 'active'
     AND p2.source_presence_status = 'active'
     AND sc1.verification_status IN ('unreviewed', 'reviewed', 'verified')
     AND m1.verification_status IN ('unreviewed', 'reviewed', 'verified')
     AND m2.verification_status IN ('unreviewed', 'reviewed', 'verified')
     AND m1.mapping_type IN ('exact', 'broader', 'narrower')
     AND m2.mapping_type IN ('exact', 'broader', 'narrower');
   ```

### Output Projection:
Query 4 projects unambiguous, transparent columns:
- `herb_id`: ID of the herb record.
- `botanical_identity`: Botanical name or English name of the herb.
- `herb_name`: English name of the herb.
- `identity_basis`: Constant `'same_herb_record'`.
- `source_record_id`: ID of the provenance source record.
- `source`: Key of the source authority.
- `source_claim_id`: ID of the shared underlying source claim.
- `source_field`: Field of the claim (`'virya'`).
- `raw_claim`: Raw source expression text.
- `claim_verification_status`: Status of the source claim.
- `part_1_id`: Plant part concept ID for property 1 (or NULL if unspecified).
- `part_2_id`: Plant part concept ID for property 2 (or NULL if unspecified).
- `mapping_1_id`: ID of the first concept mapping.
- `virya_1`: Normalized Virya concept for mapping 1 (e.g. `'virya.ushna'`).
- `mapping_1_status`: Verification status of mapping 1.
- `mapping_1_type`: Mapping type of mapping 1.
- `mapping_2_id`: ID of the second concept mapping.
- `virya_2`: Normalized Virya concept for mapping 2 (e.g. `'virya.sheeta'`).
- `mapping_2_status`: Verification status of mapping 2.
- `mapping_2_type`: Mapping type of mapping 2.
- `audit_category`: Constant `'HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY'`.

---

## Verification Test Results

Executing `test_stage_c_comprehensive.py` confirms 100% compliance across all 6 test suites:
- **Suite 1:** Stage B Schema Compatibility & Exact Column Verification.
- **Suite 2:** Complete Mutation & Deletion Integrity Matrix (validating FKs, triggers, source-claim assertion immutability, and partial unique indexes for nullable composite uniqueness).
- **Suite 3:** Comprehensive Virya Reconciliation Dataset (15 scenarios covering mutual exclusivity, plant-part matrix, intra/cross-source exact divergence, and the full 8x3 identity & taxonomic provenance regression matrix).
- **Suite 4:** Reconciliation Metric Count Queries.
- **Suite 5:** Repeatable Benchmark Evaluation (measuring trigger overhead across 5 runs of 1,000 rows).
- **Suite 6:** Stage B Migration Upgrade & Rollback Resilience (validating atomic forward upgrade to Version 3, incomplete statement detection, unreserved connection safety, transactional version prerequisite validation under write lock for forward and rollback, two-connection write-lock acquisition and serialization under contention, mid-execution failure trace & rollback atomicity with temporary DDL file, clean rollback to Version 2 with 100% data preservation, and idempotent re-application).

Executing `tests/test_stage_c_migration.py` via pytest validates all 23 Stage C requirements:
- `test_01_all_stage_c_table_creation`: PASSED (all 11 tables and 2 reporting views created; exact object sets verified with zero extraneous or missing tables/views).
- `test_02_foreign_key_integrity`: PASSED (foreign key cascades and restrictions enforced).
- `test_03_concept_hierarchy_cycle_prevention`: PASSED (self-parenting and recursive cycle prevented).
- `test_04_parent_child_domain_consistency`: PASSED (cross-domain parentage blocked).
- `test_05_concept_domain_restrictions`: PASSED (domain check constraints enforced).
- `test_06_cross_herb_contamination_prevention`: PASSED (cross-herb mapping assignment blocked).
- `test_07_dosha_composite_pairing_integrity`: PASSED (dosha and dosha_effect domain validation enforced).
- `test_08_label_verification_requirements`: PASSED (machine-generated origin rejected, citation required).
- `test_09_citation_deletion_and_modification_safeguards`: PASSED (last citation deletion blocked).
- `test_10_source_presence_status_validation`: PASSED (active, candidate_omission, confirmed_omission validated).
- `test_11_source_reconciliation_event_integrity`: PASSED (incomplete extraction blocked from complete snapshot).
- `test_12_historical_claim_preservation`: PASSED (source-claim assertion immutability: explicitly tests all 6 protected fields—source_record_id, claim_type, source_field, source_expression, language_code, normalization_method—blocked on mapped claims; supersession workflow permitted; historical claims preserved).
- `test_13_failed_migration_rollback`: PASSED (mid-execution failure atomicity: temporary DDL file with valid DDL + invalid SQL; SQLite trace callback verifies valid statement execution before error; rolls back cleanly, maintains version 2, no version 3 row, Stage B data preserved, connection unreserved).
- `test_14_successful_migration`: PASSED (schema version 2 -> 3 recorded in ledger with dynamically generated UTC ISO-8601 execution timestamp).
- `test_15_rollback_and_reapplication`: PASSED (idempotent rollback and re-migration verified).
- `test_16_stage_b_data_preservation`: PASSED (100% preservation across all 13 Stage B legacy tables via deterministic table-level dictionary snapshots through forward migration, rollback, and re-application).
- `test_17_nullable_composite_uniqueness`: PASSED (partial unique indexes enforce uniqueness when part is NULL for properties and preparations; different specified parts remain valid; duplicate specified parts rejected).
- `test_18_source_claim_immutability_via_dosha_assertion`: PASSED (separate test case verifying that all 6 assertion-defining fields are protected when referenced solely by dosha_claim_assertions without concept mappings; status updates, supersession, and historical audit preserved).
- `test_19_forward_migration_prerequisite_validation`: PASSED (validates that forward migration prerequisite version check evaluates under BEGIN IMMEDIATE write lock, rejects databases at version != 2, cleanly rolls back, and leaves connection unreserved).
- `test_20_rollback_migration_prerequisite_validation`: PASSED (validates that rollback migration prerequisite version check evaluates under BEGIN IMMEDIATE write lock, rejects databases at version != 3, cleanly rolls back, and leaves connection unreserved).
- `test_21_two_connection_version_check_under_write_lock`: PASSED (genuinely verifies SQLite write-lock acquisition and serialization: connection 1 acquires BEGIN IMMEDIATE and retains write lock; connection 2 attempts BEGIN IMMEDIATE and apply_migration, failing with OperationalError 'database is locked' within 50ms busy timeout; connection 1 rolls back; connection 2 subsequently acquires lock and reads MAX(version) == 2 under write lock; both connections closed cleanly).
- `test_22_sequential_migration_rejection_on_upgraded_database`: PASSED (verifies sequential migration prerequisite rejection: connection 1 applies Migration 3 to reach version 3; connection 2 attempts forward migration under write lock and is rejected with expected version 2, got 3; connection 1 rolls back to version 2; connection 2 attempts rollback under write lock and is rejected with expected version 3, got 2).
- `test_23_concurrent_thread_write_lock_serialization`: PASSED (verifies actual multi-threaded write-lock serialization: two synchronized worker threads using threading.Event demonstrate lock contention without arbitrary sleeps; worker 1 holds BEGIN IMMEDIATE, worker 2 is blocked with OperationalError 'database is locked' on 50ms busy timeout; worker 1 releases write lock; worker 2 acquires lock, verifies schema version 2, and releases; zero thread hangs or timeouts).
