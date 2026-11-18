"""
Herbal Almanac — Stage C.2 Work Package 4 (WP-4)
Stage B -> Stage C Semantic Backfill & Ingestion Engine
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any

from .schema_capability_gate import require_stage_c_schema_v3
from .concept_catalog import seed_canonical_concept_catalog, normalize_label


# ============================================================================
# 1. Stage B Legacy Tables Specification
# ============================================================================

STAGE_B_TABLES: tuple[str, ...] = (
    "herbs",
    "illness",
    "treatment",
    "herb_attributes",
    "herb_doshas",
    "sources",
    "source_records",
    "source_claims",
    "legacy_herb_map",
    "herb_names",
    "taxa",
    "taxon_relationships",
    "herb_taxa",
)


def _validate_iso_utc_timestamp(ts: str) -> None:
    """Validates that a timestamp is a non-empty ISO-8601 string in UTC."""
    if not isinstance(ts, str) or not ts.strip():
        raise ValueError(f"Timestamp 'now' must be a non-empty ISO-8601 string; got {ts!r}")
    s = ts.strip()
    if not (s.endswith("Z") or s.endswith("+00:00")):
        raise ValueError(f"Timestamp must explicitly terminate with UTC offset 'Z' or '+00:00'; got {ts!r}")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
            raise ValueError("Timestamp must represent zero-offset UTC time")
    except Exception as exc:
        raise ValueError(f"Invalid UTC ISO-8601 timestamp '{ts}': {exc}") from exc


def _check_preconditions(connection: sqlite3.Connection) -> None:
    """Verifies schema version 3, foreign keys enabled, and active transaction."""
    require_stage_c_schema_v3(connection)

    fk_row = connection.execute("PRAGMA foreign_keys;").fetchone()
    if fk_row is None or fk_row[0] != 1:
        raise RuntimeError("Foreign key enforcement must be enabled (PRAGMA foreign_keys = ON)")

    if not connection.in_transaction:
        raise RuntimeError(
            "Database connection must have an active transaction (e.g. BEGIN IMMEDIATE) before executing backfill operations."
        )


# ============================================================================
# 2. Stage B Table Invariance Checker
# ============================================================================

def capture_stage_b_table_snapshot(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Captures schema, row counts, and cryptographic row hashes for all 13 Stage B legacy tables."""
    snapshot: dict[str, dict[str, Any]] = {}

    for tbl in STAGE_B_TABLES:
        col_rows = connection.execute(f"PRAGMA table_info({tbl});").fetchall()
        if not col_rows:
            raise KeyError(f"Required Stage B table '{tbl}' does not exist in database.")
        col_names = [r[1] for r in col_rows]
        col_types = {r[1]: r[2] for r in col_rows}

        count = connection.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0]

        order_by = ", ".join(col_names) if col_names else "rowid"
        rows = connection.execute(f"SELECT * FROM {tbl} ORDER BY {order_by};").fetchall()

        hasher = hashlib.sha256()
        for row in rows:
            hasher.update(str(tuple(row)).encode("utf-8"))
        row_hash = hasher.hexdigest()

        snapshot[tbl] = {
            "columns": col_names,
            "column_types": col_types,
            "count": count,
            "row_hash": row_hash,
        }

    return snapshot


def verify_stage_b_row_invariance(
    before_snapshot: dict[str, dict[str, Any]],
    after_snapshot: dict[str, dict[str, Any]],
) -> None:
    """Compares pre- and post-operation snapshots to guarantee zero unintended mutations to Stage B tables.

    Raises:
        AssertionError: If any Stage B table suffered row count modifications, schema alterations,
                        or row hash divergences.
    """
    for tbl in STAGE_B_TABLES:
        if tbl not in before_snapshot:
            raise AssertionError(f"Pre-snapshot missing Stage B table '{tbl}'")
        if tbl not in after_snapshot:
            raise AssertionError(f"Post-snapshot missing Stage B table '{tbl}'")

        before_meta = before_snapshot[tbl]
        after_meta = after_snapshot[tbl]

        # Schema invariance
        if before_meta["columns"] != after_meta["columns"]:
            raise AssertionError(
                f"Stage B Invariance Violation on table '{tbl}': column list mutated from "
                f"{before_meta['columns']} to {after_meta['columns']}"
            )
        if before_meta["column_types"] != after_meta["column_types"]:
            raise AssertionError(
                f"Stage B Invariance Violation on table '{tbl}': column types mutated from "
                f"{before_meta['column_types']} to {after_meta['column_types']}"
            )

        # Row count invariance
        if before_meta["count"] != after_meta["count"]:
            raise AssertionError(
                f"Stage B Invariance Violation on table '{tbl}': row count mutated from "
                f"{before_meta['count']} to {after_meta['count']}"
            )

        # Content hash invariance
        if before_meta["row_hash"] != after_meta["row_hash"]:
            raise AssertionError(
                f"Stage B Invariance Violation on table '{tbl}': content row hash divergence detected! "
                f"Expected {before_meta['row_hash']}, got {after_meta['row_hash']}"
            )


