# Architecture Decision Record: Stage C.2 Architecture, Ingestion Lifecycle, and Repository Specification (Revision 9)

| Metadata | Details |
| :--- | :--- |
| **Status** | Accepted / Signed Off (WP-0 Complete) |
| **Date** | 2026-11-19 |
| **Scope** | Stage C.2 Work Package 0 (WP-0) Schema-First Architectural Baseline (Revision 9) |
| **Target Schema Version** | Version 3 (`migration_0003_semantic_dravyaguna.py`) |
| **Active Production Baseline** | Version 2 (`AyurvedicDB.db` / `data/inspection.db`) |
| **Approved Baseline Artifacts** | `stage_c_ddl_and_triggers.sql`, `virya_reconciliation.sql`, `migration_0003_semantic_dravyaguna.py`, 23 Migration Tests |

---

## 1. Context and Problem Statement

The Herbal Almanac repository successfully completed Stage B operational provenance integration, establishing source-tracking tables (`sources`, `source_records`, `source_claims`, `legacy_herb_map`, `herb_names`, `herb_taxa`) operating at schema version 2.

Stage C.1 established the normalized Dravyaguna relational model across 11 core tables, 44 triggers, 2 reporting views, and a 23-test migration verification suite. Stage C.1 received formal independent review sign-off.

Before implementing Stage C.2 (ingestion pipelines, catalog population, and query services), Work Package 0 (WP-0) mandates an explicit, schema-first Architecture Decision Record (ADR) that:
1. Accurately describes what Stage C.1 actually enforces through DDL constraints, partial unique indexes, and triggers versus what must be enforced by the future Python application layer.
2. Maps concept-code namespaces and domain validation boundaries across all 11 accepted domains.
3. Completely decouples concept lifecycle (`dravyaguna_concepts.status`) from label verification (`concept_labels.verification_status`).
4. Details localization and Sanskrit reference resolution with unified ranking order.
5. Retains `mapping_confidence = NULL` for exact lexical matches.
6. Establishes dual-pathway claim lifecycle enforcement: routine pipelines enforce forward transitions and same-status idempotency, while administrative adjudication handles curator downgrades and terminal claim revisions with mandatory caller-authentication preconditions, non-destructive note appending, and audit logging.
7. Resolves cascading trigger hazards: defines a deterministic lineage tag (`[INHERITED_FROM_CLAIM:{claim_id}:PRIOR={prior_status}]`) and protocol that pre-captures child states, restores independently terminal child mappings post-trigger, cascades non-terminal Dosha assertions, and selectively reopens only inherited children without auto-promoting unreviewed children.
8. Defines section-level completeness contracts for omission detection, recognizing that database events track source-level completeness only, and embeds entity traceability tags (`[CLAIM_ID: ...]`, `[HERB_ID: ...]`) within event notes.
9. Provides exact, verified TypedDict contracts and SQL mapping specifications for the active profile API (including explicit `mapping_type != 'disputed'` filtering and derived `is_disputed` projection) and all four queries in `virya_reconciliation.sql`.
10. Explicitly identifies unresolved taxonomic and architectural design decisions (including the classical *Mridu* vs. *Manda* variant in Ashta-Virya) rather than silently making arbitrary assumptions.

---

## 2. Decision 1: Concept Identifier Namespace & Domain Mapping

All canonical concepts in `dravyaguna_concepts` must adhere to a standardized identifier syntax.

### A. Database-Enforced DDL Constraints
In `stage_c_ddl_and_triggers.sql`, the database enforces:
1. **Uniqueness:** `concept_code TEXT NOT NULL UNIQUE`.
2. **Domain Whitelist:**
   ```sql
   CHECK (concept_domain IN (
       'rasa', 'guna', 'virya', 'vipaka', 'prabhava',
       'karma', 'dosha', 'dosha_effect', 'plant_part',
       'preparation_form', 'indication'
   ))
   ```
3. **Parent Domain Invariance:** Triggers `trg_validate_concept_parent_domain_insert` and `trg_validate_concept_parent_domain_update` verify that when `parent_concept_id IS NOT NULL`, the parent record shares the identical `concept_domain`.
4. **Hierarchy Cycle Prevention:** Trigger `trg_prevent_concept_cycle_update` prevents circular parent-child relationships via recursive CTE checking.

*Database Boundary Distinction:* The Stage C.1 DDL does **not** enforce text-prefix alignment on `concept_code`, nor does it enforce any regular expression constraint on concept identifiers.

### B. Application-Level Invariant (WP-1 Scope)
The application layer (specifically Work Package 1) must enforce concept-code formatting and prefix-to-domain alignment through a dedicated Python validator (`validate_concept_code_prefix`):
- **Proposed Identifier Format:** `<DOMAIN_PREFIX>_<CANONICAL_TOKEN>` (uppercase ASCII tokens separated by an underscore).
- **Proposed Identifier Regex:** `^[A-Z]+_[A-Z0-9_]+$`
- **Namespace-to-Domain Mapping:**

| Domain Prefix | Concept Domain | Classical / Pharmacopoeial Scope | Representative Seed Identifiers |
| :--- | :--- | :--- | :--- |
| `RASA_*` | `rasa` | Gustatory taste (6 classical Rasas) | `RASA_MADHURA`, `RASA_TIKTA`, `RASA_KASHAYA` |
| `GUNA_*` | `guna` | Pharmacological attributes (20 Gurvadi + 10 Paradi) | `GUNA_GURU`, `GUNA_LAGHU`, `GUNA_SNIGDHA` |
| `VIRYA_*` | `virya` | Potency (2 primary + 8-fold classical) | `VIRYA_USHNA`, `VIRYA_SHITA` |
| `VIPAKA_*` | `vipaka` | Post-digestive metabolic transformation (3 classical) | `VIPAKA_MADHURA`, `VIPAKA_AMLA`, `VIPAKA_KATU` |
| `PRABHAVA_*` | `prabhava` | Specific pharmacological action beyond Guna/Virya | `PRABHAVA_VISHAGHNA`, `PRABHAVA_MEDHYA` |
| `KARMA_*` | `karma` | General therapeutic action category | `KARMA_DEEPANA`, `KARMA_PACHANA`, `KARMA_ANULOMANA` |
| `DOSHA_*` | `dosha` | Three biological humors (Tridosha) | `DOSHA_VATA`, `DOSHA_PITTA`, `DOSHA_KAPHA` |
| `EFFECT_*` | `dosha_effect` | Directional impact on Doshas | `EFFECT_DECREASE`, `EFFECT_INCREASE` |
| `PART_*` | `plant_part` | Morphological plant parts (API Part 1) | `PART_ROOT`, `PART_STEM_BARK`, `PART_LEAF`, `PART_FRUIT` |
| `PREP_*` | `preparation_form` | Pharmaceutical dosage forms (AFI / Sharngadhara) | `PREP_CHURNA`, `PREP_KWATHA`, `PREP_SWARASA`, `PREP_TAILA` |
| `IND_*` | `indication` | Classical disease and clinical indications | `IND_JVARA`, `IND_KASA`, `IND_SHWASA`, `IND_PRAMEHA` |

---

## 3. Decision 2: Disentangling Concept Lifecycle from Label Verification

Concept lifecycle and label verification represent orthogonal concerns and are strictly isolated across separate tables.

### A. Concept Lifecycle Status (`dravyaguna_concepts.status`)
Enforced in `dravyaguna_concepts`: `CHECK (status IN ('active', 'deprecated', 'provisional'))`.
- `active`: Fully validated concept node eligible for automated ingestion and default public query exposure.
- `provisional`: Candidate concept under review. Quarantined from default production queries.
- `deprecated`: Retired concept node preserved for historical foreign key integrity. Ingestion into deprecated concepts is rejected.

### B. Label Verification Status (`concept_labels.verification_status`)
Enforced in `concept_labels`: `CHECK (verification_status IN ('unreviewed', 'reviewed', 'verified', 'disputed', 'rejected'))`.
- `unreviewed`: Initial state of automated or seed labels.
- `reviewed`: Human curator checked text transcription and language codes.
- `verified`: Formally verified against an authoritative treatise or pharmacopoeial citation.
- `disputed`: Conflicting translations or contentious vernacular usages flagged for curator review.
- `rejected`: Inaccurate transcription, erroneous translation, or OCR artifact.

### C. Provisional Concept Quarantine Policy
Concepts marked with `status = 'provisional'` are subject to an architectural quarantine:
1. Excluded from default API endpoints (`herb_dravyaguna_profile`).
2. Excluded from Virya cross-source reconciliation.
3. Accessible only via administrative audit endpoints with explicit `include_provisional=True`.
4. Promotion from `provisional` to `active` requires an explicit curator review transaction.

---

## 4. Decision 3: Localization, Sanskrit Reference, and Label Selection Policy

### A. Language Priority & Classical Terminology
Modern operational interfaces prioritize Hindi (`hi`) and English (`en`) for readability across diverse user groups. Classical Sanskrit terms (Devanagari and IAST) are maintained as authoritative reference fields attached to every concept.

Sanskrit representations (`canonical_sanskrit_deva` and `canonical_sanskrit_iast`) are **computed reference properties** derived from `concept_labels` at query time. They are not stored columns in `dravyaguna_concepts`.

### B. Unified Deterministic Display Label Selection Algorithm
When resolving `display_label` for an active concept (`dravyaguna_concepts.status = 'active'`):

1. **Candidate Scope Gate:**
   - Consider only labels for active concepts (`dravyaguna_concepts.status = 'active'`).
   - Exclude labels with `verification_status IN ('disputed', 'rejected')`.
