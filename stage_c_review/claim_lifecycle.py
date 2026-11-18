"""
Herbal Almanac — Stage C.2 Work Package 3 (WP-3)
Claim Lifecycle, Interpretation Review & Section-Level Omission Engine
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from schema_capability_gate import require_stage_c_schema_v3


# ============================================================================
# 1. Validation & Lineage Tagging Helpers
# ============================================================================

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
            "Database connection must have an active transaction (e.g. BEGIN IMMEDIATE) before executing lifecycle operations."
        )


def _parse_inherited_tag(notes: str | None, source_claim_id: int | None = None) -> str | None:
    """Extract prior status from [INHERITED_FROM_CLAIM:{id}:PRIOR={status}] tag."""
    if not notes:
        return None
    if source_claim_id is not None:
        prefix = f"[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR="
        if prefix in notes:
            m = re.search(rf'\[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=([^\]]+)\]', notes)
            if m:
                return m.group(1).strip()
    else:
        m = re.search(r'\[INHERITED_FROM_CLAIM:\d+:PRIOR=([^\]]+)\]', notes)
        if m:
            return m.group(1).strip()
    return None


def _strip_inherited_tag(notes: str | None, source_claim_id: int | None = None) -> str | None:
    """Remove inherited lineage tag from notes string."""
    if not notes:
        return None
    if source_claim_id is not None:
        pattern = rf'\[INHERITED_FROM_CLAIM:{source_claim_id}:PRIOR=[^\]]+\]\s*'
    else:
        pattern = r'\[INHERITED_FROM_CLAIM:\d+:PRIOR=[^\]]+\]\s*'
    cleaned = re.sub(pattern, '', notes)
    return cleaned.strip() or None


# ============================================================================
# 2. Routine Source Claim Lifecycle Helper
# ============================================================================

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
    _check_preconditions(connection)

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
        formatted_new_notes = f"{citation_header} {reviewer_notes.strip()}" if reviewer_notes and reviewer_notes.strip() else citation_header

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
        (new_status, now, reviewed_by.strip() if reviewed_by else None, reviewed_by.strip() if reviewed_by else None, now, merged_claim_notes, source_claim_id),
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
                (new_status, reviewed_by.strip() if reviewed_by else None, reviewed_by.strip() if reviewed_by else None, now, tagged_notes, a_id),
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
            (source_id, now, audit_note, reviewed_by.strip() if reviewed_by else 'routine_pipeline'),
        )


# ============================================================================
# 3. Administrative Claim Override & Reopening Helper
# ============================================================================

def adjudicate_claim_status_override(
    connection: sqlite3.Connection,
    source_claim_id: int,
    new_status: str,
    *args: Any,
    now: str | None = None,
    authorized_curator_id: str | None = None,
    adjudication_reason: str | None = None,
    authority_citation: str | None = None,
    herb_id: int | None = None,
    **kwargs: Any,
) -> None:
    """Administratively override or reopen a claim status with mandatory audit logging.

    PRECONDITION: The application service layer must authenticate the actor and confirm
    curator/admin privileges prior to calling this helper. Parameter authorized_curator_id
    records the authenticated identity for audit provenance; the helper does not authenticate.

    TRANSACTION CONTRACT: Must be executed within caller transaction (BEGIN IMMEDIATE).
    """
    _check_preconditions(connection)

    # Resolve flexible calling convention between ADR Section 7.F and prompt ordering:
    # Option A (ADR 7.F): (conn, claim_id, new_status, now, curator_id, reason, [citation, herb_id])
    # Option B (Prompt):  (conn, claim_id, new_status, curator_id, reason, now, [citation, herb_id])
    # Option C (Keyword): (conn, claim_id, new_status, now=..., authorized_curator_id=..., ...)
    if len(args) >= 3:
        # Determine whether args[0] or args[2] is the timestamp
        arg0_str = str(args[0]) if args[0] is not None else ""
        if arg0_str.endswith("Z") or arg0_str.endswith("+00:00"):
            now = now or args[0]
            authorized_curator_id = authorized_curator_id or args[1]
            adjudication_reason = adjudication_reason or args[2]
        else:
            authorized_curator_id = authorized_curator_id or args[0]
            adjudication_reason = adjudication_reason or args[1]
            now = now or args[2]
        if len(args) > 3 and authority_citation is None:
            authority_citation = args[3]
        if len(args) > 4 and herb_id is None:
            herb_id = args[4]
    elif len(args) == 2:
        # (curator_id, reason) passed positionally, now passed as keyword
        authorized_curator_id = authorized_curator_id or args[0]
        adjudication_reason = adjudication_reason or args[1]
    elif len(args) == 1:
        authorized_curator_id = authorized_curator_id or args[0]

    # Handle kwargs fallbacks
    if "curator_id" in kwargs and not authorized_curator_id:
        authorized_curator_id = kwargs["curator_id"]
    if "reason" in kwargs and not adjudication_reason:
        adjudication_reason = kwargs["reason"]

    valid_statuses = ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded')
    if new_status not in valid_statuses:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")

    if now is None:
        raise ValueError("Timestamp 'now' must be provided")
    _validate_iso_utc_timestamp(now)

    if not authorized_curator_id or not str(authorized_curator_id).strip():
        raise ValueError("Administrative adjudication requires a non-empty authorized_curator_id")

    if not adjudication_reason or len(str(adjudication_reason).strip()) < 10:
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

    citation_part = f" [CITATION: {authority_citation.strip()}]" if authority_citation and authority_citation.strip() else ""
    formatted_override = f"[ADMIN OVERRIDE: {current_status} -> {new_status}]{citation_part} {str(adjudication_reason).strip()}"
    merged_claim_notes = f"{existing_claim_notes.strip()} | {formatted_override}" if existing_claim_notes and existing_claim_notes.strip() else formatted_override

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
        (new_status, now, str(authorized_curator_id).strip(), now, merged_claim_notes, source_claim_id),
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
                (new_status, str(authorized_curator_id).strip(), now, tagged_notes, a_id),
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
                    (target_child_status, str(authorized_curator_id).strip(), now, clean_notes, m_id),
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
                    (target_child_status, str(authorized_curator_id).strip(), now, clean_notes, a_id),
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
        (source_id, now, audit_notes, str(authorized_curator_id).strip()),
    )


# ============================================================================
# 4. Independent Child Interpretation Review Helper
# ============================================================================

def transition_interpretation_status(
    connection: sqlite3.Connection,
    table_name: str,
    record_id: int,
    new_status: str,
    now: str,
    reviewed_by: str | None = None,
    reviewer_notes: str | None = None,
    authority_citation: str | None = None,
    herb_id: int | None = None,
) -> None:
    """Independently review or verify a child mapping or Dosha assertion.

    Implements the independent review workflow specified in ADR Revision 9 Section 7.E.
    """
    _check_preconditions(connection)

    if table_name not in ('concept_claim_mappings', 'dosha_claim_assertions'):
        raise ValueError(
            f"Invalid table_name: {table_name!r}. Must be 'concept_claim_mappings' or 'dosha_claim_assertions'"
        )

    valid_statuses = ('unreviewed', 'reviewed', 'verified', 'rejected', 'superseded')
    if new_status not in valid_statuses:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")

    _validate_iso_utc_timestamp(now)

    # Fetch child record and parent claim status
    if table_name == 'concept_claim_mappings':
        row = connection.execute(
            """
            SELECT m.mapping_id, m.source_claim_id, m.verification_status, m.reviewer_notes,
                   sc.verification_status AS parent_status, sr.source_id
            FROM concept_claim_mappings m
            JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
            JOIN source_records sr ON sr.source_record_id = sc.source_record_id
            WHERE m.mapping_id = ?
            """,
            (record_id,),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT a.dosha_assertion_id, a.source_claim_id, a.verification_status, a.reviewer_notes,
                   sc.verification_status AS parent_status, sr.source_id
            FROM dosha_claim_assertions a
            JOIN source_claims sc ON sc.source_claim_id = a.source_claim_id
            JOIN source_records sr ON sr.source_record_id = sc.source_record_id
            WHERE a.dosha_assertion_id = ?
            """,
            (record_id,),
        ).fetchone()

    if row is None:
        raise KeyError(f"Record {record_id} not found in {table_name}")

    rec_id, source_claim_id, current_child_status, existing_child_notes, parent_status, source_id = row

    # Same-status idempotency
    if current_child_status == new_status:
        return

    # Parent Constraint (ADR Section 7.E.1)
    if new_status in ('reviewed', 'verified'):
        if parent_status in ('unreviewed', 'rejected', 'superseded'):
            raise ValueError(
                f"Cannot transition child interpretation to '{new_status}' because parent claim {source_claim_id} "
                f"is in status '{parent_status}'. Parent must be 'reviewed' or 'verified'."
            )

    # Reviewer Identity & Citation validation
    if new_status in ('reviewed', 'verified'):
        if not reviewed_by or not reviewed_by.strip():
            raise ValueError(f"Transition to '{new_status}' requires a non-empty reviewed_by identifier")

    if new_status == 'verified':
        if not authority_citation or len(authority_citation.strip()) < 5:
            raise ValueError("Transition to 'verified' strictly requires an explicit authority_citation (min 5 chars)")

    # When transitioning an inheriting child independently to terminal status, strip any inherited tag
    clean_notes = existing_child_notes
    if new_status in ('rejected', 'superseded'):
        clean_notes = _strip_inherited_tag(existing_child_notes, source_claim_id)

    formatted_new_notes = reviewer_notes
    if new_status == 'verified':
        citation_header = f"[CITATION: {authority_citation.strip()}]"
        formatted_new_notes = (
            f"{citation_header} {reviewer_notes.strip()}"
            if reviewer_notes and reviewer_notes.strip()
            else citation_header
        )

    base_notes = clean_notes if new_status in ('rejected', 'superseded') else existing_child_notes
    if base_notes and formatted_new_notes:
        merged_notes = f"{base_notes.strip()} | {formatted_new_notes.strip()}"
    else:
        merged_notes = formatted_new_notes or base_notes

    # Update child row
    pk_column = "mapping_id" if table_name == 'concept_claim_mappings' else "dosha_assertion_id"
    connection.execute(
        f"""
        UPDATE {table_name}
        SET verification_status = ?,
            reviewed_by = COALESCE(?, reviewed_by),
            reviewed_at = CASE WHEN ? IS NOT NULL THEN ? ELSE reviewed_at END,
            reviewer_notes = ?
        WHERE {pk_column} = ?
        """,
        (new_status, reviewed_by.strip() if reviewed_by else None, reviewed_by.strip() if reviewed_by else None, now, merged_notes, record_id),
    )

    # Log audit event
    herb_tag = f"[HERB_ID: {herb_id}]" if herb_id is not None else "[HERB_ID: UNATTACHED]"
    audit_notes = (
        f"[CLAIM_ID: {source_claim_id}] {herb_tag} [CHILD_TABLE: {table_name}] [CHILD_ID: {record_id}] "
        f"[INTERPRETATION_TRANSITION: {current_child_status} -> {new_status}]"
        f"{' ' + merged_notes if merged_notes else ''}"
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
        (source_id, now, audit_notes, reviewed_by.strip() if reviewed_by else 'routine_curator'),
    )


