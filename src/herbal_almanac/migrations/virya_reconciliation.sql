-- ============================================================================
-- HERBAL ALMANAC: VIRYA RECONCILIATION QUERIES (MUTUALLY EXCLUSIVE TIERS)
-- Includes Mapping Ambiguity Audit Query
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Tier 1 — Unreviewed Candidate Divergence
-- Criteria:
-- - Distinct source claims (sc1.source_claim_id != sc2.source_claim_id)
-- - Both source claims have active/valid status: verification_status IN ('unreviewed', 'reviewed', 'verified')
-- - Both mappings have valid status: verification_status IN ('unreviewed', 'reviewed', 'verified')
-- - Both mappings have valid comparative mapping types: mapping_type IN ('exact', 'broader', 'narrower')
-- - Tier 1 defining condition: At least one mapping OR underlying source claim has verification_status = 'unreviewed'
-- - Compatible plant-part scope (either same part ID or at least one NULL, distinct parts excluded)
-- - Presence status active on both sides
-- - Eligible identity conditions:
--   1. Same herb record (h1.id = h2.id)
--   2. Shared accepted taxon via herb_taxa (relationship_type = 'accepted')
--   3. Same non-empty botanical-name string
-- ----------------------------------------------------------------------------
SELECT DISTINCT
    COALESCE(h1.botanical_name, h1.english_name) AS botanical_identity,
    CASE 
        WHEN h1.id = h2.id THEN 'same_herb_record'
        WHEN EXISTS (
            SELECT 1 FROM herb_taxa ht1
            JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
            JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
            JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
            WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id
              AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
              AND sc_taxa1.verification_status = 'verified'
              AND sc_taxa2.verification_status = 'verified'
        ) THEN 'taxonomically_verified_shared_accepted_taxon'
        WHEN EXISTS (
            SELECT 1 FROM herb_taxa ht1
            JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
            JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
            JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
            WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id
              AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
              AND sc_taxa1.verification_status IN ('reviewed', 'verified')
              AND sc_taxa2.verification_status IN ('reviewed', 'verified')
        ) THEN 'taxonomically_reviewed_shared_accepted_taxon'
        WHEN h1.botanical_name IS NOT NULL AND trim(h1.botanical_name) != '' AND h1.botanical_name = h2.botanical_name THEN 'candidate_match_botanical_string_equality'
        ELSE 'unmatched'
    END AS identity_basis,
    h1.id AS herb_1_id,
    h1.english_name AS herb_1_name,
    h2.id AS herb_2_id,
    h2.english_name AS herb_2_name,
    s1.source_key AS source_1,
    p1.part_concept_id AS part_1_id,
    c_part1.concept_code AS part_1_code,
    c1.concept_code AS virya_1,
    sc1.source_expression AS raw_claim_1,
    m1.verification_status AS mapping_1_status,
    m1.mapping_type AS mapping_1_type,
    s2.source_key AS source_2,
    p2.part_concept_id AS part_2_id,
    c_part2.concept_code AS part_2_code,
    c2.concept_code AS virya_2,
    sc2.source_expression AS raw_claim_2,
    m2.verification_status AS mapping_2_status,
    m2.mapping_type AS mapping_2_type,
    CASE 
        WHEN p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NOT NULL AND p1.part_concept_id = p2.part_concept_id THEN 'exact_part_match'
        WHEN p1.part_concept_id IS NULL AND p2.part_concept_id IS NULL THEN 'both_parts_unspecified'
        ELSE 'unspecified_vs_specified_part'
    END AS part_comparison_scope,
    CASE 
        WHEN sr1.source_record_id = sr2.source_record_id THEN 'intra_source_record_divergence'
        WHEN s1.source_id = s2.source_id THEN 'intra_source_multi_record_divergence'
        ELSE 'cross_source_divergence'
    END AS source_scope,
    'UNREVIEWED_CANDIDATE_DIVERGENCE' AS divergence_tier
FROM herb_dravyaguna_properties p1
JOIN herbs h1 ON h1.id = p1.herb_id
JOIN concept_claim_mappings m1 ON m1.mapping_id = p1.mapping_id
JOIN dravyaguna_concepts c1 ON c1.concept_id = m1.concept_id
JOIN source_claims sc1 ON sc1.source_claim_id = m1.source_claim_id
JOIN source_records sr1 ON sr1.source_record_id = sc1.source_record_id
JOIN sources s1 ON s1.source_id = sr1.source_id
LEFT JOIN dravyaguna_concepts c_part1 ON c_part1.concept_id = p1.part_concept_id