2. **Language Priority Sequence:**
   - **If requested language is `hi` (Hindi):**
     - Rank 1: `language_code = 'hi'`
     - Rank 2: `language_code = 'en'`
     - Rank 3: `language_code = 'sa'` AND `script_code = 'Deva'`
     - Rank 4: `language_code = 'sa'` AND `script_code = 'Latn'`
   - **If requested language is `en` (English, default):**
     - Rank 1: `language_code = 'en'`
     - Rank 2: `language_code = 'hi'`
     - Rank 3: `language_code = 'sa'` AND `script_code = 'Deva'`
     - Rank 4: `language_code = 'sa'` AND `script_code = 'Latn'`
3. **Intra-Language Candidate Ranking:**
   Within the highest matching language rank, sort candidates deterministically:
   - Priority 1: `verification_status` priority (`'verified'` > `'reviewed'` > `'unreviewed'`).
   - Priority 2: Preference flag (`is_preferred DESC`: `1` before `0`).
   - Priority 3: Lowest `concept_label_id ASC` (oldest record).
4. **Fallback:** If no eligible labels exist across all ranks, return `concept_code` with `display_label_status = 'unreviewed'`.
5. **Output Transparency:** Return selected `label_text` and its actual `verification_status` (projected as `display_label_status`).

### C. Independent Sanskrit Reference Field Resolution
The computed reference properties `canonical_sanskrit_deva` and `canonical_sanskrit_iast` are resolved independently from the interface display label, using the **identical ranking ordering** (verification status over preference) and strictly excluding both `disputed` and `rejected` labels:
- **`canonical_sanskrit_deva`:**
  ```sql
  SELECT label_text FROM concept_labels
  WHERE concept_id = :concept_id
    AND language_code = 'sa'
    AND script_code = 'Deva'
    AND verification_status NOT IN ('disputed', 'rejected')
  ORDER BY CASE verification_status WHEN 'verified' THEN 1 WHEN 'reviewed' THEN 2 ELSE 3 END,
           is_preferred DESC,
           concept_label_id ASC
  LIMIT 1;
  ```
- **`canonical_sanskrit_iast`:**
  ```sql
  SELECT label_text FROM concept_labels
  WHERE concept_id = :concept_id
    AND language_code = 'sa'
    AND script_code = 'Latn'
    AND verification_status NOT IN ('disputed', 'rejected')
  ORDER BY CASE verification_status WHEN 'verified' THEN 1 WHEN 'reviewed' THEN 2 ELSE 3 END,
           is_preferred DESC,
           concept_label_id ASC
  LIMIT 1;
  ```

---

## 5. Decision 4: Calibrated Mapping Confidence Policy

In accordance with data-integrity guidelines, mapping confidence describes empirical mathematical calibration and remains strictly nullable:

1. **Backfill & Exact Lexical Matching:**
   Automated backfill and ruleset mappings (`mapping_method = 'lexicon_exact'`) must record:
   ```sql
   mapping_confidence = NULL
   ```
   *Rationale:* Exact string matching between an OCR/source string and a catalog label does not guarantee pharmacological semantic equivalence without expert human validation. Storing an arbitrary `1.0` is strictly prohibited.
2. **Empirical Numerical Confidence:**
   Numerical confidence values (`0.0 <= mapping_confidence <= 1.0`) are reserved exclusively for validated probabilistic, vector-similarity, or calibrated fuzzy-match algorithms documented in the repository.
3. **Audit Tracking:** The exact operational provenance is tracked via `mapping_method = 'lexicon_exact'` and `verification_status = 'unreviewed'`.

---

## 6. Decision 5: Active Reporting & Decoupled Status Matrices

### A. Stage C.1 SQL Views Invariant
The accepted Stage C.1 reporting views (`v_active_herb_dravyaguna_properties` and `v_active_herb_dosha_effects`) filter strictly on relationship presence:
```sql
WHERE p.source_presence_status = 'active';
```
These views expose `m.verification_status AS mapping_status` and `sc.verification_status AS claim_status`. They do not filter out superseded or rejected claims.

### B. Repository Query Layer Dual-Layer Filtering
The repository query layer (`herb_dravyaguna_profile`) enforces clinical and semantic validity by applying dual-layer filtering:
```sql
WHERE p.source_presence_status = 'active'
  AND sc.verification_status NOT IN ('superseded', 'rejected')
  AND m.verification_status NOT IN ('superseded', 'rejected')
  AND c.status = 'active'
```
*(and `a.verification_status NOT IN ('superseded', 'rejected')` for Dosha assertions).*

### C. Visibility Principle: Visible Does Not Mean Clinically Verified
The Herbal Almanac organizes traditional historical assertions; it does not vouch for modern clinical efficacy:
- `unreviewed`: Displayed as unverified traditional source information.
- `reviewed`: Displayed as curator-transcribed traditional source information.
- `verified`: Displayed as verified classical textual or pharmacopoeial information backed by classical treatise citations.
- `rejected`, `superseded`: Strictly excluded from active clinical profiles.

### D. Four Decoupled Status Matrices

#### 1. Claim, Mapping, and Dosha Assertion Status (`verification_status`)
Enforced in `source_claims`, `concept_claim_mappings`, and `dosha_claim_assertions`:
`CHECK (verification_status IN ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded'))`

| Status | Semantic Meaning | Active Profile API | Virya Reconciliation | Audit API |
| :--- | :--- | :---: | :---: | :---: |
| `unreviewed` | Initial machine/ruleset mapping | Visible (flagged unreviewed) | Tier 1 (Unreviewed) | Visible |
| `reviewed` | Human curator confirmed transcription | Visible (flagged reviewed) | Tier 2 (Reviewed) | Visible |
| `verified` | Expert verified with authority citation | Visible (flagged verified) | Tier 3 (Verified) | Visible |
| `rejected` | Corrupted text, OCR error, invalid assertion | **Excluded** | **Excluded** | Visible |
| `superseded` | Replaced by newer source snapshot claim | **Excluded** | **Excluded** | Visible |

*(Note: `disputed` is NOT a valid `verification_status` for claims, mappings, or assertions in the Stage C.1 DDL. It exists only as a `mapping_type` in `concept_claim_mappings.mapping_type`.)*

#### 2. Concept Label Verification Status (`concept_labels.verification_status`)
Enforced in `concept_labels`:
`CHECK (verification_status IN ('unreviewed', 'reviewed', 'verified', 'disputed', 'rejected'))`

| Status | Semantic Meaning | Display Candidate Pool | Curation Flag |
| :--- | :--- | :---: | :---: |
| `unreviewed` | Seed or machine-generated label | Eligible (Priority 3) | Pending review |
| `reviewed` | Curator reviewed language and text | Eligible (Priority 2) | Reviewed |
| `verified` | Authenticated against Samhita or Pharmacopoeia | Eligible (Priority 1) | Fully verified |
| `disputed` | Contentious vernacular usage or debated translation | **Excluded** | Under review |
| `rejected` | Erroneous transcription or incorrect translation | **Excluded** | Discarded |

#### 3. Domain Relationship Presence Status (`source_presence_status`)
Enforced across all 5 relationship tables (`herb_dravyaguna_properties`, `herb_dosha_effects`, `herb_plant_parts`, `herb_preparations`, `herb_indications`):
`CHECK (source_presence_status IN ('active', 'candidate_omission', 'confirmed_omission'))`

| Status | Semantic Meaning | Active Profile API | Virya Reconciliation | Omission Audit |
| :--- | :--- | :---: | :---: | :---: |
| `active` | Currently attested in source record | Visible | Eligible | Excluded |
| `candidate_omission` | Missing in latest complete snapshot | **Excluded** | Excluded | Flagged |
| `confirmed_omission` | Curator confirmed intentional omission | **Excluded** | Excluded | Confirmed |

*(Note: `source_presence_status` permits only `'active'`, `'candidate_omission'`, and `'confirmed_omission'`. Values such as `superseded` or `disputed` violate the CHECK constraint and must never be assigned.)*

#### 4. Concept Lifecycle Status (`dravyaguna_concepts.status`)
Enforced in `dravyaguna_concepts`:
`CHECK (status IN ('active', 'deprecated', 'provisional'))`

| Status | Semantic Meaning | Public Profile Resolution | Ingestion Target |
| :--- | :--- | :---: | :---: |
| `active` | Established pharmacological concept | Primary | Allowed |
| `provisional` | Candidate concept under review | **Excluded** (quarantined) | Allowed (quarantined) |
| `deprecated` | Retired concept node | Excluded | Blocked |

---

## 7. Decision 6: Claim, Assertion & Relationship Lifecycle Specification

### A. State Transition Policy: Dual-Pathway Enforcement

The lifecycle of `source_claims.verification_status` is governed by two strictly delineated operational pathways:
1. **Routine Pipeline Pathway (`transition_claim_status`)**: Enforces ordinary forward progression, automated retirement, and same-status idempotency. Strictly rejects curator downgrades and terminal state modifications.
2. **Administrative Adjudication Pathway (`adjudicate_claim_status_override`)**: Enforces exceptional curator interventions (status rollbacks, terminal claim reopening, and terminal reclassifications) requiring verified authorization, non-empty justification, explicit authority citations when transitioning to `verified`, non-destructive notes, and mandatory audit logging.

