-- ============================================================================
-- HERBAL ALMANAC: STAGE C DDL & TRIGGERS
-- Normalized Dravyaguna Domain Model & Multilingual Data Architecture
-- Compatible with Stage B Schema (Migrations 1 & 2)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Standardized Dravyaguna Concepts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dravyaguna_concepts (
    concept_id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_code TEXT NOT NULL UNIQUE,
    concept_domain TEXT NOT NULL,
    parent_concept_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (parent_concept_id) REFERENCES dravyaguna_concepts(concept_id)
        ON DELETE RESTRICT,
    CHECK (concept_domain IN (
        'rasa', 'guna', 'virya', 'vipaka', 'prabhava',
        'karma', 'dosha', 'dosha_effect', 'plant_part',
        'preparation_form', 'indication'
    )),
    CHECK (status IN ('active', 'deprecated', 'provisional')),
    CHECK (parent_concept_id IS NULL OR parent_concept_id != concept_id)
);

CREATE INDEX IF NOT EXISTS idx_concepts_domain ON dravyaguna_concepts(concept_domain);
CREATE INDEX IF NOT EXISTS idx_concepts_parent ON dravyaguna_concepts(parent_concept_id);

-- ----------------------------------------------------------------------------
-- 2. Multilingual Concept Labels
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concept_labels (
    concept_label_id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER NOT NULL,
    language_code TEXT NOT NULL,
    script_code TEXT NOT NULL,
    label_text TEXT NOT NULL,
    normalized_label TEXT NOT NULL,
    label_type TEXT NOT NULL,
    translation_origin TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewed_by TEXT,
    reviewed_at TEXT,
    verified_by TEXT,
    verified_at TEXT,
    reviewer_notes TEXT,
    is_preferred INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (concept_id) REFERENCES dravyaguna_concepts(concept_id)
        ON DELETE RESTRICT,
    CHECK (is_preferred IN (0, 1)),
    CHECK (label_type IN (
        'canonical_sanskrit', 'scholarly_translation',
        'transliteration', 'vernacular_equivalent', 'synonym'
    )),
    CHECK (translation_origin IN (
        'classical_lexicon', 'scholarly_reference',
        'source_authored', 'human_curated', 'machine_generated'
    )),
    CHECK (verification_status IN (
        'unreviewed', 'reviewed', 'verified', 'disputed', 'rejected'
    )),
    UNIQUE(concept_id, language_code, script_code, normalized_label)
);

CREATE INDEX IF NOT EXISTS idx_concept_labels_lookup ON concept_labels(concept_id, language_code, is_preferred);
CREATE INDEX IF NOT EXISTS idx_concept_labels_normalized ON concept_labels(normalized_label);

