"""Herbal Almanac — Stage C.2 Work Package 5: Repository API & Presentation Services

Enforces ADR Decision 8 (Section 9):
- require_stage_c_schema_v3 capability gating before query execution
- herb_dravyaguna_profile() localized profile aggregator with multi-concept quarantine
- reconcile_herb_virya() Virya reconciliation report generator with active concept filtering
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Literal, TypedDict, cast

try:
    from .concept_catalog import (
        resolve_concept_display_label,
        resolve_concept_sanskrit_references,
    )
    from .schema_capability_gate import FeatureUnavailableError, require_stage_c_schema_v3
except ImportError:
    from concept_catalog import (
        resolve_concept_display_label,
        resolve_concept_sanskrit_references,
    )
    from schema_capability_gate import FeatureUnavailableError, require_stage_c_schema_v3

# Resolve path to accepted Stage C.1 virya_reconciliation.sql
_local_sql = Path(__file__).resolve().parent / "virya_reconciliation.sql"
_migrations_sql = Path(__file__).resolve().parent / "migrations" / "virya_reconciliation.sql"
RECONCILIATION_SQL_PATH = _local_sql if _local_sql.exists() else _migrations_sql


# ============================================================================
# Static Typing Definitions (ADR Revision 9 Section 9.B.2)
# ============================================================================

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
    part_comparison_scope: Literal[
        'exact_part_match',
        'different_part_or_unspecified_compatible',
        'both_parts_unspecified',
        'unspecified_vs_specified_part',
    ]
    source_scope: Literal[
        'same_source_internal_divergence',
        'cross_source_divergence',
        'cross_source_verified_disagreement',
        'intra_source_record_divergence',
        'intra_source_multi_record_divergence',
    ]
    divergence_tier: Literal[
        'TIER_1_UNREVIEWED_DIVERGENCE',
        'TIER_2_REVIEWED_DIVERGENCE',
        'VERIFIED_SOURCE_DISAGREEMENT',
        'UNREVIEWED_CANDIDATE_DIVERGENCE',
        'REVIEWED_CANDIDATE_DIVERGENCE',
    ]
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


class DravyagunaProfileProperty(TypedDict):
    property_id: int
    domain: str
    concept_code: str
    display_label: str
    display_label_status: str
    canonical_sanskrit_deva: str | None
    canonical_sanskrit_iast: str | None
    part_concept_code: str | None
    part_display_label: str | None
    mapping_type: str
    mapping_confidence: float | None
    mapping_status: str
    is_disputed: bool
    source_presence_status: str
    source_claim_id: int
    source_expression: str
    source_key: str


class DravyagunaProfileDoshaEffect(TypedDict):
    dosha_effect_id: int
    dosha_concept_code: str
    dosha_display_label: str
    effect_concept_code: str
    effect_display_label: str
    assertion_status: str
    is_disputed: bool
    source_presence_status: str
    source_claim_id: int
    source_expression: str


class DravyagunaProfilePlantPart(TypedDict):
    part_id: int
    concept_code: str
    display_label: str
    display_label_status: str
    canonical_sanskrit_deva: str | None
    canonical_sanskrit_iast: str | None
    source_presence_status: str
    mapping_status: str
    is_disputed: bool
    source_claim_id: int
    source_expression: str


class DravyagunaProfilePreparation(TypedDict):
    preparation_id: int
    prep_concept_code: str
    prep_display_label: str
    part_concept_code: str | None
    part_display_label: str | None
    source_presence_status: str
    mapping_status: str
    is_disputed: bool
    source_claim_id: int
    source_expression: str


class DravyagunaProfileIndication(TypedDict):
    indication_id: int
    indication_concept_code: str
    display_label: str
    display_label_status: str
    canonical_sanskrit_deva: str | None
    canonical_sanskrit_iast: str | None
    source_presence_status: str
    mapping_status: str
    is_disputed: bool
    source_claim_id: int
    source_expression: str


# ============================================================================
# Herb Dravyaguna Profile Service (ADR Section 9.A)
# ============================================================================

def herb_dravyaguna_profile(
    connection: sqlite3.Connection,
    herb_id: int,
    language: str = "en",
    include_disputed: bool = False,
    include_provisional: bool = False,
) -> dict[str, Any]:
    """Retrieves an active localized Dravyaguna profile for a target herb.

    Enforces:
    - Schema version 3 capability gating via require_stage_c_schema_v3()
    - PRAGMA foreign_keys = ON
    - Multi-concept active-status quarantine (unless include_provisional=True)
    - Disputed mapping filtering (unless include_disputed=True)
    - Localized display labels and canonical Sanskrit references (Devanagari/IAST)
    """
    require_stage_c_schema_v3(connection)
    connection.execute("PRAGMA foreign_keys = ON;")

    # Verify herb exists in Stage B herbs table
    herb_row = connection.execute(
        "SELECT id, english_name, botanical_name FROM herbs WHERE id = ?",
        (herb_id,),
    ).fetchone()
    if herb_row is None:
        raise KeyError(f"Herb with id {herb_id} not found")

    include_disp_int = 1 if include_disputed else 0
    include_prov_int = 1 if include_provisional else 0

    # 1. Dravyaguna Properties (Rasa, Guna, Virya, Vipaka, Prabhava, Karma)
    sql_properties = """
    SELECT 
        p.herb_property_id AS property_id,
        c.concept_id,
        c.concept_domain AS domain,
        c.concept_code,
        c_part.concept_id AS part_concept_id,
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
      AND (:include_provisional = 1 AND c.status IN ('active', 'provisional') OR c.status = 'active')
      AND (p.part_concept_id IS NULL OR (:include_provisional = 1 AND c_part.status IN ('active', 'provisional') OR c_part.status = 'active'))
      AND (:include_disputed = 1 OR m.mapping_type != 'disputed')
    ORDER BY p.herb_property_id ASC;
    """
    prop_rows = connection.execute(
        sql_properties,
        {
            "herb_id": herb_id,
            "include_disputed": include_disp_int,
            "include_provisional": include_prov_int,
        },
    ).fetchall()

    properties: list[DravyagunaProfileProperty] = []
    for r in prop_rows:
        prop_id, c_id, domain, c_code, p_cid, p_code, m_type, m_conf, m_status, is_disp, p_status, sc_id, sc_expr, s_key = r
        disp_info = resolve_concept_display_label(
            connection, c_id, language=language, allow_provisional=include_provisional
        )
        sanskrit_refs = resolve_concept_sanskrit_references(
            connection, c_id, allow_provisional=include_provisional
        )
        part_display: str | None = None
        if p_cid is not None:
            part_disp_info = resolve_concept_display_label(
                connection, p_cid, language=language, allow_provisional=include_provisional
            )
            part_display = part_disp_info["display_label"] if part_disp_info else p_code

        properties.append({
            "property_id": prop_id,
            "domain": domain,
            "concept_code": c_code,
            "display_label": disp_info["display_label"] if disp_info else c_code,
            "display_label_status": disp_info["display_label_status"] if disp_info else "unreviewed",
            "canonical_sanskrit_deva": sanskrit_refs["canonical_sanskrit_deva"] if sanskrit_refs else None,
            "canonical_sanskrit_iast": sanskrit_refs["canonical_sanskrit_iast"] if sanskrit_refs else None,
            "part_concept_code": p_code,
            "part_display_label": part_display,
            "mapping_type": m_type,
            "mapping_confidence": m_conf,
            "mapping_status": m_status,
            "is_disputed": bool(is_disp),
            "source_presence_status": p_status,
            "source_claim_id": sc_id,
            "source_expression": sc_expr,
            "source_key": s_key,
        })

    # 2. Dosha Effects
    sql_dosha = """
    SELECT 
        e.herb_dosha_effect_id AS dosha_effect_id,
        c_dosha.concept_id AS dosha_concept_id,
        c_dosha.concept_code AS dosha_concept_code,
        c_effect.concept_id AS effect_concept_id,
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
      AND (:include_provisional = 1 AND c_dosha.status IN ('active', 'provisional') OR c_dosha.status = 'active')
      AND (:include_provisional = 1 AND c_effect.status IN ('active', 'provisional') OR c_effect.status = 'active')
    ORDER BY e.herb_dosha_effect_id ASC;
    """
    dosha_rows = connection.execute(
        sql_dosha,
        {
            "herb_id": herb_id,
            "include_provisional": include_prov_int,
        },
    ).fetchall()

    dosha_effects: list[DravyagunaProfileDoshaEffect] = []
    for r in dosha_rows:
        eff_id, d_cid, d_code, e_cid, e_code, a_status, is_disp, e_status, sc_id, sc_expr = r
        d_disp_info = resolve_concept_display_label(
            connection, d_cid, language=language, allow_provisional=include_provisional
        )
        e_disp_info = resolve_concept_display_label(
            connection, e_cid, language=language, allow_provisional=include_provisional
        )
        dosha_effects.append({
            "dosha_effect_id": eff_id,
            "dosha_concept_code": d_code,
            "dosha_display_label": d_disp_info["display_label"] if d_disp_info else d_code,
            "effect_concept_code": e_code,
            "effect_display_label": e_disp_info["display_label"] if e_disp_info else e_code,
            "assertion_status": a_status,
            "is_disputed": bool(is_disp),
            "source_presence_status": e_status,
            "source_claim_id": sc_id,
            "source_expression": sc_expr,
        })

    # 3. Plant Parts
    sql_parts = """
    SELECT 
        pp.herb_part_id AS part_id,
        c.concept_id,
        c.concept_code,
        pp.source_presence_status,
        m.verification_status AS mapping_status,
        CASE WHEN m.mapping_type = 'disputed' THEN 1 ELSE 0 END AS is_disputed,
        sc.source_claim_id,
        sc.source_expression
    FROM herb_plant_parts pp
    JOIN concept_claim_mappings m ON m.mapping_id = pp.mapping_id
    JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
    JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
    WHERE pp.herb_id = :herb_id
      AND pp.source_presence_status = 'active'
      AND m.verification_status NOT IN ('superseded', 'rejected')
      AND sc.verification_status NOT IN ('superseded', 'rejected')
      AND (:include_provisional = 1 AND c.status IN ('active', 'provisional') OR c.status = 'active')
      AND (:include_disputed = 1 OR m.mapping_type != 'disputed')
    ORDER BY pp.herb_part_id ASC;
    """
    part_rows = connection.execute(
        sql_parts,
        {
            "herb_id": herb_id,
            "include_disputed": include_disp_int,
            "include_provisional": include_prov_int,
        },
    ).fetchall()

    plant_parts: list[DravyagunaProfilePlantPart] = []
    for r in part_rows:
        p_id, c_id, c_code, p_status, m_status, is_disp, sc_id, sc_expr = r
        disp_info = resolve_concept_display_label(
            connection, c_id, language=language, allow_provisional=include_provisional
        )
        sanskrit_refs = resolve_concept_sanskrit_references(
            connection, c_id, allow_provisional=include_provisional
        )
        plant_parts.append({
            "part_id": p_id,
            "concept_code": c_code,
            "display_label": disp_info["display_label"] if disp_info else c_code,
            "display_label_status": disp_info["display_label_status"] if disp_info else "unreviewed",
            "canonical_sanskrit_deva": sanskrit_refs["canonical_sanskrit_deva"] if sanskrit_refs else None,
            "canonical_sanskrit_iast": sanskrit_refs["canonical_sanskrit_iast"] if sanskrit_refs else None,
            "source_presence_status": p_status,
            "mapping_status": m_status,
            "is_disputed": bool(is_disp),
            "source_claim_id": sc_id,
            "source_expression": sc_expr,
        })

    # 4. Preparations
    sql_preparations = """
    SELECT 
        prep.herb_preparation_id AS preparation_id,
        c_prep.concept_id AS prep_concept_id,
        c_prep.concept_code AS prep_concept_code,
        c_part.concept_id AS part_concept_id,
        c_part.concept_code AS part_concept_code,
        prep.source_presence_status,
        m_prep.verification_status AS mapping_status,
        CASE 
            WHEN m_prep.mapping_type = 'disputed' 
              OR (m_part.mapping_type IS NOT NULL AND m_part.mapping_type = 'disputed') 
            THEN 1 ELSE 0 
        END AS is_disputed,
        sc.source_claim_id,
        sc.source_expression
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
      AND (:include_provisional = 1 AND c_prep.status IN ('active', 'provisional') OR c_prep.status = 'active')
      AND (prep.part_mapping_id IS NULL OR ((:include_provisional = 1 AND c_part.status IN ('active', 'provisional') OR c_part.status = 'active') AND m_part.verification_status NOT IN ('superseded', 'rejected')))
      AND (:include_disputed = 1 OR m_prep.mapping_type != 'disputed')
      AND (prep.part_mapping_id IS NULL OR :include_disputed = 1 OR m_part.mapping_type != 'disputed')
    ORDER BY prep.herb_preparation_id ASC;
    """
    prep_rows = connection.execute(
        sql_preparations,
        {
            "herb_id": herb_id,
            "include_disputed": include_disp_int,
            "include_provisional": include_prov_int,
        },
    ).fetchall()

    preparations: list[DravyagunaProfilePreparation] = []
    for r in prep_rows:
        prep_id, prep_cid, prep_code, part_cid, part_code, p_status, m_status, is_disp, sc_id, sc_expr = r
        disp_info = resolve_concept_display_label(
            connection, prep_cid, language=language, allow_provisional=include_provisional
        )
        part_display: str | None = None
        if part_cid is not None:
            part_disp_info = resolve_concept_display_label(
                connection, part_cid, language=language, allow_provisional=include_provisional
            )
            part_display = part_disp_info["display_label"] if part_disp_info else part_code

        preparations.append({
            "preparation_id": prep_id,
            "prep_concept_code": prep_code,
            "prep_display_label": disp_info["display_label"] if disp_info else prep_code,
            "part_concept_code": part_code,
            "part_display_label": part_display,
            "source_presence_status": p_status,
            "mapping_status": m_status,
            "is_disputed": bool(is_disp),
            "source_claim_id": sc_id,
            "source_expression": sc_expr,
        })

    # 5. Indications
    sql_indications = """
    SELECT 
        ind.herb_indication_id AS indication_id,
        c.concept_id,
        c.concept_code AS indication_concept_code,
        ind.source_presence_status,
        m.verification_status AS mapping_status,
        CASE WHEN m.mapping_type = 'disputed' THEN 1 ELSE 0 END AS is_disputed,
        sc.source_claim_id,
        sc.source_expression
    FROM herb_indications ind
    JOIN concept_claim_mappings m ON m.mapping_id = ind.mapping_id
    JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
    JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
    WHERE ind.herb_id = :herb_id
      AND ind.source_presence_status = 'active'
      AND m.verification_status NOT IN ('superseded', 'rejected')
      AND sc.verification_status NOT IN ('superseded', 'rejected')
      AND (:include_provisional = 1 AND c.status IN ('active', 'provisional') OR c.status = 'active')
      AND (:include_disputed = 1 OR m.mapping_type != 'disputed')
    ORDER BY ind.herb_indication_id ASC;
    """
    ind_rows = connection.execute(
        sql_indications,
        {
            "herb_id": herb_id,
            "include_disputed": include_disp_int,
            "include_provisional": include_prov_int,
        },
    ).fetchall()

    indications: list[DravyagunaProfileIndication] = []
    for r in ind_rows:
        ind_id, c_id, ind_code, ind_status, m_status, is_disp, sc_id, sc_expr = r
        disp_info = resolve_concept_display_label(
            connection, c_id, language=language, allow_provisional=include_provisional
        )
        sanskrit_refs = resolve_concept_sanskrit_references(
            connection, c_id, allow_provisional=include_provisional
        )
        indications.append({
            "indication_id": ind_id,
            "indication_concept_code": ind_code,
            "display_label": disp_info["display_label"] if disp_info else ind_code,
            "display_label_status": disp_info["display_label_status"] if disp_info else "unreviewed",
            "canonical_sanskrit_deva": sanskrit_refs["canonical_sanskrit_deva"] if sanskrit_refs else None,
            "canonical_sanskrit_iast": sanskrit_refs["canonical_sanskrit_iast"] if sanskrit_refs else None,
            "source_presence_status": ind_status,
            "mapping_status": m_status,
            "is_disputed": bool(is_disp),
            "source_claim_id": sc_id,
            "source_expression": sc_expr,
        })

    return {
        "herb_id": herb_id,
        "english_name": herb_row[1],
        "botanical_name": herb_row[2],
        "language": language,
        "properties": properties,
        "dosha_effects": dosha_effects,
        "plant_parts": plant_parts,
        "preparations": preparations,
        "indications": indications,
    }


# ============================================================================
# Virya Reconciliation Service (ADR Section 9.B)
# ============================================================================

def _load_virya_reconciliation_queries() -> tuple[str, str, str, str]:
    """Reads and parses the four accepted queries from virya_reconciliation.sql."""
    if not RECONCILIATION_SQL_PATH.exists():
        raise FileNotFoundError(f"Missing reconciliation queries file: {RECONCILIATION_SQL_PATH}")
    script = RECONCILIATION_SQL_PATH.read_text(encoding="utf-8")
    queries = [q.strip() for q in script.split(";") if "SELECT" in q]
    if len(queries) < 4:
        raise ValueError(f"Expected at least 4 queries in {RECONCILIATION_SQL_PATH}, found {len(queries)}")
    return queries[0], queries[1], queries[2], queries[3]


def reconcile_herb_virya(
    connection: sqlite3.Connection,
    herb_id: int,
) -> ViryaReconciliationReport:
    """Executes the 4 accepted Virya reconciliation queries for a target herb.

    Enforces:
    - Schema version 3 capability gating via require_stage_c_schema_v3()
    - PRAGMA foreign_keys = ON
    - Active concept filtering (ADR Section 9.B.3): filters out rows where
      virya_1, virya_2, part_1_code, or part_2_code reference non-active concepts
    - Deterministic summary count reconciliation across Tiers 1-3 and Query 4
    """
    require_stage_c_schema_v3(connection)
    connection.execute("PRAGMA foreign_keys = ON;")

    # Verify herb exists
    herb_row = connection.execute(
        "SELECT id FROM herbs WHERE id = ?",
        (herb_id,),
    ).fetchone()
    if herb_row is None:
        raise KeyError(f"Herb with id {herb_id} not found")

    q1, q2, q3, q4 = _load_virya_reconciliation_queries()

    # Active concept lookup for executor contract filtering
    active_concept_codes = {
        r[0]
        for r in connection.execute(
            "SELECT concept_code FROM dravyaguna_concepts WHERE status = 'active'"
        ).fetchall()
    }
    active_concept_ids = {
        r[0]
        for r in connection.execute(
            "SELECT concept_id FROM dravyaguna_concepts WHERE status = 'active'"
        ).fetchall()
    }

    # Execute Tier 1 (Unreviewed Candidate Divergence)
    sql_t1 = f"SELECT * FROM (\n{q1}\n) AS q WHERE q.herb_1_id = ? OR q.herb_2_id = ?"
    cur1 = connection.execute(sql_t1, (herb_id, herb_id))
    cols1 = [c[0] for c in cur1.description]
    tier_1_raw = [dict(zip(cols1, r)) for r in cur1.fetchall()]

    tier_1_rows: list[ViryaPairwiseDivergenceRecord] = []
    for r in tier_1_raw:
        if r["virya_1"] not in active_concept_codes or r["virya_2"] not in active_concept_codes:
            continue
        if r.get("part_1_code") and r["part_1_code"] not in active_concept_codes:
            continue
        if r.get("part_2_code") and r["part_2_code"] not in active_concept_codes:
            continue
        tier_1_rows.append({
            "botanical_identity": r["botanical_identity"],
            "identity_basis": r["identity_basis"],
            "herb_1_id": r["herb_1_id"],
            "herb_1_name": r["herb_1_name"],
            "herb_2_id": r["herb_2_id"],
            "herb_2_name": r["herb_2_name"],
            "source_1": r["source_1"],
            "part_1_id": r.get("part_1_id"),
            "part_1_code": r.get("part_1_code"),
            "virya_1": r["virya_1"],
            "raw_claim_1": r["raw_claim_1"],
            "mapping_1_status": r["mapping_1_status"],
            "mapping_1_type": r["mapping_1_type"],
            "source_2": r["source_2"],
            "part_2_id": r.get("part_2_id"),
            "part_2_code": r.get("part_2_code"),
            "virya_2": r["virya_2"],
            "raw_claim_2": r["raw_claim_2"],
            "mapping_2_status": r["mapping_2_status"],
            "mapping_2_type": r["mapping_2_type"],
            "part_comparison_scope": r["part_comparison_scope"],
            "source_scope": r["source_scope"],
            "divergence_tier": r["divergence_tier"],
            "claim_1_reviewed_by": None,
            "claim_1_reviewed_at": None,
            "mapping_1_verified_by": None,
            "mapping_1_verified_at": None,
            "claim_2_reviewed_by": None,
            "claim_2_reviewed_at": None,
            "mapping_2_verified_by": None,
            "mapping_2_verified_at": None,
        })

    # Execute Tier 2 (Reviewed Candidate Divergence)
    sql_t2 = f"SELECT * FROM (\n{q2}\n) AS q WHERE q.herb_1_id = ? OR q.herb_2_id = ?"
    cur2 = connection.execute(sql_t2, (herb_id, herb_id))
    cols2 = [c[0] for c in cur2.description]
    tier_2_raw = [dict(zip(cols2, r)) for r in cur2.fetchall()]

    tier_2_rows: list[ViryaPairwiseDivergenceRecord] = []
    for r in tier_2_raw:
        if r["virya_1"] not in active_concept_codes or r["virya_2"] not in active_concept_codes:
            continue
        if r.get("part_1_code") and r["part_1_code"] not in active_concept_codes:
            continue
        if r.get("part_2_code") and r["part_2_code"] not in active_concept_codes:
            continue
        tier_2_rows.append({
            "botanical_identity": r["botanical_identity"],
            "identity_basis": r["identity_basis"],
            "herb_1_id": r["herb_1_id"],
            "herb_1_name": r["herb_1_name"],
            "herb_2_id": r["herb_2_id"],
            "herb_2_name": r["herb_2_name"],
            "source_1": r["source_1"],
            "part_1_id": r.get("part_1_id"),
            "part_1_code": r.get("part_1_code"),
            "virya_1": r["virya_1"],
            "raw_claim_1": r["raw_claim_1"],
            "mapping_1_status": r["mapping_1_status"],
            "mapping_1_type": r["mapping_1_type"],
            "source_2": r["source_2"],
            "part_2_id": r.get("part_2_id"),
            "part_2_code": r.get("part_2_code"),
            "virya_2": r["virya_2"],
            "raw_claim_2": r["raw_claim_2"],
            "mapping_2_status": r["mapping_2_status"],
            "mapping_2_type": r["mapping_2_type"],
            "part_comparison_scope": r["part_comparison_scope"],
            "source_scope": r["source_scope"],
            "divergence_tier": r["divergence_tier"],
            "claim_1_reviewed_by": None,
            "claim_1_reviewed_at": None,
            "mapping_1_verified_by": None,
            "mapping_1_verified_at": None,
            "claim_2_reviewed_by": None,
            "claim_2_reviewed_at": None,
            "mapping_2_verified_by": None,
            "mapping_2_verified_at": None,
        })

    # Execute Tier 3 (Verified Source Disagreement)
    sql_t3 = f"SELECT * FROM (\n{q3}\n) AS q WHERE q.herb_1_id = ? OR q.herb_2_id = ?"
    cur3 = connection.execute(sql_t3, (herb_id, herb_id))
    cols3 = [c[0] for c in cur3.description]
    tier_3_raw = [dict(zip(cols3, r)) for r in cur3.fetchall()]

    tier_3_rows: list[ViryaPairwiseDivergenceRecord] = []
    for r in tier_3_raw:
        if r["virya_1"] not in active_concept_codes or r["virya_2"] not in active_concept_codes:
            continue
        if r.get("part_1_code") and r["part_1_code"] not in active_concept_codes:
            continue
        if r.get("part_2_code") and r["part_2_code"] not in active_concept_codes:
            continue
        tier_3_rows.append({
            "botanical_identity": r["botanical_identity"],
            "identity_basis": r["identity_basis"],
            "herb_1_id": r["herb_1_id"],
            "herb_1_name": r["herb_1_name"],
            "herb_2_id": r["herb_2_id"],
            "herb_2_name": r["herb_2_name"],
            "source_1": r["source_1"],
            "part_1_id": r.get("part_1_id"),
            "part_1_code": r.get("part_1_code"),
            "virya_1": r["virya_1"],
            "raw_claim_1": r["raw_claim_1"],
            "mapping_1_status": "verified",
            "mapping_1_type": "exact",
            "source_2": r["source_2"],
            "part_2_id": r.get("part_2_id"),
            "part_2_code": r.get("part_2_code"),
            "virya_2": r["virya_2"],
            "raw_claim_2": r["raw_claim_2"],
            "mapping_2_status": "verified",
            "mapping_2_type": "exact",
            "part_comparison_scope": r["part_comparison_scope"],
            "source_scope": r["source_scope"],
            "divergence_tier": r["divergence_tier"],
            "claim_1_reviewed_by": r.get("claim_1_reviewed_by"),
            "claim_1_reviewed_at": r.get("claim_1_reviewed_at"),
            "mapping_1_verified_by": r.get("mapping_1_verified_by"),
            "mapping_1_verified_at": r.get("mapping_1_verified_at"),
            "claim_2_reviewed_by": r.get("claim_2_reviewed_by"),
            "claim_2_reviewed_at": r.get("claim_2_reviewed_at"),
            "mapping_2_verified_by": r.get("mapping_2_verified_by"),
            "mapping_2_verified_at": r.get("mapping_2_verified_at"),
        })

    # Execute Query 4 (Same-Claim Ambiguity Audit)
    sql_t4 = f"SELECT * FROM (\n{q4}\n) AS q WHERE q.herb_id = ?"
    cur4 = connection.execute(sql_t4, (herb_id,))
    cols4 = [c[0] for c in cur4.description]
    ambiguity_raw = [dict(zip(cols4, r)) for r in cur4.fetchall()]

    ambiguity_rows: list[ViryaSameClaimAmbiguityRecord] = []
    for r in ambiguity_raw:
        if r["virya_1"] not in active_concept_codes or r["virya_2"] not in active_concept_codes:
            continue
        if r.get("part_1_id") and r["part_1_id"] not in active_concept_ids:
            continue
        if r.get("part_2_id") and r["part_2_id"] not in active_concept_ids:
            continue
        ambiguity_rows.append({
            "herb_id": r["herb_id"],
            "botanical_identity": r["botanical_identity"],
            "herb_name": r["herb_name"],
            "identity_basis": "same_herb_record",
            "source_record_id": r["source_record_id"],
            "source": r["source"],
            "source_claim_id": r["source_claim_id"],
            "source_field": r["source_field"],
            "raw_claim": r["raw_claim"],
            "claim_verification_status": r["claim_verification_status"],
            "part_1_id": r.get("part_1_id"),
            "part_2_id": r.get("part_2_id"),
            "mapping_1_id": r["mapping_1_id"],
            "virya_1": r["virya_1"],
            "mapping_1_status": r["mapping_1_status"],
            "mapping_1_type": r["mapping_1_type"],
            "mapping_2_id": r["mapping_2_id"],
            "virya_2": r["virya_2"],
            "mapping_2_status": r["mapping_2_status"],
            "mapping_2_type": r["mapping_2_type"],
            "audit_category": "HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY",
        })

    tier_1_count = len(tier_1_rows)
    tier_2_count = len(tier_2_rows)
    tier_3_count = len(tier_3_rows)
    ambiguity_count = len(ambiguity_rows)
    total_reconciled = tier_1_count + tier_2_count + tier_3_count + ambiguity_count

    summary: ViryaReconciliationSummary = {
        "tier_1_unreviewed_divergence_count": tier_1_count,
        "tier_2_reviewed_divergence_count": tier_2_count,
        "tier_3_verified_disagreement_count": tier_3_count,
        "same_claim_mapping_ambiguity_count": ambiguity_count,
        "total_reconciled_pairs": total_reconciled,
    }

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "target_herb_id": herb_id,
        "reconciled_at": now_iso,
        "summary_counts": summary,
        "tier_1_unreviewed_divergence": tier_1_rows,
        "tier_2_reviewed_divergence": tier_2_rows,
        "tier_3_verified_disagreements": tier_3_rows,
        "same_claim_ambiguities": ambiguity_rows,
    }