| Current Status | Target Status | Pathway | Conditions & Architectural Enforcement |
| :--- | :--- | :---: | :--- |
| `unreviewed` | `reviewed` | **Routine** | Requires non-empty `reviewed_by` and valid UTC ISO-8601 timestamp. |
| `unreviewed` | `verified` | **Routine** | Requires non-empty `reviewed_by`, valid UTC ISO-8601 timestamp, and explicit `authority_citation`. Logs audit event. |
| `unreviewed` | `superseded` | **Routine** | Pre-captures child states, triggers mapping cascade, restores independently terminal children, tags inheriting children, and logs audit event. |
| `unreviewed` | `rejected` | **Routine** | Pre-captures child states, triggers mapping cascade, restores independently terminal children, tags inheriting children, and logs audit event. |
| `reviewed` | `verified` | **Routine** | Promotion upon authority verification; requires `reviewed_by`, UTC ISO-8601 timestamp, and `authority_citation`. Logs audit event. |
| `reviewed` | `superseded` | **Routine** | Terminal transition; full pre-capture, cascade, restoration, and audit logging. |
| `reviewed` | `rejected` | **Routine** | Terminal transition; full pre-capture, cascade, restoration, and audit logging. |
| `reviewed` | `unreviewed` | **Admin Override** | **Curator downgrade.** Rejected by routine helper. Requires authenticated curator identity, explicit reason, and logs reconciliation event. |
| `verified` | `superseded` | **Routine** | Terminal transition if source transcription error found. Full cascade and audit logging. |
| `verified` | `rejected` | **Routine** | Terminal transition if assertion is invalid. Full cascade and audit logging. |
| `verified` | `reviewed` | **Admin Override** | **Curator downgrade.** Rejected by routine helper. Requires authenticated curator identity, explicit reason, and logs reconciliation event. |
| `verified` | `unreviewed` | **Admin Override** | **Curator downgrade.** Rejected by routine helper. Requires authenticated curator identity, explicit reason, and logs reconciliation event. |
| `superseded` | `unreviewed`, `reviewed` | **Admin Override** | **Terminal reopening.** Resynchronizes only inheriting child mappings/assertions per deterministic lineage tags; leaves independently terminal children untouched; logs reconciliation event. |
| `superseded` | `verified` | **Admin Override** | **Terminal reopening.** Requires explicit `authority_citation`, resynchronizes inheriting children (restoring to `reviewed`, never auto-verified), leaves independently terminal children untouched; logs reconciliation event. |
| `rejected` | `unreviewed`, `reviewed` | **Admin Override** | **Terminal reopening.** Resynchronizes only inheriting child mappings/assertions per deterministic lineage tags; leaves independently terminal children untouched; logs reconciliation event. |
| `rejected` | `verified` | **Admin Override** | **Terminal reopening.** Requires explicit `authority_citation`, resynchronizes inheriting children (restoring to `reviewed`, never auto-verified), leaves independently terminal children untouched; logs reconciliation event. |
| `superseded` | `rejected` (or vice versa) | **Admin Override** | **Terminal reclassification.** Requires administrative adjudication; pre-captures and preserves independently terminal children; logs reconciliation event. Rejected by routine helper. |
| *Any status* | *Same status* (`X -> X`) | **Routine / Admin** | **Idempotent no-op.** Returns immediately without updating timestamps, notes, or child records. |

---

### B. Exact DDL Trigger Coverage vs Application-Level Guarantees

#### 1. Mapping Protection (`trg_protect_claim_mapping_mutation`)
- **DDL Enforcement:** Trigger intercepts `BEFORE UPDATE OF source_claim_id, concept_id ON concept_claim_mappings`. If the mapping is currently referenced by `herb_dravyaguna_properties`, `herb_plant_parts`, `herb_preparations`, or `herb_indications`, it aborts with an integrity error.
- **Application Boundary:**
  - It does **not** protect `mapping_type` at the database level.
  - It does **not** protect mappings that are not currently referenced by herb relationship tables.
  - Universal immutability of mapping attributes must be enforced by the application layer.

#### 2. Dosha Assertion Protection (`trg_protect_dosha_assertion_mutation`)
- **DDL Enforcement:** Intercepts `BEFORE UPDATE OF source_claim_id, dosha_concept_id, effect_concept_id ON dosha_claim_assertions` when referenced by `herb_dosha_effects`.
- **Application Boundary:** The accepted DDL does not contain columns named `plant_part_concept_id` or `is_negated`. The database protects only `source_claim_id`, `dosha_concept_id`, and `effect_concept_id`.

#### 3. Source Claim Protection (`trg_protect_source_claim_mutation`)
- **DDL Enforcement:** Intercepts `BEFORE UPDATE` of assertion-defining columns (`source_record_id`, `claim_type`, `source_field`, `source_expression`, `language_code`, `normalization_method`) on `source_claims` when referenced by any `concept_claim_mappings` or `dosha_claim_assertions`.
- **Application Boundary:** The database allows in-place mutation of unreferenced claims; the application layer enforces that even unreferenced claims follow supersession workflows once published.

#### 4. Mapping Cascade (`trg_cascade_claim_supersession`) and Trigger-Order Hazards
- **DDL Enforcement:**
  ```sql
  CREATE TRIGGER IF NOT EXISTS trg_cascade_claim_supersession
  AFTER UPDATE OF verification_status ON source_claims
  FOR EACH ROW
  WHEN NEW.verification_status IN ('superseded', 'rejected')
  BEGIN
      UPDATE concept_claim_mappings 
      SET verification_status = NEW.verification_status
      WHERE source_claim_id = NEW.source_claim_id;
  END;
  ```
- **Hazard Analysis:** This trigger unconditionally sets `verification_status = NEW.verification_status` on **every** mapping attached to `source_claim_id`. It does **not** check whether a child mapping was already independently rejected or superseded, nor does it cascade to `dosha_claim_assertions`.
- **Deterministic Child Lineage Tag Format:**
  To distinguish an independently terminal child from a child that inherited a terminal status from its parent claim, the system defines a standard tag embedded in `reviewer_notes`:
  ```text
  [INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR={prior_non_terminal_status}]
  ```
- **Mandatory Trigger-Order & Child-Status Preservation Protocol:**
  Because the trigger will blindly overwrite all child mappings, both routine (`transition_claim_status`) and administrative (`adjudicate_claim_status_override`) helpers must execute this exact sequence inside an active write transaction (`BEGIN IMMEDIATE`):
  1. **Pre-Transition Capture & Partitioning:**
     Query all child rows in `concept_claim_mappings` (`mapping_id, verification_status, reviewer_notes`) and `dosha_claim_assertions` (`dosha_assertion_id, verification_status, reviewer_notes`) for `source_claim_id`.
     - **Independently terminal children:** Rows where `verification_status IN ('rejected', 'superseded')` AND `reviewer_notes` does **not** start with `[INHERITED_FROM_CLAIM:{source_claim_id}:`.
     - **Inheriting children:** Rows where `verification_status IN ('unreviewed', 'reviewed', 'verified')`, OR rows that already carry an `[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=...]` tag (preserving their original prior status).
  2. **Execute Parent Update:** Update `source_claims.verification_status = new_status` (which fires `trg_cascade_claim_supersession`).
  3. **Post-Trigger Mapping Restoration & Tagging:**
     - For every **independently terminal mapping**: explicitly restore its original `verification_status` (in case the trigger changed `'rejected'` to `'superseded'` or vice versa) and leave its `reviewer_notes` untouched.
     - For every **inheriting mapping**: ensure `verification_status = new_status` and ensure its `reviewer_notes` is prefixed with `[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR={prior_non_terminal_status}] `.
  4. **Application-Level Dosha Cascade & Tagging:**
     - For every **inheriting Dosha assertion**: update `verification_status = new_status` and prefix `reviewer_notes` with `[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR={prior_non_terminal_status}] `, recording `reviewed_by` and `reviewed_at`.
     - For every **independently terminal Dosha assertion**: leave completely untouched.
  5. **Audit Logging:** Record the transition lineage in `source_reconciliation_events.notes`.

#### 5. Review Metadata Trigger Coverage
- **DDL Enforcement:** Triggers `trg_validate_source_claim_review_metadata_insert` and `trg_validate_source_claim_review_metadata_update` enforce that `source_claims` must have non-empty `reviewed_by` and `reviewed_at` when `verification_status IN ('reviewed', 'verified')`.
- **Application Boundary:** The accepted DDL contains **no review-metadata enforcement triggers** for `concept_claim_mappings` or `dosha_claim_assertions`. While those tables possess `reviewed_by`, `reviewed_at`, and `reviewer_notes` columns, validating their presence on child reviews is strictly an application-level contract.

---

### C. Reconciliation Event Ledger Scope & Guarantees

#### 1. Database-Enforced Event Constraints
In `stage_c_ddl_and_triggers.sql`, `source_reconciliation_events` enforces:
1. `event_type IN ('ingest_batch', 'snapshot_reconciliation', 'manual_adjudication', 'omission_detection')`.
2. `extraction_status IN ('in_progress', 'completed', 'partial_failed', 'failed', 'aborted')`.
3. Snapshot integrity triggers (`trg_protect_reconciliation_snapshot_integrity_insert/update`) ensuring `is_complete_snapshot = 1` requires `extraction_status = 'completed'`.

#### 2. Schema Boundaries & Nonexistent Columns
The accepted `source_reconciliation_events` table:
- **Contains:** `event_id`, `source_id`, `event_type`, `snapshot_timestamp`, `extraction_status`, `is_complete_snapshot`, `claims_evaluated`, `properties_reconciled`, `omissions_flagged`, `initiated_by`, `completed_at`, `notes`, `created_at`.
- **Does NOT contain:** `herb_id`, `source_claim_id`, `event_status`, `performed_by`, or `performed_at`.
- **Allowed event types:** Only the 4 listed above. Event types such as `reappearance_conflict`, `reconciliation_conflict`, or `conflict_adjudicated` violate the CHECK constraint and must never be used.