# ============================================================================
# 5. Calibrated Mapping Confidence Enforcer
# ============================================================================

def validate_calibrated_mapping_confidence(
    mapping_method: str,
    mapping_confidence: float | None,
) -> None:
    """Enforces calibrated mapping confidence constraints per ADR Decision 4 (Section 5).

    Rules:
    - 'lexicon_exact' mappings MUST have mapping_confidence = None (exact lexical lookups
      do not carry artificial numeric certainty scores). Raises ValueError if a numeric
      value is supplied.
    - If mapping_confidence is provided (for probabilistic/fuzzy/normalizer methods),
      it must be between 0.0 and 1.0 inclusive (0.0 <= mapping_confidence <= 1.0).
    """
    if not isinstance(mapping_method, str) or not mapping_method.strip():
        raise ValueError(f"mapping_method must be a non-empty string; got {mapping_method!r}")

    clean_method = mapping_method.strip()
    valid_methods = {"lexicon_exact", "rule_normalizer", "human_expert", "heuristic"}
    if clean_method not in valid_methods:
        raise ValueError(f"Unknown mapping_method {clean_method!r}. Must be one of {sorted(valid_methods)}")

    if clean_method == "lexicon_exact":
        if mapping_confidence is not None:
            raise ValueError(
                f"Calibrated Confidence Error: mapping_method 'lexicon_exact' strictly requires "
                f"mapping_confidence=None (got {mapping_confidence}). Exact lexical mappings must retain "
                f"NULL confidence to avoid false quantitative precision."
            )
    else:
        if mapping_confidence is not None:
            if not isinstance(mapping_confidence, (int, float)):
                raise ValueError(f"mapping_confidence must be numeric or None; got {type(mapping_confidence).__name__}")
            if not (0.0 <= float(mapping_confidence) <= 1.0):
                raise ValueError(
                    f"mapping_confidence {mapping_confidence} out of range [0.0, 1.0]. "
                    f"Must be between 0.0 and 1.0 inclusive."
                )