-- ----------------------------------------------------------------------------
-- 3. Concept Label Sources (Bibliographical Citations)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concept_label_sources (
    label_source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_label_id INTEGER NOT NULL,
    source_id INTEGER,
    authority_citation TEXT NOT NULL,
    citation_type TEXT NOT NULL,
    verified_by TEXT,
    verified_at TEXT,
    citation_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (concept_label_id) REFERENCES concept_labels(concept_label_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
        ON DELETE RESTRICT,
    CHECK (citation_type IN (
        'classical_text', 'statutory_pharmacopoeia',
        'multilateral_standard', 'academic_lexicon', 'source_document'
    )),
    CHECK (source_id IS NOT NULL OR citation_type IN ('classical_text', 'academic_lexicon'))
);

CREATE INDEX IF NOT EXISTS idx_label_sources_label ON concept_label_sources(concept_label_id);
CREATE INDEX IF NOT EXISTS idx_label_sources_source ON concept_label_sources(source_id);

-- ----------------------------------------------------------------------------
-- 4. Atomic Concept Claim Mappings
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concept_claim_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_claim_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    mapping_type TEXT NOT NULL DEFAULT 'exact',
    mapping_confidence REAL CHECK (mapping_confidence IS NULL OR (mapping_confidence >= 0.0 AND mapping_confidence <= 1.0)),
    mapping_method TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewed_by TEXT,
    reviewed_at TEXT,
    reviewer_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (concept_id) REFERENCES dravyaguna_concepts(concept_id)
        ON DELETE RESTRICT,
    CHECK (mapping_type IN ('exact', 'broader', 'narrower', 'partial', 'disputed')),
    CHECK (mapping_method IN ('lexicon_exact', 'rule_normalizer', 'human_expert', 'heuristic')),
    CHECK (verification_status IN ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded')),
    UNIQUE(source_claim_id, concept_id)
);

CREATE INDEX IF NOT EXISTS idx_claim_mappings_claim ON concept_claim_mappings(source_claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_mappings_concept ON concept_claim_mappings(concept_id);

-- ----------------------------------------------------------------------------
-- 5. Dosha Claim Assertions (Composite Pairings)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dosha_claim_assertions (
    dosha_assertion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_claim_id INTEGER NOT NULL,
    dosha_concept_id INTEGER NOT NULL,
    effect_concept_id INTEGER NOT NULL,
    clause_expression TEXT,
    mapping_confidence REAL CHECK (mapping_confidence IS NULL OR (mapping_confidence >= 0.0 AND mapping_confidence <= 1.0)),
    mapping_method TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewed_by TEXT,
    reviewed_at TEXT,
    reviewer_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (dosha_concept_id) REFERENCES dravyaguna_concepts(concept_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (effect_concept_id) REFERENCES dravyaguna_concepts(concept_id)
        ON DELETE RESTRICT,
    CHECK (mapping_method IN ('rule_normalizer', 'human_expert', 'lexicon_exact')),
    CHECK (verification_status IN ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded')),
    UNIQUE(source_claim_id, dosha_concept_id, effect_concept_id)
);

CREATE INDEX IF NOT EXISTS idx_dosha_assertions_claim ON dosha_claim_assertions(source_claim_id);
CREATE INDEX IF NOT EXISTS idx_dosha_assertions_pair ON dosha_claim_assertions(dosha_concept_id, effect_concept_id);

-- ----------------------------------------------------------------------------
-- 6. Herb Dravyaguna Properties (Preserves legacy herb_attributes intact)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS herb_dravyaguna_properties (
    herb_property_id INTEGER PRIMARY KEY AUTOINCREMENT,
    herb_id INTEGER NOT NULL,
    mapping_id INTEGER NOT NULL,
    part_concept_id INTEGER,
    qualifier TEXT,
    source_presence_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (herb_id) REFERENCES herbs(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (mapping_id) REFERENCES concept_claim_mappings(mapping_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (part_concept_id) REFERENCES dravyaguna_concepts(concept_id)
        ON DELETE RESTRICT,
    CHECK (source_presence_status IN ('active', 'candidate_omission', 'confirmed_omission')),
    UNIQUE(herb_id, mapping_id, part_concept_id)
);

CREATE INDEX IF NOT EXISTS idx_herb_properties_herb ON herb_dravyaguna_properties(herb_id);
CREATE INDEX IF NOT EXISTS idx_herb_properties_mapping ON herb_dravyaguna_properties(mapping_id);
CREATE INDEX IF NOT EXISTS idx_herb_properties_part ON herb_dravyaguna_properties(part_concept_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_herb_dravyaguna_prop_null_part ON herb_dravyaguna_properties(herb_id, mapping_id) WHERE part_concept_id IS NULL;

-- ----------------------------------------------------------------------------
-- 7. Herb Dosha Effects (Preserves legacy herb_doshas intact)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS herb_dosha_effects (
    herb_dosha_effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
    herb_id INTEGER NOT NULL,
    dosha_assertion_id INTEGER NOT NULL,
    source_presence_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (herb_id) REFERENCES herbs(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (dosha_assertion_id) REFERENCES dosha_claim_assertions(dosha_assertion_id)
        ON DELETE RESTRICT,
    CHECK (source_presence_status IN ('active', 'candidate_omission', 'confirmed_omission')),
    UNIQUE(herb_id, dosha_assertion_id)
);

CREATE INDEX IF NOT EXISTS idx_herb_dosha_herb ON herb_dosha_effects(herb_id);
CREATE INDEX IF NOT EXISTS idx_herb_dosha_assertion ON herb_dosha_effects(dosha_assertion_id);

-- ----------------------------------------------------------------------------
-- 8. Herb Plant Parts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS herb_plant_parts (
    herb_part_id INTEGER PRIMARY KEY AUTOINCREMENT,
    herb_id INTEGER NOT NULL,
    mapping_id INTEGER NOT NULL,
    context_notes TEXT,
    source_presence_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (herb_id) REFERENCES herbs(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (mapping_id) REFERENCES concept_claim_mappings(mapping_id)
        ON DELETE RESTRICT,
    CHECK (source_presence_status IN ('active', 'candidate_omission', 'confirmed_omission')),
    UNIQUE(herb_id, mapping_id)
);

CREATE INDEX IF NOT EXISTS idx_herb_parts_herb ON herb_plant_parts(herb_id);
CREATE INDEX IF NOT EXISTS idx_herb_parts_mapping ON herb_plant_parts(mapping_id);

-- ----------------------------------------------------------------------------
-- 9. Herb Preparations
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS herb_preparations (
    herb_preparation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    herb_id INTEGER NOT NULL,
    prep_mapping_id INTEGER NOT NULL,
    part_mapping_id INTEGER,
    context_notes TEXT,
    source_presence_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (herb_id) REFERENCES herbs(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (prep_mapping_id) REFERENCES concept_claim_mappings(mapping_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (part_mapping_id) REFERENCES concept_claim_mappings(mapping_id)
        ON DELETE RESTRICT,
    CHECK (source_presence_status IN ('active', 'candidate_omission', 'confirmed_omission')),
    UNIQUE(herb_id, prep_mapping_id, part_mapping_id)
);

CREATE INDEX IF NOT EXISTS idx_herb_preparations_herb ON herb_preparations(herb_id);
CREATE INDEX IF NOT EXISTS idx_herb_preparations_prep ON herb_preparations(prep_mapping_id);
CREATE INDEX IF NOT EXISTS idx_herb_preparations_part ON herb_preparations(part_mapping_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_herb_preparations_null_part ON herb_preparations(herb_id, prep_mapping_id) WHERE part_mapping_id IS NULL;

-- ----------------------------------------------------------------------------
-- 10. Herb Traditional Indications (Preserves legacy treatment/illness intact)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS herb_indications (
    herb_indication_id INTEGER PRIMARY KEY AUTOINCREMENT,
    herb_id INTEGER NOT NULL,
    mapping_id INTEGER NOT NULL,
    context_notes TEXT,
    source_presence_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (herb_id) REFERENCES herbs(id)
        ON DELETE RESTRICT,
    FOREIGN KEY (mapping_id) REFERENCES concept_claim_mappings(mapping_id)
        ON DELETE RESTRICT,
    CHECK (source_presence_status IN ('active', 'candidate_omission', 'confirmed_omission')),
    UNIQUE(herb_id, mapping_id)
);

CREATE INDEX IF NOT EXISTS idx_herb_indications_herb ON herb_indications(herb_id);
CREATE INDEX IF NOT EXISTS idx_herb_indications_mapping ON herb_indications(mapping_id);

-- ============================================================================
-- STAGE C INTEGRITY TRIGGERS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Section 1: Source & Claim Mutation & Supersession Cascades
-- ----------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_protect_source_key_mutation
BEFORE UPDATE OF source_key ON sources
FOR EACH ROW
WHEN (
    OLD.source_key != NEW.source_key
    AND (
        EXISTS (
            SELECT 1 FROM source_records sr
            JOIN source_claims sc ON sc.source_record_id = sr.source_record_id
            JOIN concept_claim_mappings m ON m.source_claim_id = sc.source_claim_id
            WHERE sr.source_id = OLD.source_id
              AND (
                  EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE mapping_id = m.mapping_id)
                  OR EXISTS (SELECT 1 FROM herb_plant_parts WHERE mapping_id = m.mapping_id)
                  OR EXISTS (SELECT 1 FROM herb_preparations WHERE prep_mapping_id = m.mapping_id OR part_mapping_id = m.mapping_id)
                  OR EXISTS (SELECT 1 FROM herb_indications WHERE mapping_id = m.mapping_id)
              )
        )
        OR EXISTS (
            SELECT 1 FROM source_records sr
            JOIN source_claims sc ON sc.source_record_id = sr.source_record_id
            JOIN dosha_claim_assertions a ON a.source_claim_id = sc.source_claim_id
            WHERE sr.source_id = OLD.source_id
              AND EXISTS (SELECT 1 FROM herb_dosha_effects WHERE dosha_assertion_id = a.dosha_assertion_id)
        )
        OR EXISTS (
            SELECT 1 FROM concept_label_sources cls
            JOIN concept_labels cl ON cl.concept_label_id = cls.concept_label_id
            WHERE cls.source_id = OLD.source_id
              AND cl.verification_status = 'verified'
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate source_key of a source currently referenced by active herb relationships or verified label citations');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_sources_delete
BEFORE DELETE ON sources
FOR EACH ROW
WHEN (
    EXISTS (SELECT 1 FROM source_records WHERE source_id = OLD.source_id)
    OR EXISTS (SELECT 1 FROM concept_label_sources WHERE source_id = OLD.source_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot delete source referenced by source_records or concept_label_sources');
END;

CREATE TRIGGER IF NOT EXISTS trg_cascade_claim_supersession
AFTER UPDATE OF verification_status ON source_claims
FOR EACH ROW
WHEN NEW.verification_status IN ('superseded', 'rejected')
BEGIN
    UPDATE concept_claim_mappings 
    SET verification_status = NEW.verification_status
    WHERE source_claim_id = NEW.source_claim_id;
END;

-- ----------------------------------------------------------------------------
-- Section 2: Concept Hierarchy & Domain Mutability Invariants
-- ----------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_prevent_concept_cycle_update
BEFORE UPDATE OF parent_concept_id ON dravyaguna_concepts
FOR EACH ROW
WHEN NEW.parent_concept_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Hierarchy Error: Cycle detected in concept hierarchy')
    WHERE EXISTS (
        WITH RECURSIVE ancestors(ancestor_id) AS (
            SELECT NEW.parent_concept_id
            UNION ALL
            SELECT c.parent_concept_id
            FROM dravyaguna_concepts c
            JOIN ancestors a ON c.concept_id = a.ancestor_id
            WHERE c.parent_concept_id IS NOT NULL
        )
        SELECT 1 FROM ancestors WHERE ancestor_id = NEW.concept_id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_concept_parent_domain_insert
BEFORE INSERT ON dravyaguna_concepts
FOR EACH ROW
WHEN NEW.parent_concept_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: parent_concept_id must have the same concept_domain as child')
    WHERE NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts p
        WHERE p.concept_id = NEW.parent_concept_id
          AND p.concept_domain = NEW.concept_domain
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_concept_parent_domain_update
BEFORE UPDATE OF parent_concept_id, concept_domain ON dravyaguna_concepts
FOR EACH ROW
WHEN NEW.parent_concept_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: parent_concept_id must have the same concept_domain as child')
    WHERE NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts p
        WHERE p.concept_id = NEW.parent_concept_id
          AND p.concept_domain = NEW.concept_domain
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_prevent_parent_domain_mutation_with_children
BEFORE UPDATE OF concept_domain ON dravyaguna_concepts
FOR EACH ROW
WHEN OLD.concept_domain != NEW.concept_domain
BEGIN
    SELECT RAISE(ABORT, 'Hierarchy Error: Cannot change concept_domain of a concept that has existing child concepts')
    WHERE EXISTS (
        SELECT 1 FROM dravyaguna_concepts child
        WHERE child.parent_concept_id = OLD.concept_id
    );
    SELECT RAISE(ABORT, 'Domain Mutation Error: Cannot change concept_domain while mappings reference it')
    WHERE EXISTS (SELECT 1 FROM concept_claim_mappings WHERE concept_id = OLD.concept_id)
       OR EXISTS (SELECT 1 FROM dosha_claim_assertions WHERE dosha_concept_id = OLD.concept_id OR effect_concept_id = OLD.concept_id)
       OR EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE part_concept_id = OLD.concept_id);
END;

-- ----------------------------------------------------------------------------
-- Section 3: Multilingual Label Verification & Identity Invariants
-- ----------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_validate_label_verification_insert
BEFORE INSERT ON concept_labels
FOR EACH ROW
WHEN NEW.verification_status = 'verified'
BEGIN
    SELECT RAISE(ABORT, 'Label Verification Error: New labels cannot be inserted directly as verified; insert as unreviewed, attach verified citation, then update');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_verified_label_identity_mutation
BEFORE UPDATE OF concept_id, label_text, normalized_label, language_code, script_code, label_type, verified_by, verified_at, reviewed_by, reviewed_at ON concept_labels
FOR EACH ROW
WHEN OLD.verification_status = 'verified'
BEGIN
    SELECT RAISE(ABORT, 'Label Verification Error: Cannot mutate identity fields (concept_id, label_text, language, script, type) of a verified label; demote to unreviewed/reviewed first')
    WHERE OLD.concept_id != NEW.concept_id
       OR OLD.label_text != NEW.label_text
       OR OLD.normalized_label != NEW.normalized_label
       OR OLD.language_code != NEW.language_code
       OR OLD.script_code != NEW.script_code
       OR OLD.label_type != NEW.label_type;

    SELECT RAISE(ABORT, 'Label Verification Error: Cannot clear verified_by or verified_at on a verified label; demote first')
    WHERE NEW.verification_status = 'verified'
      AND (
          (COALESCE(NEW.verified_by, NEW.reviewed_by) IS NULL OR TRIM(COALESCE(NEW.verified_by, NEW.reviewed_by)) = '')
          OR
          (COALESCE(NEW.verified_at, NEW.reviewed_at) IS NULL OR TRIM(COALESCE(NEW.verified_at, NEW.reviewed_at)) = '')
      );
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_verified_label_delete
BEFORE DELETE ON concept_labels
FOR EACH ROW
WHEN OLD.verification_status = 'verified'
BEGIN
    SELECT RAISE(ABORT, 'Label Deletion Error: Cannot delete a verified label; demote to unreviewed/reviewed or mark deprecated first');
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_label_verification_update
BEFORE UPDATE OF verification_status, translation_origin, reviewed_by, reviewed_at, verified_by, verified_at ON concept_labels
FOR EACH ROW
WHEN NEW.verification_status = 'verified'
BEGIN
    SELECT RAISE(ABORT, 'Label Verification Error: Machine-generated translations cannot be verified')
    WHERE NEW.translation_origin = 'machine_generated';

    SELECT RAISE(ABORT, 'Label Verification Error: verified_by must be populated for verified label')
    WHERE (NEW.verified_by IS NULL OR TRIM(NEW.verified_by) = '')
      AND (NEW.reviewed_by IS NULL OR TRIM(NEW.reviewed_by) = '');

    SELECT RAISE(ABORT, 'Label Verification Error: verified_at must be populated for verified label')
    WHERE (NEW.verified_at IS NULL OR TRIM(NEW.verified_at) = '')
      AND (NEW.reviewed_at IS NULL OR TRIM(NEW.reviewed_at) = '');

    SELECT RAISE(ABORT, 'Label Verification Error: A label cannot be verified without at least one valid verified citation with non-empty authority citation in concept_label_sources')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_label_sources cls
        WHERE cls.concept_label_id = NEW.concept_label_id
          AND cls.verified_by IS NOT NULL AND TRIM(cls.verified_by) != ''
          AND cls.verified_at IS NOT NULL AND TRIM(cls.verified_at) != ''
          AND cls.authority_citation IS NOT NULL AND TRIM(cls.authority_citation) != ''
          AND cls.citation_type IN ('classical_text', 'statutory_pharmacopoeia', 'multilateral_standard', 'academic_lexicon', 'source_document')
          AND (cls.source_id IS NOT NULL OR cls.citation_type IN ('classical_text', 'academic_lexicon'))
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_verified_label_citation_delete
BEFORE DELETE ON concept_label_sources
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Citation Invalidation Error: Cannot delete the last valid verified citation while parent label is verified; demote label first')
    WHERE (SELECT verification_status FROM concept_labels WHERE concept_label_id = OLD.concept_label_id) = 'verified'
      AND (
          SELECT COUNT(*) FROM concept_label_sources
          WHERE concept_label_id = OLD.concept_label_id 
            AND label_source_id != OLD.label_source_id
            AND verified_by IS NOT NULL AND TRIM(verified_by) != ''
            AND verified_at IS NOT NULL AND TRIM(verified_at) != ''
            AND authority_citation IS NOT NULL AND TRIM(authority_citation) != ''
            AND citation_type IN ('classical_text', 'statutory_pharmacopoeia', 'multilateral_standard', 'academic_lexicon', 'source_document')
            AND (source_id IS NOT NULL OR citation_type IN ('classical_text', 'academic_lexicon'))
      ) = 0;
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_verified_label_citation_update
BEFORE UPDATE OF authority_citation, citation_type, verified_by, verified_at, concept_label_id, source_id ON concept_label_sources
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Citation Invalidation Error: Cannot invalidate or reassign the last verified citation of a verified label; demote label first')
    WHERE (SELECT verification_status FROM concept_labels WHERE concept_label_id = OLD.concept_label_id) = 'verified'
      AND (
          OLD.concept_label_id != NEW.concept_label_id
          OR NEW.verified_by IS NULL OR TRIM(NEW.verified_by) = ''
          OR NEW.verified_at IS NULL OR TRIM(NEW.verified_at) = ''
          OR NEW.authority_citation IS NULL OR TRIM(NEW.authority_citation) = ''
          OR NEW.citation_type NOT IN ('classical_text', 'statutory_pharmacopoeia', 'multilateral_standard', 'academic_lexicon', 'source_document')
          OR (NEW.source_id IS NULL AND NEW.citation_type NOT IN ('classical_text', 'academic_lexicon'))
      )
      AND (
          SELECT COUNT(*) FROM concept_label_sources
          WHERE concept_label_id = OLD.concept_label_id 
            AND label_source_id != OLD.label_source_id
            AND verified_by IS NOT NULL AND TRIM(verified_by) != ''
            AND verified_at IS NOT NULL AND TRIM(verified_at) != ''
            AND authority_citation IS NOT NULL AND TRIM(authority_citation) != ''
            AND citation_type IN ('classical_text', 'statutory_pharmacopoeia', 'multilateral_standard', 'academic_lexicon', 'source_document')
            AND (source_id IS NOT NULL OR citation_type IN ('classical_text', 'academic_lexicon'))
      ) = 0;
END;

-- ----------------------------------------------------------------------------
-- Section 4: Parent-Side Cross-Herb Evidence Immutability Invariants
-- ----------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_protect_claim_mapping_mutation
BEFORE UPDATE OF source_claim_id, concept_id ON concept_claim_mappings
FOR EACH ROW
WHEN (
    EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE mapping_id = OLD.mapping_id)
    OR EXISTS (SELECT 1 FROM herb_plant_parts WHERE mapping_id = OLD.mapping_id)
    OR EXISTS (SELECT 1 FROM herb_preparations WHERE prep_mapping_id = OLD.mapping_id OR part_mapping_id = OLD.mapping_id)
    OR EXISTS (SELECT 1 FROM herb_indications WHERE mapping_id = OLD.mapping_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate source_claim_id or concept_id of a mapping currently referenced by active herb relationships');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_dosha_assertion_mutation
BEFORE UPDATE OF source_claim_id, dosha_concept_id, effect_concept_id ON dosha_claim_assertions
FOR EACH ROW
WHEN (
    EXISTS (SELECT 1 FROM herb_dosha_effects WHERE dosha_assertion_id = OLD.dosha_assertion_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate source_claim_id or concepts of a dosha assertion currently referenced by active herb relationships');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_source_claim_mutation
BEFORE UPDATE OF source_record_id, claim_type, source_field, source_expression, language_code, normalization_method ON source_claims
FOR EACH ROW
WHEN (
    (
        NEW.source_record_id IS NOT OLD.source_record_id
        OR NEW.claim_type IS NOT OLD.claim_type
        OR NEW.source_field IS NOT OLD.source_field
        OR NEW.source_expression IS NOT OLD.source_expression
        OR NEW.language_code IS NOT OLD.language_code
        OR NEW.normalization_method IS NOT OLD.normalization_method
    )
    AND (
        EXISTS (
            SELECT 1 FROM concept_claim_mappings WHERE source_claim_id = OLD.source_claim_id
        )
        OR EXISTS (
            SELECT 1 FROM dosha_claim_assertions WHERE source_claim_id = OLD.source_claim_id
        )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate original assertion-defining fields (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method) on a source claim referenced by Stage C mappings or assertions');
END;

-- ----------------------------------------------------------------------------
-- Source Claim Review Auditability Triggers
-- Enforce reviewed_by and reviewed_at non-empty when status is reviewed or verified
-- ----------------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_validate_source_claim_review_metadata_insert
BEFORE INSERT ON source_claims
FOR EACH ROW
WHEN NEW.verification_status IN ('reviewed', 'verified')
BEGIN
    SELECT CASE
        WHEN NEW.reviewed_by IS NULL OR trim(NEW.reviewed_by) = ''
             OR NEW.reviewed_at IS NULL OR trim(NEW.reviewed_at) = ''
        THEN RAISE(ABORT, 'Integrity Error: reviewed_by and reviewed_at must be populated when source_claims.verification_status is reviewed or verified')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_source_claim_review_metadata_update
BEFORE UPDATE OF verification_status, reviewed_by, reviewed_at ON source_claims
FOR EACH ROW
WHEN NEW.verification_status IN ('reviewed', 'verified')
BEGIN
    SELECT CASE
        WHEN NEW.reviewed_by IS NULL OR trim(NEW.reviewed_by) = ''
             OR NEW.reviewed_at IS NULL OR trim(NEW.reviewed_at) = ''
        THEN RAISE(ABORT, 'Integrity Error: reviewed_by and reviewed_at must be populated when source_claims.verification_status is reviewed or verified')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_source_record_mutation
BEFORE UPDATE OF source_id, external_record_key, raw_artifact_ref ON source_records
FOR EACH ROW
WHEN (
    EXISTS (
        SELECT 1 FROM source_claims sc
        JOIN concept_claim_mappings m ON m.source_claim_id = sc.source_claim_id
        WHERE sc.source_record_id = OLD.source_record_id
          AND (
              EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE mapping_id = m.mapping_id)
              OR EXISTS (SELECT 1 FROM herb_plant_parts WHERE mapping_id = m.mapping_id)
              OR EXISTS (SELECT 1 FROM herb_preparations WHERE prep_mapping_id = m.mapping_id OR part_mapping_id = m.mapping_id)
              OR EXISTS (SELECT 1 FROM herb_indications WHERE mapping_id = m.mapping_id)
          )
    )
    OR EXISTS (
        SELECT 1 FROM source_claims sc
        JOIN dosha_claim_assertions a ON a.source_claim_id = sc.source_claim_id
        WHERE sc.source_record_id = OLD.source_record_id
          AND EXISTS (SELECT 1 FROM herb_dosha_effects WHERE dosha_assertion_id = a.dosha_assertion_id)
    )
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate identity fields of a source record currently referenced by active herb relationships');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_legacy_herb_map_mutation
BEFORE UPDATE OF legacy_herb_id, herb_id ON legacy_herb_map
FOR EACH ROW
WHEN (
    EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_plant_parts WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_preparations WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_indications WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_dosha_effects WHERE herb_id = OLD.herb_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate legacy_herb_map for a herb with active Stage C relationships');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_legacy_herb_map_delete
BEFORE DELETE ON legacy_herb_map
FOR EACH ROW
WHEN (
    EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_plant_parts WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_preparations WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_indications WHERE herb_id = OLD.herb_id)
    OR EXISTS (SELECT 1 FROM herb_dosha_effects WHERE herb_id = OLD.herb_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot delete legacy_herb_map for a herb with active Stage C relationships');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_herb_identity_mutation
BEFORE UPDATE OF source, source_record_id ON herbs
FOR EACH ROW
WHEN (
    EXISTS (
        SELECT 1 FROM legacy_herb_map lhm
        WHERE lhm.legacy_herb_id = OLD.id
          AND (
              EXISTS (SELECT 1 FROM herb_dravyaguna_properties WHERE herb_id = lhm.herb_id)
              OR EXISTS (SELECT 1 FROM herb_plant_parts WHERE herb_id = lhm.herb_id)
              OR EXISTS (SELECT 1 FROM herb_preparations WHERE herb_id = lhm.herb_id)
              OR EXISTS (SELECT 1 FROM herb_indications WHERE herb_id = lhm.herb_id)
              OR EXISTS (SELECT 1 FROM herb_dosha_effects WHERE herb_id = lhm.herb_id)
          )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'Evidence Immutability Error: Cannot mutate source or source_record_id of a herb with active Stage C relationships');
END;

-- ----------------------------------------------------------------------------
-- Section 5: Child-Side Domain & Cross-Herb Validation Invariants
-- ----------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prop_domain_insert
BEFORE INSERT ON herb_dravyaguna_properties
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: mapping must point to a concept in rasa, guna, virya, vipaka, prabhava, or karma')
    WHERE NOT EXISTS (
        SELECT 1 
        FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.mapping_id
          AND c.concept_domain IN ('rasa', 'guna', 'virya', 'vipaka', 'prabhava', 'karma')
    );
    SELECT RAISE(ABORT, 'Domain Error: part_concept_id must belong to plant_part domain')
    WHERE NEW.part_concept_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts c
        WHERE c.concept_id = NEW.part_concept_id AND c.concept_domain = 'plant_part'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prop_domain_update
BEFORE UPDATE OF mapping_id, part_concept_id ON herb_dravyaguna_properties
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: mapping must point to a concept in rasa, guna, virya, vipaka, prabhava, or karma')
    WHERE NOT EXISTS (
        SELECT 1 
        FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.mapping_id
          AND c.concept_domain IN ('rasa', 'guna', 'virya', 'vipaka', 'prabhava', 'karma')
    );
    SELECT RAISE(ABORT, 'Domain Error: part_concept_id must belong to plant_part domain')
    WHERE NEW.part_concept_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts c
        WHERE c.concept_id = NEW.part_concept_id AND c.concept_domain = 'plant_part'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prop_mapping_insert
BEFORE INSERT ON herb_dravyaguna_properties
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prop_mapping_update
BEFORE UPDATE OF herb_id, mapping_id ON herb_dravyaguna_properties
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_parts_domain_insert
BEFORE INSERT ON herb_plant_parts
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: mapping_id must point to plant_part domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.mapping_id AND c.concept_domain = 'plant_part'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_parts_domain_update
BEFORE UPDATE OF mapping_id ON herb_plant_parts
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: mapping_id must point to plant_part domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.mapping_id AND c.concept_domain = 'plant_part'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_parts_mapping_insert
BEFORE INSERT ON herb_plant_parts
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_parts_mapping_update
BEFORE UPDATE OF herb_id, mapping_id ON herb_plant_parts
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prep_domains_insert
BEFORE INSERT ON herb_preparations
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: prep_mapping_id must point to preparation_form domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.prep_mapping_id AND c.concept_domain = 'preparation_form'
    );
    SELECT RAISE(ABORT, 'Domain Error: part_mapping_id must point to plant_part domain')
    WHERE NEW.part_mapping_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.part_mapping_id AND c.concept_domain = 'plant_part'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prep_domains_update
BEFORE UPDATE OF prep_mapping_id, part_mapping_id ON herb_preparations
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: prep_mapping_id must point to preparation_form domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.prep_mapping_id AND c.concept_domain = 'preparation_form'
    );
    SELECT RAISE(ABORT, 'Domain Error: part_mapping_id must point to plant_part domain')
    WHERE NEW.part_mapping_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.part_mapping_id AND c.concept_domain = 'plant_part'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prep_cross_herb_insert
BEFORE INSERT ON herb_preparations
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: prep_mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.prep_mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
    SELECT RAISE(ABORT, 'Integrity Error: part_mapping_id does not belong to the source record of herb_id')
    WHERE NEW.part_mapping_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.part_mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_prep_cross_herb_update
BEFORE UPDATE OF herb_id, prep_mapping_id, part_mapping_id ON herb_preparations
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: prep_mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.prep_mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
    SELECT RAISE(ABORT, 'Integrity Error: part_mapping_id does not belong to the source record of herb_id')
    WHERE NEW.part_mapping_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.part_mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_indications_domain_insert
BEFORE INSERT ON herb_indications
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: mapping_id must point to indication domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.mapping_id AND c.concept_domain = 'indication'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_indications_domain_update
BEFORE UPDATE OF mapping_id ON herb_indications
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: mapping_id must point to indication domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM concept_claim_mappings m
        JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
        WHERE m.mapping_id = NEW.mapping_id AND c.concept_domain = 'indication'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_indications_mapping_insert
BEFORE INSERT ON herb_indications
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_indications_mapping_update
BEFORE UPDATE OF herb_id, mapping_id ON herb_indications
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: mapping_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM concept_claim_mappings m
        JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE m.mapping_id = NEW.mapping_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_dosha_assertion_domains_insert
BEFORE INSERT ON dosha_claim_assertions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: dosha_concept_id must belong to dosha domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts WHERE concept_id = NEW.dosha_concept_id AND concept_domain = 'dosha'
    );
    SELECT RAISE(ABORT, 'Domain Error: effect_concept_id must belong to dosha_effect domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts WHERE concept_id = NEW.effect_concept_id AND concept_domain = 'dosha_effect'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_dosha_assertion_domains_update
BEFORE UPDATE OF dosha_concept_id, effect_concept_id ON dosha_claim_assertions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Domain Error: dosha_concept_id must belong to dosha domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts WHERE concept_id = NEW.dosha_concept_id AND concept_domain = 'dosha'
    );
    SELECT RAISE(ABORT, 'Domain Error: effect_concept_id must belong to dosha_effect domain')
    WHERE NOT EXISTS (
        SELECT 1 FROM dravyaguna_concepts WHERE concept_id = NEW.effect_concept_id AND concept_domain = 'dosha_effect'
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_dosha_assertion_insert
BEFORE INSERT ON herb_dosha_effects
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: dosha_assertion_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM dosha_claim_assertions dca
        JOIN source_claims sc ON sc.source_claim_id = dca.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE dca.dosha_assertion_id = NEW.dosha_assertion_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_herb_dosha_assertion_update
BEFORE UPDATE OF herb_id, dosha_assertion_id ON herb_dosha_effects
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Integrity Error: dosha_assertion_id does not belong to the source record of herb_id')
    WHERE NOT EXISTS (
        SELECT 1
        FROM dosha_claim_assertions dca
        JOIN source_claims sc ON sc.source_claim_id = dca.source_claim_id
        JOIN source_records sr ON sr.source_record_id = sc.source_record_id
        JOIN sources s ON s.source_id = sr.source_id
        JOIN legacy_herb_map lhm ON lhm.herb_id = NEW.herb_id
        JOIN herbs h ON h.id = lhm.legacy_herb_id
        WHERE dca.dosha_assertion_id = NEW.dosha_assertion_id
          AND (
              (h.source_record_id IS NOT NULL 
               AND s.source_key = TRIM(h.source)
               AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
              OR
              (h.source_record_id IS NULL 
               AND s.source_key = 'manual' 
               AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
          )
    );
END;

-- ============================================================================
-- 11. Source Reconciliation Event Ledger
-- ============================================================================
CREATE TABLE IF NOT EXISTS source_reconciliation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    snapshot_timestamp TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    is_complete_snapshot INTEGER NOT NULL DEFAULT 0,
    claims_evaluated INTEGER NOT NULL DEFAULT 0,
    properties_reconciled INTEGER NOT NULL DEFAULT 0,
    omissions_flagged INTEGER NOT NULL DEFAULT 0,
    initiated_by TEXT NOT NULL,
    completed_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
        ON DELETE RESTRICT,
    CHECK (event_type IN ('ingest_batch', 'snapshot_reconciliation', 'manual_adjudication', 'omission_detection')),
    CHECK (extraction_status IN ('in_progress', 'completed', 'partial_failed', 'failed', 'aborted')),
    CHECK (is_complete_snapshot IN (0, 1)),
    CHECK (claims_evaluated >= 0),
    CHECK (properties_reconciled >= 0),
    CHECK (omissions_flagged >= 0),
    CHECK (is_complete_snapshot = 0 OR extraction_status = 'completed')
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_events_source ON source_reconciliation_events(source_id);
CREATE INDEX IF NOT EXISTS idx_reconciliation_events_status ON source_reconciliation_events(extraction_status);
CREATE INDEX IF NOT EXISTS idx_reconciliation_events_complete ON source_reconciliation_events(is_complete_snapshot);

-- Triggers for source reconciliation snapshot integrity
CREATE TRIGGER IF NOT EXISTS trg_protect_reconciliation_snapshot_integrity_insert
BEFORE INSERT ON source_reconciliation_events
FOR EACH ROW
WHEN NEW.is_complete_snapshot = 1 AND NEW.extraction_status != 'completed'
BEGIN
    SELECT RAISE(ABORT, 'Reconciliation Event Error: Incomplete or failed extraction cannot be treated as a complete source snapshot');
END;

CREATE TRIGGER IF NOT EXISTS trg_protect_reconciliation_snapshot_integrity_update
BEFORE UPDATE OF is_complete_snapshot, extraction_status ON source_reconciliation_events
FOR EACH ROW
WHEN NEW.is_complete_snapshot = 1 AND NEW.extraction_status != 'completed'
BEGIN
    SELECT RAISE(ABORT, 'Reconciliation Event Error: Incomplete or failed extraction cannot be treated as a complete source snapshot');
END;

-- ============================================================================
-- 12. Stage C Semantic Dravyaguna Reporting Views
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_active_herb_dravyaguna_properties AS
SELECT 
    h.id AS herb_id,
    h.english_name AS herb_name,
    h.botanical_name,
    s.source_key,
    p.herb_property_id,
    c.concept_domain,
    c.concept_code,
    c_part.concept_code AS part_code,
    m.mapping_type,
    m.verification_status AS mapping_status,
    sc.source_expression AS raw_claim,
    sc.verification_status AS claim_status,
    p.source_presence_status
FROM herb_dravyaguna_properties p
JOIN herbs h ON h.id = p.herb_id
JOIN concept_claim_mappings m ON m.mapping_id = p.mapping_id
JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
JOIN source_records sr ON sr.source_record_id = sc.source_record_id
JOIN sources s ON s.source_id = sr.source_id
LEFT JOIN dravyaguna_concepts c_part ON c_part.concept_id = p.part_concept_id
WHERE p.source_presence_status = 'active';

CREATE VIEW IF NOT EXISTS v_active_herb_dosha_effects AS
SELECT 
    h.id AS herb_id,
    h.english_name AS herb_name,
    h.botanical_name,
    s.source_key,
    e.herb_dosha_effect_id,
    c_dosha.concept_code AS dosha_code,
    c_effect.concept_code AS effect_code,
    a.verification_status AS assertion_status,
    sc.source_expression AS raw_claim,
    sc.verification_status AS claim_status,
    e.source_presence_status
FROM herb_dosha_effects e
JOIN herbs h ON h.id = e.herb_id
JOIN dosha_claim_assertions a ON a.dosha_assertion_id = e.dosha_assertion_id
JOIN dravyaguna_concepts c_dosha ON c_dosha.concept_id = a.dosha_concept_id
JOIN dravyaguna_concepts c_effect ON c_effect.concept_id = a.effect_concept_id
JOIN source_claims sc ON sc.source_claim_id = a.source_claim_id
JOIN source_records sr ON sr.source_record_id = sc.source_record_id
JOIN sources s ON s.source_id = sr.source_id
WHERE e.source_presence_status = 'active';