# ============================================================================
# 3. Domain Expression Parsing & Concept Resolution
# ============================================================================

# Common Sanskrit / Hindi / English variant synonyms mapping directly to canonical concepts
EXPLICIT_LEXICAL_SYNONYMS: dict[tuple[str, str], str] = {
    # Rasa
    ("rasa", "svadu"): "RASA_MADHURA",
    ("rasa", "svādu"): "RASA_MADHURA",
    ("rasa", "स्वादु"): "RASA_MADHURA",
    ("rasa", "tuvara"): "RASA_KASHAYA",
    ("rasa", "तुवर"): "RASA_KASHAYA",
    # Guna
    ("guna", "aguru"): "GUNA_GURU",
    ("guna", "अगुरु"): "GUNA_GURU",
    ("guna", "ruksha"): "GUNA_RUKSHA",
    ("guna", "rukṣa"): "GUNA_RUKSHA",
    ("guna", "rūkṣa"): "GUNA_RUKSHA",
    ("guna", "रुक्ष"): "GUNA_RUKSHA",
    ("guna", "pichchhila"): "GUNA_PICCHILA",
    ("guna", "picchila"): "GUNA_PICCHILA",
    ("guna", "पिच्छिल"): "GUNA_PICCHILA",
    # Plant Part
    ("plant_part", "leaf"): "PART_LEAF",
    ("plant_part", "leaves"): "PART_LEAF",
    ("plant_part", "patra"): "PART_LEAF",
    ("plant_part", "पत्र"): "PART_LEAF",
    ("plant_part", "root"): "PART_ROOT",
    ("plant_part", "roots"): "PART_ROOT",
    ("plant_part", "mula"): "PART_ROOT",
    ("plant_part", "mūla"): "PART_ROOT",
    ("plant_part", "मूल"): "PART_ROOT",
    ("plant_part", "seed"): "PART_SEED",
    ("plant_part", "seeds"): "PART_SEED",
    ("plant_part", "bija"): "PART_SEED",
    ("plant_part", "bīja"): "PART_SEED",
    ("plant_part", "बीज"): "PART_SEED",
    ("plant_part", "fruit"): "PART_FRUIT",
    ("plant_part", "phala"): "PART_FRUIT",
    ("plant_part", "फल"): "PART_FRUIT",
    ("plant_part", "bark"): "PART_STEM_BARK",
    ("plant_part", "tvak"): "PART_STEM_BARK",
    ("plant_part", "त्वक्"): "PART_STEM_BARK",
    ("plant_part", "flower"): "PART_FLOWER",
    ("plant_part", "pushpa"): "PART_FLOWER",
    ("plant_part", "puṣpa"): "PART_FLOWER",
    ("plant_part", "पुष्प"): "PART_FLOWER",
    ("plant_part", "rhizome"): "PART_RHIZOME",
    ("plant_part", "stem"): "PART_STEM",
    # Preparation Form
    ("preparation_form", "churna"): "PREP_CHURNA",
    ("preparation_form", "cūrṇa"): "PREP_CHURNA",
    ("preparation_form", "चूर्ण"): "PREP_CHURNA",
    ("preparation_form", "guggulu"): "PREP_GUGGULU",
    ("preparation_form", "गुग्गुलु"): "PREP_GUGGULU",
    ("preparation_form", "kvatha"): "PREP_KVATHA",
    ("preparation_form", "kvātha"): "PREP_KVATHA",
    ("preparation_form", "क्वाथ"): "PREP_KVATHA",
    ("preparation_form", "taila"): "PREP_TAILA",
    ("preparation_form", "तैल"): "PREP_TAILA",
    ("preparation_form", "ghrita"): "PREP_GHRITA",
    ("preparation_form", "घृत"): "PREP_GHRITA",
    ("preparation_form", "asava"): "PREP_ASAVA",
    ("preparation_form", "arista"): "PREP_ARISHTA",
    ("preparation_form", "arighta"): "PREP_ARISHTA",
}