# ============================================================================
# 6. Section-Level Omission Detection Engine
# ============================================================================

SECTION_DOMAIN_TABLE_MAP: dict[str, tuple[str, str, str]] = {
    "dravyaguna_properties": ("herb_dravyaguna_properties", "herb_property_id", "mapping_id"),
    "dosha_effects": ("herb_dosha_effects", "herb_dosha_effect_id", "dosha_assertion_id"),
    "plant_parts": ("herb_plant_parts", "herb_part_id", "mapping_id"),
    "preparations": ("herb_preparations", "herb_preparation_id", "prep_mapping_id"),
    "indications": ("herb_indications", "herb_indication_id", "mapping_id"),
}


def reconcile_section_omissions(
    connection: sqlite3.Connection,
    *,
    herb_id: int,
    source_id: int,
    event_id: int,
    section_domain: str,
    parsed_sections: Mapping[str, bool],
    active_relationship_ids: set[int],
    now: str,
) -> dict[str, int]:
    """Flag unattested relationships as candidate omissions for a parsed source section.

    Implements the Section-Level Omission Completeness Contract per ADR Section 7.G.
    """
    _check_preconditions(connection)
    _validate_iso_utc_timestamp(now)

    if section_domain not in SECTION_DOMAIN_TABLE_MAP:
        raise ValueError(
            f"Unknown section_domain: {section_domain!r}. Must be one of {sorted(SECTION_DOMAIN_TABLE_MAP.keys())}"
        )

    table_name, pk_col, fk_col = SECTION_DOMAIN_TABLE_MAP[section_domain]

    # Verify reconciliation event exists and belongs to source_id
    row = connection.execute(
        """
        SELECT source_id, extraction_status, is_complete_snapshot
        FROM source_reconciliation_events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Reconciliation event {event_id} not found")

    ev_source_id, extraction_status, is_complete_snapshot = row
    if ev_source_id != source_id:
        raise ValueError(f"Event {event_id} belongs to source {ev_source_id}, not expected source {source_id}")

    # Completeness Gate (ADR Section 7.G.2)
    # Both snapshot must be complete AND section must be explicitly True
    if is_complete_snapshot != 1 or extraction_status != 'completed' or parsed_sections.get(section_domain) is not True:
        return {"flagged_candidate_omissions": 0, "skipped_incomplete": 1}

    # Fetch active relationships for herb_id and source_id
    if table_name == "herb_dosha_effects":
        rel_rows = connection.execute(
            """
            SELECT rel.herb_dosha_effect_id
            FROM herb_dosha_effects rel
            JOIN dosha_claim_assertions a ON a.dosha_assertion_id = rel.dosha_assertion_id
            JOIN source_claims sc ON sc.source_claim_id = a.source_claim_id
            JOIN source_records sr ON sr.source_record_id = sc.source_record_id
            WHERE rel.herb_id = ?
              AND sr.source_id = ?
              AND rel.source_presence_status = 'active'
            """,
            (herb_id, source_id),
        ).fetchall()
    elif table_name == "herb_preparations":
        rel_rows = connection.execute(
            """
            SELECT rel.herb_preparation_id
            FROM herb_preparations rel
            JOIN concept_claim_mappings m ON m.mapping_id = rel.prep_mapping_id
            JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
            JOIN source_records sr ON sr.source_record_id = sc.source_record_id
            WHERE rel.herb_id = ?
              AND sr.source_id = ?
              AND rel.source_presence_status = 'active'
            """,
            (herb_id, source_id),
        ).fetchall()
    else:
        rel_rows = connection.execute(
            f"""
            SELECT rel.{pk_col}
            FROM {table_name} rel
            JOIN concept_claim_mappings m ON m.mapping_id = rel.{fk_col}
            JOIN source_claims sc ON sc.source_claim_id = m.source_claim_id
            JOIN source_records sr ON sr.source_record_id = sc.source_record_id
            WHERE rel.herb_id = ?
              AND sr.source_id = ?
              AND rel.source_presence_status = 'active'
            """,
            (herb_id, source_id),
        ).fetchall()

    active_set = active_relationship_ids if isinstance(active_relationship_ids, (set, frozenset)) else set(active_relationship_ids)
    missing_ids = [r[0] for r in rel_rows if r[0] not in active_set]

    if missing_ids:
        # Check if table schema has last_reconciled_event_id column
        table_cols = {
            col[1] for col in connection.execute(f"PRAGMA table_info({table_name});").fetchall()
        }
        has_last_rec = "last_reconciled_event_id" in table_cols

        for missing_pk in missing_ids:
            if has_last_rec:
                connection.execute(
                    f"UPDATE {table_name} SET source_presence_status = 'candidate_omission', last_reconciled_event_id = ? WHERE {pk_col} = ?",
                    (event_id, missing_pk),
                )
            else:
                connection.execute(
                    f"UPDATE {table_name} SET source_presence_status = 'candidate_omission' WHERE {pk_col} = ?",
                    (missing_pk,),
                )

        connection.execute(
            """
            UPDATE source_reconciliation_events
            SET omissions_flagged = omissions_flagged + ?
            WHERE event_id = ?
            """,
            (len(missing_ids), event_id),
        )

    return {"flagged_candidate_omissions": len(missing_ids), "skipped_incomplete": 0}