#### 3. Application-Level Traceability & Entity Tags
- **No Database Append-Only Guarantee:** The DDL does not prevent updates or deletes on `source_reconciliation_events`. Append-only immutability is an application-level policy.
- **Source Records Schema Context:** In Stage B, `source_records` stores `source_id, external_record_key, source_url, retrieved_at, published_at, content_hash, raw_artifact_ref`. It does **not** contain an `herb_id` foreign key.
- **Embedded Traceability Tags:** Because `source_reconciliation_events` is scoped strictly by `source_id`, entity-specific traceability must be embedded in `notes` using structured tags:
  - `[CLAIM_ID: {source_claim_id}]` is **always** embedded.
  - `[HERB_ID: {herb_id}]` is embedded when known from caller context or associated relationship tables (`herb_dravyaguna_properties`, `herb_dosha_effects`, `herb_names`, etc.). When unattached to an herb, `[HERB_ID: UNATTACHED]` is recorded.
- **Source ID Resolution:** The `source_id` is resolved by querying `source_records` via `source_claims.source_record_id`.

---

### D. Permanent Retention of Verification Citations

1. **Vulnerability of Reviewer Notes:** Storing an authority citation solely in `source_claims.reviewer_notes` is not a durable audit strategy, as subsequent transitions can overwrite `reviewer_notes`.
2. **Durable Retention Policy:**
   - Any verification transition (routine or administrative) must record the authority citation in the `source_reconciliation_events.notes` audit trail linked to `[CLAIM_ID: <id>]`.
   - On `source_claims.reviewer_notes`, subsequent transitions **append** rather than overwrite existing notes when previous notes are present (e.g. `<existing_notes> | <new_notes>`), preserving historical citations in place.
   - Child mapping and Dosha assertion reviews use their respective `reviewer_notes` columns for immediate rationale, but the permanent, unmodifiable transition record is stored in `source_reconciliation_events.notes`.
3. **Ontology vs Claim Citations:**
   - `concept_label_sources` is strictly for concept label lexical provenance.
   - It is **not** a general claim-verification citation table. Claim citations belong in claim review metadata and reconciliation audit logs.
4. **Validation vs Authenticity:**
   - A string-length check (`len(citation) >= 5`) validates only presence.
   - It does **not** establish bibliographic authenticity or clinical correctness. Those judgments belong to an authenticated curator or authorized upstream authority.

---

### E. Independent Review Workflow for Mappings and Dosha Assertions (Contract Specification)

Because the DDL lacks review-metadata triggers on `concept_claim_mappings` and `dosha_claim_assertions`, the application layer must implement an independent review workflow:

1. **Parent Constraint:** A child mapping or Dosha assertion cannot be transitioned to `'reviewed'` or `'verified'` if its parent `source_claims` record is `'unreviewed'`, `'rejected'`, or `'superseded'`.
2. **Reviewer Identity & Timestamp:** Caller must supply a non-empty `reviewed_by` and valid UTC ISO-8601 `reviewed_at`.
3. **Authority Citation for Child Verification:** Transitioning a child mapping or assertion to `'verified'` requires an explicit citation reference documented in its `reviewer_notes` column (e.g. `[CITATION: Bhavaprakasha Nighantu 1.42] Direct pharmacological concordance confirmed`).
4. **Audit Logging:** Child review transitions are recorded in `source_reconciliation_events.notes` under `event_type = 'manual_adjudication'`.
5. **Parent Reopening Rules for Children:**
   When an administrator reopens a terminal parent claim (`current_status in ('superseded', 'rejected')` to `new_status in ('unreviewed', 'reviewed', 'verified')`) via `adjudicate_claim_status_override()`:
   - **Independently terminal children are strictly untouched:** Any child that does not carry an `[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=...]` tag remains in its terminal status (`rejected` or `superseded`).
   - **Selective Resynchronization of Inheriting Children:** Only children whose `reviewer_notes` starts with `[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=` are resynchronized.
   - **Resolution of Target Child Status:**
     - The lineage tag prefix is stripped from `reviewer_notes`.
     - If `new_status == 'unreviewed'` or the child's recorded `prior_status == 'unreviewed'`, the child's `verification_status` is restored to `'unreviewed'`.
     - If both the child's `prior_status` and `new_status` are in `('reviewed', 'verified')`, the child's `verification_status` is restored to `'reviewed'`. **A child previously `'verified'` never automatically regains `'verified'` status without explicit child re-verification.**

---

### F. Caller-Managed Transaction Contract & Lifecycle Helper Pseudocode

The application service layer manages database transactions. Helpers must not call `commit()` independently.