def _resolve_claim_domain_and_table(claim_type: str, source_field: str) -> tuple[str, str] | None:
    """Maps a source claim's field/type to its concept domain and target relationship table."""
    fld = source_field or ""
    if fld.startswith("Rasa"):
        return "rasa", "herb_dravyaguna_properties"
    if fld.startswith("Guna"):
        return "guna", "herb_dravyaguna_properties"
    if fld.startswith("Virya"):
        return "virya", "herb_dravyaguna_properties"
    if fld.startswith("Vipaka"):
        return "vipaka", "herb_dravyaguna_properties"
    if fld.startswith("Prabhava"):
        return "prabhava", "herb_dravyaguna_properties"
    if fld.startswith("Karma"):
        return "karma", "herb_dravyaguna_properties"
    if fld.startswith("Parts Used") or fld.startswith("Part Used"):
        return "plant_part", "herb_plant_parts"
    if fld.startswith("Dosage Formulation") or fld.startswith("Preparation"):
        return "preparation_form", "herb_preparations"
    if fld.startswith("Therapeutic Usage") or fld.startswith("Vyadhi") or fld.startswith("Indication"):
        return "indication", "herb_indications"
    if fld.startswith("Doshakarma") or claim_type == "dosha_expression":
        return "dosha", "herb_dosha_effects"
    return None


def _clean_and_tokenize_expression(expression: str) -> list[str]:
    """Splits compound textual expressions by standard separators."""
    if not expression:
        return []
    parts = re.split(r'[/,;|]', expression)
    return [p.strip() for p in parts if p.strip()]


def _match_concept_in_domain(
    domain: str,
    token: str,
    domain_labels: dict[tuple[str, str], tuple[int, str]],
    concept_codes: dict[str, int],
) -> tuple[int, str] | None:
    """Matches a token within a domain against normalized concept labels and synonyms."""
    norm = normalize_label(token)
    if not norm:
        return None

    # 1. Direct label lookup
    if (domain, norm) in domain_labels:
        return domain_labels[(domain, norm)]

    # 2. Explicit synonym lookup
    if (domain, norm) in EXPLICIT_LEXICAL_SYNONYMS:
        syn_code = EXPLICIT_LEXICAL_SYNONYMS[(domain, norm)]
        if syn_code in concept_codes:
            return concept_codes[syn_code], syn_code

    # 3. Strip domain noun suffixes
    suffixes: dict[str, list[str]] = {
        "virya": [" virya", " vīrya", " वीर्य", "virya"],
        "vipaka": [" vipaka", " vipāka", " विपाक", "vipaka"],
        "rasa": [" rasa", " ras", " रस", "rasa"],
        "guna": [" guna", " guṇa", " गुण", "guna"],
        "karma": [" karma", " karm", " कर्म", "karma"],
        "preparation_form": [" formulation", " form", " dosage"],
        "plant_part": [" part used", " part", " used"],
    }
    for sfx in suffixes.get(domain, []):
        if norm.endswith(sfx):
            sub = norm[:-len(sfx)].strip()
            if (domain, sub) in domain_labels:
                return domain_labels[(domain, sub)]
            if (domain, sub) in EXPLICIT_LEXICAL_SYNONYMS:
                syn_code = EXPLICIT_LEXICAL_SYNONYMS[(domain, sub)]
                if syn_code in concept_codes:
                    return concept_codes[syn_code], syn_code

    # 4. Check if token matches concept code token
    for code, cid in concept_codes.items():
        if code.startswith(f"{domain.upper()}_"):
            suffix_token = code[len(domain) + 1:].lower()
            if norm == suffix_token:
                return cid, code

    return None