JOIN herb_dravyaguna_properties p2 ON p2.herb_property_id > p1.herb_property_id
JOIN herbs h2 ON h2.id = p2.herb_id
JOIN concept_claim_mappings m2 ON m2.mapping_id = p2.mapping_id
JOIN dravyaguna_concepts c2 ON c2.concept_id = m2.concept_id
JOIN source_claims sc2 ON sc2.source_claim_id = m2.source_claim_id
JOIN source_records sr2 ON sr2.source_record_id = sc2.source_record_id
JOIN sources s2 ON s2.source_id = sr2.source_id
LEFT JOIN dravyaguna_concepts c_part2 ON c_part2.concept_id = p2.part_concept_id

WHERE (
    h1.id = h2.id
    OR (
        h1.botanical_name IS NOT NULL 
        AND trim(h1.botanical_name) != '' 
        AND h1.botanical_name = h2.botanical_name
    )
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
  AND sc1.source_claim_id != sc2.source_claim_id
  AND c1.concept_domain = 'virya' AND c2.concept_domain = 'virya'
  AND c1.concept_id != c2.concept_id
  -- Compatible plant-part scope (exclude distinct parts)
  AND NOT (p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NOT NULL AND p1.part_concept_id != p2.part_concept_id)
  -- Active presence status
  AND p1.source_presence_status = 'active'
  AND p2.source_presence_status = 'active'
  -- Positive whitelist for source claim eligibility
  AND sc1.verification_status IN ('unreviewed', 'reviewed', 'verified')
  AND sc2.verification_status IN ('unreviewed', 'reviewed', 'verified')
  -- Positive whitelist for mapping eligibility and mapping quality
  AND m1.verification_status IN ('unreviewed', 'reviewed', 'verified')
  AND m2.verification_status IN ('unreviewed', 'reviewed', 'verified')
  AND m1.mapping_type IN ('exact', 'broader', 'narrower')
  AND m2.mapping_type IN ('exact', 'broader', 'narrower')
  -- Tier 1 defining condition: At least one mapping OR source claim is unreviewed
  AND (m1.verification_status = 'unreviewed' OR m2.verification_status = 'unreviewed'
       OR sc1.verification_status = 'unreviewed' OR sc2.verification_status = 'unreviewed');


-- ----------------------------------------------------------------------------
-- Tier 2 — Reviewed Candidate Divergence
-- Criteria:
-- - Distinct source claims (sc1.source_claim_id != sc2.source_claim_id)
-- - Neither mapping is unreviewed - both are reviewed or verified
-- - Neither source claim is unreviewed - both are reviewed or verified
-- - Both mappings have valid comparative mapping types: mapping_type IN ('exact', 'broader', 'narrower')
-- - Compatible plant-part scope (either same part ID or at least one NULL, distinct parts excluded)
-- - Presence status active on both sides
-- - Eligible identity conditions (same record, shared accepted taxon, or same non-empty botanical string)
-- - Tier 2 defining condition: Fails one or more Tier 3 criteria:
--   * At least one mapping is an approximation (broader or narrower)
--   * OR at least one mapping is reviewed rather than verified
--   * OR intra-source divergence (same source authority s1.source_id = s2.source_id)
--   * OR non-identical plant part scope (unspecified vs specified part)
-- ----------------------------------------------------------------------------
SELECT DISTINCT
    COALESCE(h1.botanical_name, h1.english_name) AS botanical_identity,
    CASE 
        WHEN h1.id = h2.id THEN 'same_herb_record'
        WHEN EXISTS (
            SELECT 1 FROM herb_taxa ht1
            JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
            JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
            JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
            WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id
              AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
              AND sc_taxa1.verification_status = 'verified'
              AND sc_taxa2.verification_status = 'verified'
        ) THEN 'taxonomically_verified_shared_accepted_taxon'
        WHEN EXISTS (
            SELECT 1 FROM herb_taxa ht1
            JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
            JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
            JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
            WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id
              AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
              AND sc_taxa1.verification_status IN ('reviewed', 'verified')
              AND sc_taxa2.verification_status IN ('reviewed', 'verified')
        ) THEN 'taxonomically_reviewed_shared_accepted_taxon'
        WHEN h1.botanical_name IS NOT NULL AND trim(h1.botanical_name) != '' AND h1.botanical_name = h2.botanical_name THEN 'candidate_match_botanical_string_equality'
        ELSE 'unmatched'
    END AS identity_basis,
    h1.id AS herb_1_id,
    h1.english_name AS herb_1_name,
    h2.id AS herb_2_id,
    h2.english_name AS herb_2_name,
    s1.source_key AS source_1,
    p1.part_concept_id AS part_1_id,
    c_part1.concept_code AS part_1_code,
    c1.concept_code AS virya_1,
    sc1.source_expression AS raw_claim_1,
    m1.verification_status AS mapping_1_status,
    m1.mapping_type AS mapping_1_type,
    s2.source_key AS source_2,
    p2.part_concept_id AS part_2_id,
    c_part2.concept_code AS part_2_code,
    c2.concept_code AS virya_2,
    sc2.source_expression AS raw_claim_2,
    m2.verification_status AS mapping_2_status,
    m2.mapping_type AS mapping_2_type,
    CASE 
        WHEN p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NOT NULL AND p1.part_concept_id = p2.part_concept_id THEN 'exact_part_match'
        WHEN p1.part_concept_id IS NULL AND p2.part_concept_id IS NULL THEN 'both_parts_unspecified'
        ELSE 'unspecified_vs_specified_part'
    END AS part_comparison_scope,
    CASE 
        WHEN sr1.source_record_id = sr2.source_record_id THEN 'intra_source_record_divergence'
        WHEN s1.source_id = s2.source_id THEN 'intra_source_multi_record_divergence'
        ELSE 'cross_source_divergence'
    END AS source_scope,
    'REVIEWED_CANDIDATE_DIVERGENCE' AS divergence_tier
FROM herb_dravyaguna_properties p1
JOIN herbs h1 ON h1.id = p1.herb_id
JOIN concept_claim_mappings m1 ON m1.mapping_id = p1.mapping_id
JOIN dravyaguna_concepts c1 ON c1.concept_id = m1.concept_id
JOIN source_claims sc1 ON sc1.source_claim_id = m1.source_claim_id
JOIN source_records sr1 ON sr1.source_record_id = sc1.source_record_id
JOIN sources s1 ON s1.source_id = sr1.source_id
LEFT JOIN dravyaguna_concepts c_part1 ON c_part1.concept_id = p1.part_concept_id

JOIN herb_dravyaguna_properties p2 ON p2.herb_property_id > p1.herb_property_id
JOIN herbs h2 ON h2.id = p2.herb_id
JOIN concept_claim_mappings m2 ON m2.mapping_id = p2.mapping_id
JOIN dravyaguna_concepts c2 ON c2.concept_id = m2.concept_id
JOIN source_claims sc2 ON sc2.source_claim_id = m2.source_claim_id
JOIN source_records sr2 ON sr2.source_record_id = sc2.source_record_id
JOIN sources s2 ON s2.source_id = sr2.source_id
LEFT JOIN dravyaguna_concepts c_part2 ON c_part2.concept_id = p2.part_concept_id

WHERE (
    h1.id = h2.id
    OR (
        h1.botanical_name IS NOT NULL 
        AND trim(h1.botanical_name) != '' 
        AND h1.botanical_name = h2.botanical_name
    )
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
  AND sc1.source_claim_id != sc2.source_claim_id
  AND c1.concept_domain = 'virya' AND c2.concept_domain = 'virya'
  AND c1.concept_id != c2.concept_id
  -- Compatible plant-part scope (exclude distinct parts)
  AND NOT (p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NOT NULL AND p1.part_concept_id != p2.part_concept_id)
  -- Active presence status
  AND p1.source_presence_status = 'active'
  AND p2.source_presence_status = 'active'
  -- Source claims must be reviewed or verified (positive whitelist - neither is unreviewed)
  AND sc1.verification_status IN ('reviewed', 'verified')
  AND sc2.verification_status IN ('reviewed', 'verified')
  -- Mappings must be reviewed or verified (neither is unreviewed)
  AND m1.verification_status IN ('reviewed', 'verified')
  AND m2.verification_status IN ('reviewed', 'verified')
  -- Mapping quality filters (exclude partial and disputed)
  AND m1.mapping_type IN ('exact', 'broader', 'narrower')
  AND m2.mapping_type IN ('exact', 'broader', 'narrower')
  -- Tier 2 defining condition: Fails one or more Tier 3 criteria
  AND (
      m1.mapping_type IN ('broader', 'narrower') OR m2.mapping_type IN ('broader', 'narrower')
      OR m1.verification_status != 'verified' OR m2.verification_status != 'verified'
      OR s1.source_id = s2.source_id
      OR p1.part_concept_id IS NOT p2.part_concept_id
  );


-- ----------------------------------------------------------------------------
-- Tier 3 — Verified Source Disagreement
-- Criteria:
-- - Distinct source claims (sc1.source_claim_id != sc2.source_claim_id)
-- - Both mappings are verified (m.verification_status = 'verified')
-- - Both mapping types are exact (m.mapping_type = 'exact')
-- - Both underlying source claims are attested/reviewed (sc.verification_status IN ('reviewed', 'verified'))
-- - Distinct source authorities (s1.source_id != s2.source_id)
-- - Plant-part scopes are strictly identical, including the explicitly handled NULL/NULL case
-- - Presence status active on both sides
-- - Eligible identity conditions (same record, shared accepted taxon, or same non-empty botanical string)
-- - Exposes full audit metadata for both source claims and concept mappings
-- ----------------------------------------------------------------------------
SELECT DISTINCT
    COALESCE(h1.botanical_name, h1.english_name) AS botanical_identity,
    CASE 
        WHEN h1.id = h2.id THEN 'same_herb_record'
        WHEN EXISTS (
            SELECT 1 FROM herb_taxa ht1
            JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
            JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
            JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
            WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id
              AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
              AND sc_taxa1.verification_status = 'verified'
              AND sc_taxa2.verification_status = 'verified'
        ) THEN 'taxonomically_verified_shared_accepted_taxon'
        WHEN EXISTS (
            SELECT 1 FROM herb_taxa ht1
            JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
            JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
            JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
            WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id
              AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
              AND sc_taxa1.verification_status IN ('reviewed', 'verified')
              AND sc_taxa2.verification_status IN ('reviewed', 'verified')
        ) THEN 'taxonomically_reviewed_shared_accepted_taxon'
        WHEN h1.botanical_name IS NOT NULL AND trim(h1.botanical_name) != '' AND h1.botanical_name = h2.botanical_name THEN 'candidate_match_botanical_string_equality'
        ELSE 'unmatched'
    END AS identity_basis,
    h1.id AS herb_1_id,
    h1.english_name AS herb_1_name,
    h2.id AS herb_2_id,
    h2.english_name AS herb_2_name,
    s1.source_key AS source_1,
    p1.part_concept_id AS part_1_id,
    c_part1.concept_code AS part_1_code,
    c1.concept_code AS virya_1,
    sc1.source_expression AS raw_claim_1,
    sc1.reviewed_by AS claim_1_reviewed_by,
    sc1.reviewed_at AS claim_1_reviewed_at,
    m1.reviewed_by AS mapping_1_verified_by,
    m1.reviewed_at AS mapping_1_verified_at,
    s2.source_key AS source_2,
    p2.part_concept_id AS part_2_id,
    c_part2.concept_code AS part_2_code,
    c2.concept_code AS virya_2,
    sc2.source_expression AS raw_claim_2,
    sc2.reviewed_by AS claim_2_reviewed_by,
    sc2.reviewed_at AS claim_2_reviewed_at,
    m2.reviewed_by AS mapping_2_verified_by,
    m2.reviewed_at AS mapping_2_verified_at,
    CASE 
        WHEN p1.part_concept_id IS NOT NULL THEN 'exact_part_match'
        ELSE 'both_parts_unspecified'
    END AS part_comparison_scope,
    'cross_source_verified_disagreement' AS source_scope,
    'VERIFIED_SOURCE_DISAGREEMENT' AS divergence_tier
FROM herb_dravyaguna_properties p1
JOIN herbs h1 ON h1.id = p1.herb_id
JOIN concept_claim_mappings m1 ON m1.mapping_id = p1.mapping_id
JOIN dravyaguna_concepts c1 ON c1.concept_id = m1.concept_id
JOIN source_claims sc1 ON sc1.source_claim_id = m1.source_claim_id
JOIN source_records sr1 ON sr1.source_record_id = sc1.source_record_id
JOIN sources s1 ON s1.source_id = sr1.source_id
LEFT JOIN dravyaguna_concepts c_part1 ON c_part1.concept_id = p1.part_concept_id

JOIN herb_dravyaguna_properties p2 ON p2.herb_property_id > p1.herb_property_id
JOIN herbs h2 ON h2.id = p2.herb_id
JOIN concept_claim_mappings m2 ON m2.mapping_id = p2.mapping_id
JOIN dravyaguna_concepts c2 ON c2.concept_id = m2.concept_id
JOIN source_claims sc2 ON sc2.source_claim_id = m2.source_claim_id
JOIN source_records sr2 ON sr2.source_record_id = sc2.source_record_id
JOIN sources s2 ON s2.source_id = sr2.source_id
LEFT JOIN dravyaguna_concepts c_part2 ON c_part2.concept_id = p2.part_concept_id

WHERE (
    h1.id = h2.id
    OR (
        h1.botanical_name IS NOT NULL 
        AND trim(h1.botanical_name) != '' 
        AND h1.botanical_name = h2.botanical_name
    )
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
  AND sc1.source_claim_id != sc2.source_claim_id
  AND c1.concept_domain = 'virya' AND c2.concept_domain = 'virya'
  AND c1.concept_id != c2.concept_id
  -- Strictly identical part scope (either same part ID or both NULL)
  AND (p1.part_concept_id IS p2.part_concept_id)
  -- Plant part eligibility: Exclude different specified plant parts
  AND NOT (p1.part_concept_id IS NOT NULL AND p2.part_concept_id IS NOT NULL AND p1.part_concept_id != p2.part_concept_id)
  -- Distinct source authorities
  AND s1.source_id != s2.source_id
  -- Active presence status
  AND p1.source_presence_status = 'active'
  AND p2.source_presence_status = 'active'
  -- Positive whitelist for underlying source claim verification/review
  AND sc1.verification_status IN ('reviewed', 'verified')
  AND sc2.verification_status IN ('reviewed', 'verified')
  -- Strictly verified and exact mappings
  AND m1.verification_status = 'verified'
  AND m2.verification_status = 'verified'
  AND m1.mapping_type = 'exact'
  AND m2.mapping_type = 'exact';


-- ----------------------------------------------------------------------------
-- Audit Query — Same Source Claim Mapping Ambiguity (Conservative Same-Herb)
-- Isolates single source claims that are mapped to conflicting Virya concepts
-- on the exact same herb record (h1.id = h2.id).
-- Excluded from source-disagreement tiers because there is no conflict between
-- independent source claims.
-- ----------------------------------------------------------------------------
SELECT DISTINCT
    h1.id AS herb_id,
    COALESCE(h1.botanical_name, h1.english_name) AS botanical_identity,
    h1.english_name AS herb_name,
    'same_herb_record' AS identity_basis,
    sr1.source_record_id,
    s1.source_key AS source,
    sc1.source_claim_id,
    sc1.source_field,
    sc1.source_expression AS raw_claim,
    sc1.verification_status AS claim_verification_status,
    p1.part_concept_id AS part_1_id,
    p2.part_concept_id AS part_2_id,
    m1.mapping_id AS mapping_1_id,
    c1.concept_code AS virya_1,
    m1.verification_status AS mapping_1_status,
    m1.mapping_type AS mapping_1_type,
    m2.mapping_id AS mapping_2_id,
    c2.concept_code AS virya_2,
    m2.verification_status AS mapping_2_status,
    m2.mapping_type AS mapping_2_type,
    'HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY' AS audit_category
FROM herb_dravyaguna_properties p1
JOIN herbs h1 ON h1.id = p1.herb_id
JOIN concept_claim_mappings m1 ON m1.mapping_id = p1.mapping_id
JOIN dravyaguna_concepts c1 ON c1.concept_id = m1.concept_id
JOIN source_claims sc1 ON sc1.source_claim_id = m1.source_claim_id
JOIN source_records sr1 ON sr1.source_record_id = sc1.source_record_id
JOIN sources s1 ON s1.source_id = sr1.source_id

JOIN herb_dravyaguna_properties p2 ON p2.herb_property_id > p1.herb_property_id
JOIN herbs h2 ON h2.id = p2.herb_id
JOIN concept_claim_mappings m2 ON m2.mapping_id = p2.mapping_id
JOIN dravyaguna_concepts c2 ON c2.concept_id = m2.concept_id

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