```python
import re
import sqlite3
from datetime import datetime

def _validate_iso_utc_timestamp(ts: str) -> None:
    """Validate strict UTC ISO-8601 timestamp string format."""
    if not isinstance(ts, str) or not ts.strip():
        raise ValueError("Timestamp 'now' must be a non-empty ISO-8601 string")
    clean_ts = ts.strip()
    if not (clean_ts.endswith("Z") or clean_ts.endswith("+00:00")):
        raise ValueError("Timestamp must explicitly terminate with UTC offset 'Z' or '+00:00'")
    try:
        dt = datetime.fromisoformat(clean_ts.replace("Z", "+00:00"))
        if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
            raise ValueError("Timestamp must represent zero-offset UTC time")
    except Exception as exc:
        raise ValueError(f"Invalid UTC ISO-8601 timestamp '{ts}': {exc}") from exc


def _parse_inherited_tag(notes: str | None, source_claim_id: int) -> str | None:
    """Extract prior status from [INHERITED_FROM_CLAIM:{id}:PRIOR={status}] tag."""
    if not notes:
        return None
    prefix = f"[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR="
    if prefix in notes:
        m = re.search(rf'\[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=([^\]]+)\]', notes)
        if m:
            return m.group(1).strip()
    return None


def _strip_inherited_tag(notes: str | None, source_claim_id: int) -> str | None:
    """Remove inherited lineage tag from notes string."""
    if not notes:
        return None
    cleaned = re.sub(rf'\[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=[^\]]+\]\s*', '', notes)
    return cleaned.strip() or None


def transition_claim_status(
    connection: sqlite3.Connection,
    source_claim_id: int,
    new_status: str,
    now: str,
    reviewed_by: str | None = None,
    reviewer_notes: str | None = None,
    authority_citation: str | None = None,
    herb_id: int | None = None,
) -> None:
    """Atomically transition a source claim in routine ingestion and curation workflows.

    TRANSACTION CONTRACT:
    - Connection must have PRAGMA foreign_keys = ON.
    - Caller must manage transaction: execute 'BEGIN IMMEDIATE' before calling,
      and 'COMMIT' / 'ROLLBACK' upon return / exception.
    - Helper executes strictly within caller transaction; does not commit.
    """
    valid_statuses = ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded')
    if new_status not in valid_statuses:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")

    _validate_iso_utc_timestamp(now)

    # Fetch claim, parent source_id, and existing reviewer notes
    row = connection.execute(
        """
        SELECT sc.verification_status, sr.source_id, sc.reviewer_notes
        FROM source_claims sc
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        WHERE sc.source_claim_id = ?
        """,
        (source_claim_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Source claim {source_claim_id} not found")

    current_status, source_id, existing_claim_notes = row[0], row[1], row[2]

    # Same-status idempotency: return immediately before applying transition restrictions
    if current_status == new_status:
        return

    # Routine transition matrix validation
    routine_allowed: dict[str, set[str]] = {
        'unreviewed': {'reviewed', 'verified', 'superseded', 'rejected'},
        'reviewed': {'verified', 'superseded', 'rejected'},
        'verified': {'superseded', 'rejected'},
        'superseded': set(),
        'rejected': set(),
    }

    if new_status not in routine_allowed.get(current_status, set()):
        if current_status in ('superseded', 'rejected'):
            raise ValueError(
                f"Cannot transition terminal claim {source_claim_id} ({current_status}) to '{new_status}' "
                "in routine pipelines. Reopening terminal claims requires adjudicate_claim_status_override()."
            )
        if (current_status, new_status) in [
            ('reviewed', 'unreviewed'),
            ('verified', 'reviewed'),
            ('verified', 'unreviewed'),
        ]:
            raise ValueError(
                f"Status downgrade from '{current_status}' to '{new_status}' for claim {source_claim_id} "
                "is curator-only and prohibited in routine pipelines. Use adjudicate_claim_status_override()."
            )
        raise ValueError(f"Transition from '{current_status}' to '{new_status}' is not permitted.")

    if new_status in ('reviewed', 'verified'):
        if not reviewed_by or not reviewed_by.strip():
            raise ValueError(f"Transition to '{new_status}' requires a non-empty reviewed_by identifier")

    if new_status == 'verified':
        if not authority_citation or len(authority_citation.strip()) < 5:
            raise ValueError("Transition to 'verified' strictly requires an explicit authority_citation")

    # Format new notes, non-destructively appending to existing claim notes
    formatted_new_notes = reviewer_notes
    if new_status == 'verified':
        citation_header = f"[AUTHORITY CITATION: {authority_citation.strip()}]"
        formatted_new_notes = f"{citation_header} {reviewer_notes.strip()}" if reviewer_notes else citation_header

    if existing_claim_notes and formatted_new_notes:
        merged_claim_notes = f"{existing_claim_notes.strip()} | {formatted_new_notes.strip()}"
    else:
        merged_claim_notes = formatted_new_notes or existing_claim_notes

    # Terminal cascade protocol: pre-capture child statuses before trigger fires
    indep_terminal_mappings: list[tuple[int, str]] = []
    inheriting_mappings: list[tuple[int, str, str | None]] = []
    inheriting_assertions: list[tuple[int, str, str | None]] = []

    if new_status in ('superseded', 'rejected'):
        child_mappings = connection.execute(
            "SELECT mapping_id, verification_status, reviewer_notes FROM concept_claim_mappings WHERE source_claim_id = ?",
            (source_claim_id,),
        ).fetchall()
        for m_id, m_status, m_notes in child_mappings:
            existing_prior = _parse_inherited_tag(m_notes, source_claim_id)
            if m_status in ('rejected', 'superseded') and not existing_prior:
                indep_terminal_mappings.append((m_id, m_status))
            else:
                prior_status = existing_prior if existing_prior else m_status
                clean_notes = _strip_inherited_tag(m_notes, source_claim_id)
                inheriting_mappings.append((m_id, prior_status, clean_notes))

        child_assertions = connection.execute(
            "SELECT dosha_assertion_id, verification_status, reviewer_notes FROM dosha_claim_assertions WHERE source_claim_id = ?",
            (source_claim_id,),
        ).fetchall()
        for a_id, a_status, a_notes in child_assertions:
            existing_prior = _parse_inherited_tag(a_notes, source_claim_id)
            if not (a_status in ('rejected', 'superseded') and not existing_prior):
                prior_status = existing_prior if existing_prior else a_status
                clean_notes = _strip_inherited_tag(a_notes, source_claim_id)
                inheriting_assertions.append((a_id, prior_status, clean_notes))

    # Update source claim (fires trg_cascade_claim_supersession if terminal)
    cursor = connection.execute(
        """
        UPDATE source_claims
        SET verification_status = ?,
            updated_at = ?,
            reviewed_by = COALESCE(?, reviewed_by),
            reviewed_at = CASE WHEN ? IS NOT NULL THEN ? ELSE reviewed_at END,
            reviewer_notes = ?
        WHERE source_claim_id = ?
        """,
        (new_status, now, reviewed_by, reviewed_by, now, merged_claim_notes, source_claim_id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"Expected exactly 1 claim updated, got {cursor.rowcount}")

    # Post-trigger restoration and lineage tagging
    if new_status in ('superseded', 'rejected'):
        for m_id, original_status in indep_terminal_mappings:
            connection.execute(
                "UPDATE concept_claim_mappings SET verification_status = ? WHERE mapping_id = ?",
                (original_status, m_id),
            )

        tag_prefix = f"[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR="
        for m_id, prior_status, clean_notes in inheriting_mappings:
            tagged_notes = f"{tag_prefix}{prior_status}] {clean_notes}" if clean_notes else f"{tag_prefix}{prior_status}]"
            connection.execute(
                "UPDATE concept_claim_mappings SET verification_status = ?, reviewer_notes = ? WHERE mapping_id = ?",
                (new_status, tagged_notes, m_id),
            )

        for a_id, prior_status, clean_notes in inheriting_assertions:
            tagged_notes = f"{tag_prefix}{prior_status}] {clean_notes}" if clean_notes else f"{tag_prefix}{prior_status}]"
            connection.execute(
                """
                UPDATE dosha_claim_assertions
                SET verification_status = ?,
                    reviewed_by = COALESCE(?, reviewed_by),
                    reviewed_at = CASE WHEN ? IS NOT NULL THEN ? ELSE reviewed_at END,
                    reviewer_notes = ?
                WHERE dosha_assertion_id = ?
                """,
                (new_status, reviewed_by, reviewed_by, now, tagged_notes, a_id),
            )

    # Audit logging for verified and terminal transitions (cross-ref Section 14.4)
    if new_status == 'verified' or new_status in ('superseded', 'rejected'):
        herb_tag = f"[HERB_ID: {herb_id}]" if herb_id is not None else "[HERB_ID: UNATTACHED]"
        lineage_summary = ""
        if new_status in ('superseded', 'rejected'):
            lineage_summary = (
                f" Lineage: {len(indep_terminal_mappings)} indep mappings preserved; "
                f"{len(inheriting_mappings)} inheriting mappings tagged; "
                f"{len(inheriting_assertions)} inheriting assertions tagged."
            )
        audit_note = (
            f"[CLAIM_ID: {source_claim_id}] {herb_tag} [ROUTINE_TRANSITION: {current_status} -> {new_status}]"
            f"{' ' + merged_claim_notes if merged_claim_notes else ''}{lineage_summary}"
        )
        connection.execute(
            """
            INSERT INTO source_reconciliation_events (
                source_id, event_type, snapshot_timestamp, extraction_status,
                is_complete_snapshot, claims_evaluated, properties_reconciled,
                omissions_flagged, notes, initiated_by
            ) VALUES (
                ?, 'manual_adjudication', ?, 'completed',
                0, 1, 0, 0, ?, ?
            )
            """,
            (source_id, now, audit_note, reviewed_by or 'routine_pipeline'),
        )


def adjudicate_claim_status_override(
    connection: sqlite3.Connection,
    source_claim_id: int,
    new_status: str,
    now: str,
    authorized_curator_id: str,
    adjudication_reason: str,
    authority_citation: str | None = None,
    herb_id: int | None = None,
) -> None:
    """Administratively override or reopen a claim status with mandatory audit logging.

    PRECONDITION: The application service layer must authenticate the actor and confirm
    curator/admin privileges prior to calling this helper. Parameter authorized_curator_id
    records the authenticated identity for audit provenance; the helper does not authenticate.

    TRANSACTION CONTRACT: Must be executed within caller transaction (BEGIN IMMEDIATE).
    """
    valid_statuses = ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded')
    if new_status not in valid_statuses:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")

    _validate_iso_utc_timestamp(now)

    if not authorized_curator_id or not authorized_curator_id.strip():
        raise ValueError("Administrative adjudication requires a non-empty authorized_curator_id")

    if not adjudication_reason or len(adjudication_reason.strip()) < 10:
        raise ValueError("Administrative adjudication requires a substantial adjudication_reason (min 10 chars)")

    if new_status == 'verified':
        if not authority_citation or len(authority_citation.strip()) < 5:
            raise ValueError("Reopening to 'verified' strictly requires an explicit authority_citation")

    row = connection.execute(
        """
        SELECT sc.verification_status, sr.source_id, sc.reviewer_notes
        FROM source_claims sc
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        WHERE sc.source_claim_id = ?
        """,
        (source_claim_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Source claim {source_claim_id} not found")

    current_status, source_id, existing_claim_notes = row[0], row[1], row[2]
    if current_status == new_status:
        return

    admin_permitted: dict[str, set[str]] = {
        'reviewed': {'unreviewed'},
        'verified': {'reviewed', 'unreviewed'},
        'superseded': {'unreviewed', 'reviewed', 'verified', 'rejected'},
        'rejected': {'unreviewed', 'reviewed', 'verified', 'superseded'},
    }
    if new_status not in admin_permitted.get(current_status, set()):
        raise ValueError(
            f"Administrative transition from '{current_status}' to '{new_status}' is not permitted."
        )

    citation_part = f" [CITATION: {authority_citation.strip()}]" if authority_citation else ""
    formatted_override = f"[ADMIN OVERRIDE: {current_status} -> {new_status}]{citation_part} {adjudication_reason.strip()}"
    merged_claim_notes = f"{existing_claim_notes.strip()} | {formatted_override}" if existing_claim_notes else formatted_override

    # If transitioning into a terminal status via admin override, pre-capture child states
    indep_terminal_mappings: list[tuple[int, str]] = []
    inheriting_mappings: list[tuple[int, str, str | None]] = []
    inheriting_assertions: list[tuple[int, str, str | None]] = []

    if new_status in ('superseded', 'rejected'):
        child_mappings = connection.execute(
            "SELECT mapping_id, verification_status, reviewer_notes FROM concept_claim_mappings WHERE source_claim_id = ?",
            (source_claim_id,),
        ).fetchall()
        for m_id, m_status, m_notes in child_mappings:
            existing_prior = _parse_inherited_tag(m_notes, source_claim_id)
            if m_status in ('rejected', 'superseded') and not existing_prior:
                indep_terminal_mappings.append((m_id, m_status))
            else:
                prior_status = existing_prior if existing_prior else m_status
                clean_notes = _strip_inherited_tag(m_notes, source_claim_id)
                inheriting_mappings.append((m_id, prior_status, clean_notes))

        child_assertions = connection.execute(
            "SELECT dosha_assertion_id, verification_status, reviewer_notes FROM dosha_claim_assertions WHERE source_claim_id = ?",
            (source_claim_id,),
        ).fetchall()
        for a_id, a_status, a_notes in child_assertions:
            existing_prior = _parse_inherited_tag(a_notes, source_claim_id)
            if not (a_status in ('rejected', 'superseded') and not existing_prior):
                prior_status = existing_prior if existing_prior else a_status
                clean_notes = _strip_inherited_tag(a_notes, source_claim_id)
                inheriting_assertions.append((a_id, prior_status, clean_notes))

    # Update source claim
    cursor = connection.execute(
        """
        UPDATE source_claims
        SET verification_status = ?,
            updated_at = ?,
            reviewed_by = ?,
            reviewed_at = ?,
            reviewer_notes = ?
        WHERE source_claim_id = ?
        """,
        (new_status, now, authorized_curator_id.strip(), now, merged_claim_notes, source_claim_id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"Expected exactly 1 claim updated, got {cursor.rowcount}")

    # Case A: Transitioning INTO terminal status
    if new_status in ('superseded', 'rejected'):
        for m_id, original_status in indep_terminal_mappings:
            connection.execute(
                "UPDATE concept_claim_mappings SET verification_status = ? WHERE mapping_id = ?",
                (original_status, m_id),
            )

        tag_prefix = f"[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR="
        for m_id, prior_status, clean_notes in inheriting_mappings:
            tagged_notes = f"{tag_prefix}{prior_status}] {clean_notes}" if clean_notes else f"{tag_prefix}{prior_status}]"
            connection.execute(
                "UPDATE concept_claim_mappings SET verification_status = ?, reviewer_notes = ? WHERE mapping_id = ?",
                (new_status, tagged_notes, m_id),
            )

        for a_id, prior_status, clean_notes in inheriting_assertions:
            tagged_notes = f"{tag_prefix}{prior_status}] {clean_notes}" if clean_notes else f"{tag_prefix}{prior_status}]"
            connection.execute(
                """
                UPDATE dosha_claim_assertions
                SET verification_status = ?,
                    reviewed_by = ?,
                    reviewed_at = ?,
                    reviewer_notes = ?
                WHERE dosha_assertion_id = ?
                """,
                (new_status, authorized_curator_id.strip(), now, tagged_notes, a_id),
            )

    # Case B: Reopening FROM terminal status into non-terminal status
    reopened_mappings_count = 0
    reopened_assertions_count = 0
    if current_status in ('superseded', 'rejected') and new_status not in ('superseded', 'rejected'):
        child_mappings = connection.execute(
            "SELECT mapping_id, verification_status, reviewer_notes FROM concept_claim_mappings WHERE source_claim_id = ?",
            (source_claim_id,),
        ).fetchall()
        for m_id, m_status, m_notes in child_mappings:
            prior_status = _parse_inherited_tag(m_notes, source_claim_id)
            if prior_status:
                clean_notes = _strip_inherited_tag(m_notes, source_claim_id)
                if new_status == 'unreviewed' or prior_status == 'unreviewed':
                    target_child_status = 'unreviewed'
                else:
                    target_child_status = 'reviewed'
                connection.execute(
                    """
                    UPDATE concept_claim_mappings
                    SET verification_status = ?,
                        reviewed_by = ?,
                        reviewed_at = ?,
                        reviewer_notes = ?
                    WHERE mapping_id = ?
                    """,
                    (target_child_status, authorized_curator_id.strip(), now, clean_notes, m_id),
                )
                reopened_mappings_count += 1

        child_assertions = connection.execute(
            "SELECT dosha_assertion_id, verification_status, reviewer_notes FROM dosha_claim_assertions WHERE source_claim_id = ?",
            (source_claim_id,),
        ).fetchall()
        for a_id, a_status, a_notes in child_assertions:
            prior_status = _parse_inherited_tag(a_notes, source_claim_id)
            if prior_status:
                clean_notes = _strip_inherited_tag(a_notes, source_claim_id)
                if new_status == 'unreviewed' or prior_status == 'unreviewed':
                    target_child_status = 'unreviewed'
                else:
                    target_child_status = 'reviewed'
                connection.execute(
                    """
                    UPDATE dosha_claim_assertions
                    SET verification_status = ?,
                        reviewed_by = ?,
                        reviewed_at = ?,
                        reviewer_notes = ?
                    WHERE dosha_assertion_id = ?
                    """,
                    (target_child_status, authorized_curator_id.strip(), now, clean_notes, a_id),
                )
                reopened_assertions_count += 1

    # Insert permanent audit record into source_reconciliation_events
    herb_tag = f"[HERB_ID: {herb_id}]" if herb_id is not None else "[HERB_ID: UNATTACHED]"
    reopen_summary = ""
    if current_status in ('superseded', 'rejected') and new_status not in ('superseded', 'rejected'):
        reopen_summary = (
            f" Selective Reopening: {reopened_mappings_count} inheriting mappings resynchronized; "
            f"{reopened_assertions_count} inheriting assertions resynchronized; "
            f"independently terminal children left untouched."
        )
    audit_notes = f"[CLAIM_ID: {source_claim_id}] {herb_tag} {formatted_override}{reopen_summary}"
    connection.execute(
        """
        INSERT INTO source_reconciliation_events (
            source_id, event_type, snapshot_timestamp, extraction_status,
            is_complete_snapshot, claims_evaluated, properties_reconciled,
            omissions_flagged, notes, initiated_by
        ) VALUES (
            ?, 'manual_adjudication', ?, 'completed',
            0, 1, 0, 0, ?, ?
        )
        """,
        (source_id, now, audit_notes, authorized_curator_id.strip()),
    )
```