def _decompose_dosha_expression(
    expression: str,
    dosha_concepts: dict[str, int],
    effect_concepts: dict[str, int],
) -> list[tuple[int, int]]:
    """Decomposes compound Dravyaguna Doshakarma expressions into (dosha_concept_id, effect_concept_id) pairs."""
    pairs: set[tuple[int, int]] = set()
    tokens = _clean_and_tokenize_expression(expression)

    for tok in tokens:
        p = tok.lower()

        # Determine directional effect
        # Decreases (Shamana / Hara) vs Increases (Vardhaka / Kopana / Kara)
        if any(w in p for w in ["vardhak", "kopan", "vriddhi", "kara", "वर्धक", "कोपन", "वृद्धि"]):
            eff_code = "EFFECT_INCREASE"
        else:
            eff_code = "EFFECT_DECREASE"

        if eff_code not in effect_concepts:
            continue
        eff_id = effect_concepts[eff_code]

        # Determine target dosha(s)
        target_doshas: list[str] = []
        if any(w in p for w in ["tridosh", "त्रिदोष", "sarvadosh", "सर्वदोष"]):
            target_doshas = ["DOSHA_VATA", "DOSHA_PITTA", "DOSHA_KAPHA"]
        else:
            if any(w in p for w in ["vata", "vāt", "वात", "vayu"]):
                target_doshas.append("DOSHA_VATA")
            if any(w in p for w in ["pitta", "pitt", "पित्त"]):
                target_doshas.append("DOSHA_PITTA")
            if any(w in p for w in ["kapha", "kaph", "sleshma", "śleṣma", "कफ", "श्लेष्म"]):
                target_doshas.append("DOSHA_KAPHA")

        for d_code in target_doshas:
            if d_code in dosha_concepts:
                pairs.add((dosha_concepts[d_code], eff_id))

    return sorted(pairs)


# ============================================================================
# 4. Deterministic Semantic Backfill Seeder
# ============================================================================