---

### G. Section-Level Omission Completeness Contract

1. **Database Boundary:** `source_reconciliation_events` tracks source-level snapshot completeness (`is_complete_snapshot = 1`). It contains no section identifier or section-level parse status.
2. **Application-Level Contract:**
   - Ingestion extractors must provide a structured section map: `parsed_sections: Mapping[str, bool]`.
   - The omission detection service must require:
     1. Source snapshot completed: `extraction_status = 'completed'` and `is_complete_snapshot = 1`.
     2. Specific section explicitly present and parsed: `parsed_sections.get(section_domain) is True`.
     3. Clear domain mapping between section and target relationship table.
   - If a source document section is missing unexpectedly or fails to parse, omissions must **not** be recorded for that domain.

---

## 8. Decision 7: Schema-Version Compatibility & Ledger Validation

The working database remains at **schema version 2** until explicit migration sign-off.

### A. Deterministic Migration Ledger Sequence Validation
Database capability gating inspects the full `schema_migrations` ledger:
```sql
SELECT version FROM schema_migrations ORDER BY version ASC;
```

Deterministic ledger evaluation rules:
1. **Uninitialized Database (Table `schema_migrations` does not exist):**
   `create_database()` initializes legacy tables and executes Migrations 1 and 2, bringing the database deterministically to **schema version 2**.
2. **Valid Version 2 Ledger (Versions exactly `[1, 2]`):**
   - Legacy and Stage B operations fully operational.
   - Ingestion completely skips Stage C tables.
   - Stage C semantic APIs (`herb_dravyaguna_profile`, `reconcile_herb_virya`) **must raise `FeatureUnavailableError`**:
     ```
     FeatureUnavailableError: Stage C normalized semantic features require schema version 3 (current database version is 2). Apply Migration 3 to enable Dravyaguna semantic profiles.
     ```
3. **Valid Version 3 Ledger (Versions exactly `[1, 2, 3]`):**
   - Legacy, Stage B provenance, and Stage C semantic operations fully operational.
   - Semantic APIs return complete profiles and reconciliation results.
4. **Malformed, Incomplete, or Unsupported Ledger:**
   - If the version list has gaps (e.g. `[1, 3]`), duplicate versions, non-sequential entries, versions `< 1`, or future versions `> 3` (e.g. `[1, 2, 3, 4]`):
     ```
     MigrationError: Unsupported database schema migration ledger <versions>. Expected exact sequence [1, 2] or [1, 2, 3].
     ```

---

## 9. Decision 8: Repository API Contracts & Static Typing

### A. `herb_dravyaguna_profile(herb_id: int, language: str = 'en', include_disputed: bool = False) -> dict[str, Any]`

#### 1. SQL Query Formulation (Actual DDL Parity)
The application query service fetches active profile components using only actual accepted tables and columns, enforcing multi-concept active-status quarantine, explicit `mapping_type != 'disputed'` filtering for public profiles, and projecting derived `is_disputed`:

```sql
-- Dravyaguna Properties (Rasa, Guna, Virya, Vipaka, Prabhava, Karma)
SELECT 
    p.herb_property_id AS property_id,
    c.concept_domain AS domain,
    c.concept_code,
    c_part.concept_code AS part_concept_code,
    m.mapping_type,
    m.mapping_confidence,
    m.verification_status AS mapping_status,
    CASE WHEN m.mapping_type = 'disputed' THEN 1 ELSE 0 END AS is_disputed,
    p.source_presence_status,
    sc.source_claim_id,
    sc.source_expression,
    s.source_key
FROM herb_dravyaguna_properties p
JOIN concept_claim_mappings m ON m.mapping_id = p.mapping_id
JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
JOIN source_records sr ON sr.source_record_id = sc.source_record_id
JOIN sources s ON s.source_id = sr.source_id
LEFT JOIN dravyaguna_concepts c_part ON c_part.concept_id = p.part_concept_id
WHERE p.herb_id = :herb_id
  AND p.source_presence_status = 'active'
  AND m.verification_status NOT IN ('superseded', 'rejected')
  AND sc.verification_status NOT IN ('superseded', 'rejected')
  AND c.status = 'active'
  AND (p.part_concept_id IS NULL OR c_part.status = 'active')
  AND (:include_disputed = 1 OR m.mapping_type != 'disputed');

-- Dosha Effects
SELECT 
    e.herb_dosha_effect_id AS dosha_effect_id,
    c_dosha.concept_code AS dosha_concept_code,
    c_effect.concept_code AS effect_concept_code,
    a.verification_status AS assertion_status,
    0 AS is_disputed,
    e.source_presence_status,
    sc.source_claim_id,
    sc.source_expression
FROM herb_dosha_effects e
JOIN dosha_claim_assertions a ON a.dosha_assertion_id = e.dosha_assertion_id
JOIN dravyaguna_concepts c_dosha ON c_dosha.concept_id = a.dosha_concept_id
JOIN dravyaguna_concepts c_effect ON c_effect.concept_id = a.effect_concept_id
JOIN source_claims sc ON sc.source_claim_id = a.source_claim_id
WHERE e.herb_id = :herb_id
  AND e.source_presence_status = 'active'
  AND a.verification_status NOT IN ('superseded', 'rejected')
  AND sc.verification_status NOT IN ('superseded', 'rejected')
  AND c_dosha.status = 'active'
  AND c_effect.status = 'active';

-- Plant Parts
SELECT 
    pp.herb_part_id AS part_id,
    c.concept_code,
    pp.source_presence_status,
    m.verification_status AS mapping_status,
    CASE WHEN m.mapping_type = 'disputed' THEN 1 ELSE 0 END AS is_disputed
FROM herb_plant_parts pp
JOIN concept_claim_mappings m ON m.mapping_id = pp.mapping_id
JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
WHERE pp.herb_id = :herb_id
  AND pp.source_presence_status = 'active'
  AND m.verification_status NOT IN ('superseded', 'rejected')
  AND sc.verification_status NOT IN ('superseded', 'rejected')
  AND c.status = 'active'
  AND (:include_disputed = 1 OR m.mapping_type != 'disputed');

-- Preparations
SELECT 
    prep.herb_preparation_id AS preparation_id,
    c_prep.concept_code AS prep_concept_code,
    c_part.concept_code AS part_concept_code,
    prep.source_presence_status,
    m_prep.verification_status AS mapping_status,
    CASE 
        WHEN m_prep.mapping_type = 'disputed' 
          OR (m_part.mapping_type IS NOT NULL AND m_part.mapping_type = 'disputed') 
        THEN 1 ELSE 0 
    END AS is_disputed
FROM herb_preparations prep
JOIN concept_claim_mappings m_prep ON m_prep.mapping_id = prep.prep_mapping_id
JOIN dravyaguna_concepts c_prep ON c_prep.concept_id = m_prep.concept_id
JOIN source_claims sc ON sc.source_claim_id = m_prep.source_claim_id
LEFT JOIN concept_claim_mappings m_part ON m_part.mapping_id = prep.part_mapping_id
LEFT JOIN dravyaguna_concepts c_part ON c_part.concept_id = m_part.concept_id
WHERE prep.herb_id = :herb_id
  AND prep.source_presence_status = 'active'
  AND m_prep.verification_status NOT IN ('superseded', 'rejected')
  AND sc.verification_status NOT IN ('superseded', 'rejected')
  AND c_prep.status = 'active'
  AND (prep.part_mapping_id IS NULL OR (c_part.status = 'active' AND m_part.verification_status NOT IN ('superseded', 'rejected')))
  AND (:include_disputed = 1 OR m_prep.mapping_type != 'disputed')
  AND (prep.part_mapping_id IS NULL OR :include_disputed = 1 OR m_part.mapping_type != 'disputed');

-- Indications
SELECT 
    ind.herb_indication_id AS indication_id,
    c.concept_code AS indication_concept_code,
    ind.source_presence_status,
    m.verification_status AS mapping_status,
    CASE WHEN m.mapping_type = 'disputed' THEN 1 ELSE 0 END AS is_disputed
FROM herb_indications ind
JOIN concept_claim_mappings m ON m.mapping_id = ind.mapping_id
JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
WHERE ind.herb_id = :herb_id
  AND ind.source_presence_status = 'active'
  AND m.verification_status NOT IN ('superseded', 'rejected')
  AND sc.verification_status NOT IN ('superseded', 'rejected')
  AND c.status = 'active'
  AND (:include_disputed = 1 OR m.mapping_type != 'disputed');
```

#### 2. Disputed Mappings Policy
- Rows with `mapping_type = 'disputed'` are excluded from default public profiles (`include_disputed=False`).
- When requested by audit/research callers (`include_disputed=True`), they are projected with derived `is_disputed = True`. (No `is_disputed` column exists in the database).

---

### B. `reconcile_herb_virya(herb_id: int) -> ViryaReconciliationReport`

#### 1. SQL Contract & Query Shapes (from `virya_reconciliation.sql`)
The four accepted reconciliation queries output two distinct shapes:
- **Queries 1, 2, and 3 (Tiers 1–3 Divergence):** Pairwise cross-record / cross-source comparisons across two distinct properties (`p1` vs `p2`) and source claims (`sc1` vs `sc2`).
- **Query 4 (Same-Claim Ambiguity Audit):** Intra-source ambiguity detecting a single claim on the identical herb record (`h1.id = h2.id` and `m1.source_claim_id = m2.source_claim_id`) mapped to conflicting Virya concepts.

#### 2. Typed Return Specification
```python
from typing import TypedDict, Literal

class ViryaPairwiseDivergenceRecord(TypedDict):
    botanical_identity: str
    identity_basis: Literal[
        'same_herb_record',
        'taxonomically_verified_shared_accepted_taxon',
        'taxonomically_reviewed_shared_accepted_taxon',
        'candidate_match_botanical_string_equality',
        'unmatched',
    ]
    herb_1_id: int
    herb_1_name: str
    herb_2_id: int
    herb_2_name: str
    source_1: str
    part_1_id: int | None
    part_1_code: str | None
    virya_1: str
    raw_claim_1: str
    mapping_1_status: str
    mapping_1_type: str
    source_2: str
    part_2_id: int | None
    part_2_code: str | None
    virya_2: str
    raw_claim_2: str
    mapping_2_status: str
    mapping_2_type: str
    part_comparison_scope: Literal['exact_part_match', 'different_part_or_unspecified_compatible', 'both_parts_unspecified']
    source_scope: Literal['same_source_internal_divergence', 'cross_source_divergence', 'cross_source_verified_disagreement']
    divergence_tier: Literal['TIER_1_UNREVIEWED_DIVERGENCE', 'TIER_2_REVIEWED_DIVERGENCE', 'VERIFIED_SOURCE_DISAGREEMENT']
    # Audit fields populated in Tier 3:
    claim_1_reviewed_by: str | None
    claim_1_reviewed_at: str | None
    mapping_1_verified_by: str | None
    mapping_1_verified_at: str | None
    claim_2_reviewed_by: str | None
    claim_2_reviewed_at: str | None
    mapping_2_verified_by: str | None
    mapping_2_verified_at: str | None

class ViryaSameClaimAmbiguityRecord(TypedDict):
    herb_id: int
    botanical_identity: str
    herb_name: str
    identity_basis: Literal['same_herb_record']
    source_record_id: int
    source: str
    source_claim_id: int
    source_field: str
    raw_claim: str
    claim_verification_status: str
    part_1_id: int | None
    part_2_id: int | None
    mapping_1_id: int
    virya_1: str
    mapping_1_status: str
    mapping_1_type: str
    mapping_2_id: int
    virya_2: str
    mapping_2_status: str
    mapping_2_type: str
    audit_category: Literal['HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY']

class ViryaReconciliationSummary(TypedDict):
    tier_1_unreviewed_divergence_count: int
    tier_2_reviewed_divergence_count: int
    tier_3_verified_disagreement_count: int
    same_claim_mapping_ambiguity_count: int
    total_reconciled_pairs: int

class ViryaReconciliationReport(TypedDict):
    target_herb_id: int
    reconciled_at: str
    summary_counts: ViryaReconciliationSummary
    tier_1_unreviewed_divergence: list[ViryaPairwiseDivergenceRecord]
    tier_2_reviewed_divergence: list[ViryaPairwiseDivergenceRecord]
    tier_3_verified_disagreements: list[ViryaPairwiseDivergenceRecord]
    same_claim_ambiguities: list[ViryaSameClaimAmbiguityRecord]
```

#### 3. WP-5 Executor Contract (Active Concept Filtering)
The accepted SQL in `virya_reconciliation.sql` joins `dravyaguna_concepts` without `c.status = 'active'`. Because `virya_reconciliation.sql` is an accepted Stage C.1 artifact that cannot be modified, the WP-5 executor must filter out returned rows where `virya_1`, `virya_2`, `part_1_code`, or `part_2_code` reference a non-active (`provisional` or `deprecated`) concept before calculating summary counts and populating `ViryaReconciliationReport`.

---

## 10. Decision 9: Canonical Catalog Authority & Citation Policy

The canonical concept catalog separates authority requirements across domains:

| Concept Domain Category | Primary Authority Standard | Citation Requirement | Non-Classical Policy |
| :--- | :--- | :--- | :--- |
| **Classical Dravyaguna (Rasa, Guna, Virya, Vipaka, Prabhava, Karma)** | Classical Samhitas (Caraka, Susruta, Astanga Hrdaya), classical Nighantus (Bhavaprakasha, Dhanvantari) | Exact treatise and verse/chapter citation (e.g. `Caraka Saṃhitā, Sūtrasthāna 26.64`). | Modern physiological theories must not be retrofitted into classical concept definitions. |
| **Dosha Principles & Effects** | Classical Samhitas | Samhita reference for fundamental Dosha actions and definitions. | Standardize canonical triads. |
| **Plant Parts (`plant_part`)** | Botanical glossary, Ayurvedic Pharmacopoeia of India (API) Part 1 | Statutory pharmacopoeia or standard botanical glossary citation (e.g. `API Part 1, Vol 1`). | Do not require classical Sanskrit citations for modern botanical anatomy. |
| **Preparation Forms (`preparation_form`)** | Ayurvedic Formulary of India (AFI), Sharngadhara Samhita | AFI standard or Sharngadhara formulation chapter. | Classical and statutory preparation standards both accepted. |
| **Clinical Indications (`indication`)** | Statutory pharmacopoeial indices (CCRAS / API) | API disease classifications and formulary indices. | Baseline standard indications. |
| **English & Scholarly Labels** | Academic lexicons, WHO benchmarks | Peer-reviewed academic lexicon or multilateral standard. | Machine translation citations are strictly prohibited. |