def run_stage_c_semantic_backfill(
    connection: sqlite3.Connection,
    now: str,
) -> dict[str, int]:
    """Scans existing Stage B source_claims and populates Stage C semantic mappings and relationship tables.

    Rules:
    - Preconditions: Stage C Schema v3, PRAGMA foreign_keys = ON, active transaction.
    - Idempotency: Multiple runs against the same database insert 0 duplicate rows.
    - Calibrated Mapping Rule (ADR Decision 4):
        mapping_method = 'lexicon_exact'
        mapping_confidence = NULL
        verification_status = 'unreviewed'
    - Rollback Safety: Rolls back to SAVEPOINT wp4_backfill on any error, leaving Stage B intact.
    - Audit Logging: Inserts a completed 'ingest_batch' record in source_reconciliation_events.

    Returns:
        Structured metrics dictionary.
    """
    _check_preconditions(connection)
    _validate_iso_utc_timestamp(now)

    # Use a savepoint to guarantee atomic failure rollback
    connection.execute("SAVEPOINT wp4_backfill;")

    try:
        # Ensure canonical concept catalog is seeded
        has_concepts = connection.execute("SELECT COUNT(*) FROM dravyaguna_concepts;").fetchone()[0]
        if has_concepts == 0:
            seed_canonical_concept_catalog(connection)

        # Build concept lookup caches
        domain_labels: dict[tuple[str, str], tuple[int, str]] = {}
        concept_codes: dict[str, int] = {}
        dosha_concepts: dict[str, int] = {}
        effect_concepts: dict[str, int] = {}

        concept_rows = connection.execute(
            "SELECT concept_id, concept_code, concept_domain, status FROM dravyaguna_concepts WHERE status = 'active';"
        ).fetchall()
        for cid, ccode, cdomain, _ in concept_rows:
            concept_codes[ccode] = cid
            if cdomain == "dosha":
                dosha_concepts[ccode] = cid
            elif cdomain == "dosha_effect":
                effect_concepts[ccode] = cid

        label_rows = connection.execute(
            """
            SELECT cl.normalized_label, c.concept_id, c.concept_code, c.concept_domain
            FROM concept_labels cl
            JOIN dravyaguna_concepts c ON c.concept_id = cl.concept_id
            WHERE c.status = 'active';
            """
        ).fetchall()
        for norm_label, cid, ccode, cdomain in label_rows:
            domain_labels[(cdomain, norm_label)] = (cid, ccode)

        # Fetch non-superseded source claims
        claims = connection.execute(
            """
            SELECT sc.source_claim_id, sc.source_record_id, sr.source_id, sc.claim_type, sc.source_field, sc.source_expression
            FROM source_claims sc
            JOIN source_records sr ON sr.source_record_id = sc.source_record_id
            WHERE sc.verification_status != 'superseded'
            ORDER BY sc.source_claim_id ASC;
            """
        ).fetchall()

        processed_claims = len(claims)
        inserted_mappings = 0
        inserted_properties = 0
        inserted_dosha_effects = 0
        inserted_plant_parts = 0
        inserted_preparations = 0
        inserted_indications = 0

        # Track sources evaluated for audit logging
        sources_evaluated: dict[int, dict[str, int]] = {}

        for claim_id, record_id, source_id, claim_type, source_field, source_expression in claims:
            if source_id not in sources_evaluated:
                sources_evaluated[source_id] = {"claims": 0, "properties": 0}
            sources_evaluated[source_id]["claims"] += 1

            domain_table = _resolve_claim_domain_and_table(claim_type, source_field)
            if domain_table is None:
                continue

            domain, rel_table = domain_table

            # Find herbs associated with this claim per Stage C provenance triggers
            herb_rows = connection.execute(
                """
                SELECT h.id
                FROM legacy_herb_map lhm
                JOIN herbs h ON h.id = lhm.legacy_herb_id
                JOIN source_records sr ON sr.source_record_id = ?
                JOIN sources s ON s.source_id = ?
                WHERE (
                    (h.source_record_id IS NOT NULL 
                     AND s.source_key = TRIM(h.source)
                     AND sr.external_record_key = CAST(h.source_record_id AS TEXT))
                    OR
                    (h.source_record_id IS NULL 
                     AND s.source_key = 'manual' 
                     AND sr.raw_artifact_ref = 'legacy_herb_id:' || CAST(h.id AS TEXT))
                );
                """,
                (record_id, source_id),
            ).fetchall()
            herb_ids = [r[0] for r in herb_rows]

            # ----------------------------------------------------------------
            # Case A: Dosha Claim Assertions & Herb Dosha Effects
            # ----------------------------------------------------------------
            if domain == "dosha":
                dosha_pairs = _decompose_dosha_expression(source_expression, dosha_concepts, effect_concepts)
                for dosha_cid, effect_cid in dosha_pairs:
                    # Idempotent insert into dosha_claim_assertions
                    existing_asst = connection.execute(
                        """
                        SELECT dosha_assertion_id FROM dosha_claim_assertions
                        WHERE source_claim_id = ? AND dosha_concept_id = ? AND effect_concept_id = ?;
                        """,
                        (claim_id, dosha_cid, effect_cid),
                    ).fetchone()

                    if existing_asst is None:
                        cursor = connection.execute(
                            """
                            INSERT INTO dosha_claim_assertions (
                                source_claim_id, dosha_concept_id, effect_concept_id,
                                mapping_confidence, mapping_method, verification_status, created_at
                            ) VALUES (?, ?, ?, NULL, 'lexicon_exact', 'unreviewed', ?);
                            """,
                            (claim_id, dosha_cid, effect_cid, now),
                        )
                        assertion_id = cursor.lastrowid
                        inserted_mappings += 1
                    else:
                        assertion_id = existing_asst[0]

                    # Link to herbs in herb_dosha_effects
                    for h_id in herb_ids:
                        existing_eff = connection.execute(
                            "SELECT herb_dosha_effect_id FROM herb_dosha_effects WHERE herb_id = ? AND dosha_assertion_id = ?;",
                            (h_id, assertion_id),
                        ).fetchone()
                        if existing_eff is None:
                            connection.execute(
                                """
                                INSERT INTO herb_dosha_effects (herb_id, dosha_assertion_id, source_presence_status, created_at)
                                VALUES (?, ?, 'active', ?);
                                """,
                                (h_id, assertion_id, now),
                            )
                            inserted_dosha_effects += 1
                            sources_evaluated[source_id]["properties"] += 1

            # ----------------------------------------------------------------
            # Case B: Properties, Plant Parts, Preparations, Indications
            # ----------------------------------------------------------------
            else:
                tokens = _clean_and_tokenize_expression(source_expression)
                for tok in tokens:
                    match = _match_concept_in_domain(domain, tok, domain_labels, concept_codes)
                    if match is None:
                        continue

                    concept_id, _ = match

                    # Idempotent insert into concept_claim_mappings
                    existing_map = connection.execute(
                        """
                        SELECT mapping_id FROM concept_claim_mappings
                        WHERE source_claim_id = ? AND concept_id = ?;
                        """,
                        (claim_id, concept_id),
                    ).fetchone()

                    if existing_map is None:
                        cursor = connection.execute(
                            """
                            INSERT INTO concept_claim_mappings (
                                source_claim_id, concept_id, mapping_type, mapping_confidence,
                                mapping_method, verification_status, created_at
                            ) VALUES (?, ?, 'exact', NULL, 'lexicon_exact', 'unreviewed', ?);
                            """,
                            (claim_id, concept_id, now),
                        )
                        mapping_id = cursor.lastrowid
                        inserted_mappings += 1
                    else:
                        mapping_id = existing_map[0]

                    # Link to herbs in target relationship table
                    for h_id in herb_ids:
                        if rel_table == "herb_dravyaguna_properties":
                            existing_rel = connection.execute(
                                """
                                SELECT herb_property_id FROM herb_dravyaguna_properties
                                WHERE herb_id = ? AND mapping_id = ? AND part_concept_id IS NULL;
                                """,
                                (h_id, mapping_id),
                            ).fetchone()
                            if existing_rel is None:
                                connection.execute(
                                    """
                                    INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, source_presence_status, created_at)
                                    VALUES (?, ?, NULL, 'active', ?);
                                    """,
                                    (h_id, mapping_id, now),
                                )
                                inserted_properties += 1
                                sources_evaluated[source_id]["properties"] += 1

                        elif rel_table == "herb_plant_parts":
                            existing_rel = connection.execute(
                                "SELECT herb_part_id FROM herb_plant_parts WHERE herb_id = ? AND mapping_id = ?;",
                                (h_id, mapping_id),
                            ).fetchone()
                            if existing_rel is None:
                                connection.execute(
                                    """
                                    INSERT INTO herb_plant_parts (herb_id, mapping_id, source_presence_status, created_at)
                                    VALUES (?, ?, 'active', ?);
                                    """,
                                    (h_id, mapping_id, now),
                                )
                                inserted_plant_parts += 1
                                sources_evaluated[source_id]["properties"] += 1

                        elif rel_table == "herb_preparations":
                            existing_rel = connection.execute(
                                """
                                SELECT herb_preparation_id FROM herb_preparations
                                WHERE herb_id = ? AND prep_mapping_id = ? AND part_mapping_id IS NULL;
                                """,
                                (h_id, mapping_id),
                            ).fetchone()
                            if existing_rel is None:
                                connection.execute(
                                    """
                                    INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, source_presence_status, created_at)
                                    VALUES (?, ?, NULL, 'active', ?);
                                    """,
                                    (h_id, mapping_id, now),
                                )
                                inserted_preparations += 1
                                sources_evaluated[source_id]["properties"] += 1

                        elif rel_table == "herb_indications":
                            existing_rel = connection.execute(
                                "SELECT herb_indication_id FROM herb_indications WHERE herb_id = ? AND mapping_id = ?;",
                                (h_id, mapping_id),
                            ).fetchone()
                            if existing_rel is None:
                                connection.execute(
                                    """
                                    INSERT INTO herb_indications (herb_id, mapping_id, source_presence_status, created_at)
                                    VALUES (?, ?, 'active', ?);
                                    """,
                                    (h_id, mapping_id, now),
                                )
                                inserted_indications += 1
                                sources_evaluated[source_id]["properties"] += 1

        # Audit Logger: Record operational audit record in source_reconciliation_events
        metrics = {
            "processed_claims": processed_claims,
            "inserted_mappings": inserted_mappings,
            "inserted_properties": inserted_properties,
            "inserted_dosha_effects": inserted_dosha_effects,
            "inserted_plant_parts": inserted_plant_parts,
            "inserted_preparations": inserted_preparations,
            "inserted_indications": inserted_indications,
        }

        for src_id, counts in sources_evaluated.items():
            audit_note = (
                f"[STAGE_C_BACKFILL] processed_claims={counts['claims']} properties_reconciled={counts['properties']} "
                f"mappings={inserted_mappings} properties={inserted_properties} dosha_effects={inserted_dosha_effects} "
                f"plant_parts={inserted_plant_parts} preps={inserted_preparations} indications={inserted_indications}"
            )
            connection.execute(
                """
                INSERT INTO source_reconciliation_events (
                    source_id, event_type, snapshot_timestamp, extraction_status,
                    is_complete_snapshot, claims_evaluated, properties_reconciled,
                    omissions_flagged, notes, initiated_by, completed_at
                ) VALUES (
                    ?, 'ingest_batch', ?, 'completed',
                    1, ?, ?,
                    0, ?, 'stage_c_backfill_engine', ?
                );
                """,
                (src_id, now, counts["claims"], counts["properties"], audit_note, now),
            )

        connection.execute("RELEASE SAVEPOINT wp4_backfill;")
        return metrics

    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT wp4_backfill;")
        connection.execute("RELEASE SAVEPOINT wp4_backfill;")
        raise