### Catalog Scope & Preferred-Label Invariants
1. **Target Volume Accounting:**
   - **Rasa:** 6 classical Rasas (Madhura, Amla, Lavana, Katu, Tikta, Kashaya).
   - **Guna:** 20 Gurvadi Gunas (10 opposing pairs) + 10 Paradi Gunas = 30 classical attributes.
   - **Virya:** 2 primary potencies (Ushna, Sheeta). The 8-fold Ashta-Virya classification involves classical textual variants (specifically *Mridu* vs. *Manda*; see Section 14.2) and is treated as an extended potency model requiring curator sign-off.
   - **Vipaka:** 3 classical post-digestive transformations (Madhura, Amla, Katu).
   - **Dosha & Effects:** 3 Doshas (Vata, Pitta, Kapha) and 2 primary directional effects (Decrease/Shamana, Increase/Vardhaka).
   - **Plant Parts & Preparations:** Morphological parts per API Part 1 and standardized dosage forms per AFI.
2. **Preferred Label Invariant (Application Contract):**
   The Stage C.1 DDL does **not** have a partial unique index guaranteeing only one preferred label per concept/language/script. Enforcing strictly one preferred label per `(concept_id, language_code, script_code)` is an application-level invariant validated by WP-1 tests.

---

## 11. Decision 10: Migration & Backfill Verification Contract

The backfill pipeline (WP-4) must operate strictly on disposable database copies until independently signed off.

### A. Pre- and Post-Migration Table Verification Set
Every pre-existing application table must be compared before and after Migration 3 to guarantee zero unintended mutations:
1. `herbs`
2. `illness`
3. `treatment`
4. `herb_attributes`
5. `herb_doshas`
6. `sources`
7. `source_records`
8. `source_claims`
9. `legacy_herb_map`
10. `herb_names`
11. `taxa`
12. `taxon_relationships`
13. `herb_taxa`

### B. Expected Schema & Sequence Ledger Changes
- **`schema_migrations`:** Must record exactly one new row:
  `version = 3`, `name = 'semantic_dravyaguna'`, `applied_at = <valid UTC ISO-8601 string>`.
- **`sqlite_sequence`:** Internal SQLite autoincrement counters for Stage B tables must remain unaltered. New sequence entries are permitted only for Stage C tables (`dravyaguna_concepts`, `concept_labels`, `concept_claim_mappings`, etc.).
- **Stage B Row Invariance:** Row counts, primary keys, and column hashes for all 13 legacy tables must remain 100% identical.

### C. Backfill Execution Protocol
- **No Synthetic Claims:** Backfilled mappings must reference genuine existing `source_claims` rows.
- **Calibrated Mapping Rule:** Automated ruleset mappings must record:
  ```sql
  mapping_method = 'lexicon_exact'
  mapping_confidence = NULL
  verification_status = 'unreviewed'
  ```
- **Idempotency Guarantee:** Executing the backfill script multiple times against the same database must insert 0 additional rows on subsequent runs.
- **Failure Rollback:** If any error occurs during backfill, the transaction must execute `ROLLBACK;`, leaving Stage B data intact and Stage C tables in their clean pre-backfill state.

---

## 12. Decision 11: Deliberately Bounded Scope of Work Package 1 (WP-1)

To prevent premature coupling with ingestion or backfill, WP-1 is strictly confined to building and validating the canonical concept catalog:

### Bounded WP-1 Deliverables
1. **Canonical Concept Seed Data (`dravyaguna_concepts`):** High-confidence entries covering all 11 domains (`status IN ('active', 'provisional')`).
2. **Multilingual Label Seed Data (`concept_labels`):** Hindi, English, and Sanskrit (IAST and Devanagari) entries (`verification_status = 'unreviewed'`).
3. **Authority Citations (`concept_label_sources`):** Explicit Samhita, Nighantu, AFI, and API citations.
4. **Concept-Code Namespace Validator:** Python module (`validate_concept_code_prefix`) enforcing `<DOMAIN_PREFIX>_<CANONICAL_TOKEN>` syntax (`^[A-Z]+_[A-Z0-9_]+$`).
5. **Domain-to-Prefix Validation Tests:** Unit tests proving validator rejects invalid prefixes or mismatched domains.
6. **Label Verification & Preferred-Label Tests:** Unit tests asserting `trg_validate_label_verification_insert` behavior and application-level single-preferred-label rules.
7. **Seed Idempotency Tests:** Verifying repeated seeding against a clean Stage C database inserts 0 duplicates.
8. **Catalog Coverage Report:** Documentation listing seeded concepts, authority references, and identifying missing or unresolved concepts.

*Explicit Non-Scope for WP-1:* Zero scraper modifications, zero backfill execution, zero ingestion pipeline changes.

---

## 13. Consequences & Trade-Offs

### Positive Consequences
- **Decoupled Architecture:** Schema v2 databases continue functioning with zero dependencies on Stage C.
- **Fail-Safe Semantic APIs:** Raising `FeatureUnavailableError` on v2 eliminates silent misinterpretation of missing data as negative clinical facts.
- **Deterministic Child Provenance:** The lineage tagging and pre-capture protocol protects independently terminal child records from being destroyed by `trg_cascade_claim_supersession` or incorrectly reopened.
- **Localized Presentation:** Hindi and English interfaces operate cleanly without displacing canonical Sanskrit scholarly terminology.
- **Conservative Calibration:** Keeping confidence `NULL` adheres strictly to data architecture guidelines.

### Negative Consequences & Operational Overhead
- **Application Orchestration Overhead:** Because SQLite triggers do not cascade to Dosha assertions and overwrite all mappings indiscriminately, the application layer must perform careful pre-capture, post-restoration, and tag management.
- **No Database-Enforced Audit Immutability:** Because `source_reconciliation_events` lacks DB-enforced immutability and claim-level foreign keys, the application layer carries full responsibility for maintaining append-only discipline and structured tag parsing in `notes`.

---

## 14. Taxonomy Decisions & Open Architectural Items

### 14.1 Dosha Effects (Formally Adjudicated)
- **Canonical Directional Effect Concepts:** Strictly seed 2 active canonical directional effect concepts in domain `dosha_effect`:
  - `EFFECT_DECREASE` (*Shamana* / *Kshaya* / *Hara* — pacifies/decreases Dosha)
  - `EFFECT_INCREASE` (*Vardhaka* / *Kopana* / *Vriddhi* — aggravates/increases Dosha)
- **Compound Decomposition Rule:** Compound expressions such as *Tridoshahara* or "balances all three Doshas" shall **not** use a third `EFFECT_BALANCE` concept. In extraction and backfill work packages (WP-3/WP-4), compound expressions decompose into discrete `EFFECT_DECREASE` (pacifying) assertions for each corresponding Dosha (`DOSHA_VATA`, `DOSHA_PITTA`, `DOSHA_KAPHA`).

### 14.2 Virya Scope & Ashta-Virya Potencies (Formally Adjudicated)
- **Primary Consensus Potencies (*Dvividha Virya*):** Seed with `status = 'active'` in domain `virya`:
  - `VIRYA_USHNA` (Hot potency)
  - `VIRYA_SHITA` (Cold potency)
- **Extended Potency Tokens (*Ashta-Virya*):** Seed 7 extended potency tokens under `concept_domain = 'virya'` with `status = 'provisional'` (cataloged with classical treatise citations for cross-treatise research while quarantined from default binary Virya reconciliation and default public profiles per Decision 2.C):
  - `VIRYA_SNIGDHA`, `VIRYA_RUKSHA`, `VIRYA_GURU`, `VIRYA_LAGHU`, `VIRYA_TIKSHNA`, `VIRYA_MRIDU` (citing *Suśruta Saṃhitā, Sūtrasthāna 40.5*), and `VIRYA_MANDA` (citing *Aṣṭāṅga Hṛdaya* / Nighaṇṭu commentaries).
- **Independent Guna Attributes:** The corresponding *Gurvadi Guna* attributes (`GUNA_SNIGDHA`, `GUNA_RUKSHA`, `GUNA_GURU`, `GUNA_LAGHU`, `GUNA_TIKSHNA`, `GUNA_MRIDU`, `GUNA_MANDA`, `GUNA_SHITA`, `GUNA_USHNA`) are independently seeded as `status = 'active'` under `concept_domain = 'guna'`.

### 14.3 Future Open Architectural Items
1. **Accepted Botanical Taxon Curation Standard:** Which statutory checklist (World Flora Online, Kew POWO, or CCRAS authority) will serve as the official standard for promoting taxa to `relationship_type = 'accepted'` (deferred to WP-4 botanical backfill).
2. **Routine Verification Event Typing:** Because `source_reconciliation_events.event_type` is restricted to 4 specific values, routine claim verification cannot be recorded in this table without reusing `manual_adjudication`. Whether to expand `event_type` via a future migration remains an open schema decision.

---

## 15. Confirmation of Execution Restrictions

In strict adherence to the WP-0 authorization scope:
- **No Python source code** under `src/herbal_almanac/` was modified.
- **No SQL DDL, triggers, or migration files** were modified.
- **No backfill scripts** were created or executed.
- **Migration 3 was NOT applied** to any existing project database.
- **Neither `data/inspection.db` nor `AyurvedicDB.db`** was modified.
- **No ingestion runs** were executed against existing project databases.
- **No test files** under `tests/` were modified.
- **No project dependencies** were installed.
- **No Git commit, push, stash, reset, or branch operations** were executed.
