from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from herbal_almanac.cleaning import PlantRecord
from herbal_almanac.database_operator import (
    AyurvedicAlmanac,
    ClaimAssociationError,
)


def make_test_record(
    plant_id: int = 1,
    ayurvedic_name: str = "Tulsi",
    botanical_name: str | None = "Ocimum tenuiflorum",
    family: str | None = "Lamiaceae",
    vernacular: dict[str, list[str]] | None = None,
    attributes: dict[str, list[str]] | None = None,
    dosha_expressions: list[str] | None = None,
) -> PlantRecord:
    attrs = dict(attributes or {})
    if vernacular:
        for lang, names in vernacular.items():
            attrs[f"Vernacular Names.{lang}"] = names
    return PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=plant_id,
        source_url=f"https://dravya.ccras.org.in/plant/{plant_id}",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name=ayurvedic_name,
        botanical_name=botanical_name,
        family=family,
        attributes=attrs,
        source_values={k: " | ".join(v) for k, v in attrs.items()},
        dosha_expressions=dosha_expressions or ["KaphaVātahara"],
    ).clean()


def test_dravya_source_creation_and_reuse(tmp_path: Path) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec1 = make_test_record(plant_id=1, ayurvedic_name="Tulsi")
    rec2 = make_test_record(plant_id=2, ayurvedic_name="Neem")

    db.insert_record(rec1)
    with db.connect() as conn:
        sources = conn.execute("SELECT * FROM sources").fetchall()
        assert len(sources) >= 1
        dravya = next(s for s in sources if s["source_key"] == "CCRAS DRAVYA")
        assert dravya["publisher"] == "CCRAS"
        assert dravya["default_url"] == "https://dravya.ccras.org.in"
        source_count_before = len(sources)

    db.insert_record(rec2)
    with db.connect() as conn:
        source_count_after = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        assert source_count_after == source_count_before


def test_source_record_creation_and_reuse(tmp_path: Path) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec = make_test_record(plant_id=10, ayurvedic_name="Haritaki")

    herb_id = db.insert_record(rec)
    with db.connect() as conn:
        sr = conn.execute(
            "SELECT * FROM source_records WHERE external_record_key = '10'"
        ).fetchone()
        assert sr is not None
        assert sr["source_url"] == "https://dravya.ccras.org.in/plant/10"
        assert sr["retrieved_at"] == "2026-01-01T00:00:00+00:00"
        sr_id_1 = sr["source_record_id"]

    # Re-scrape with updated retrieved_at
    rec_updated = make_test_record(plant_id=10, ayurvedic_name="Haritaki")
    rec_updated.retrieved_at = "2026-02-01T00:00:00+00:00"
    db.insert_record(rec_updated)

    with db.connect() as conn:
        records = conn.execute(
            "SELECT * FROM source_records WHERE external_record_key = '10'"
        ).fetchall()
        assert len(records) == 1
        assert records[0]["source_record_id"] == sr_id_1
        assert records[0]["retrieved_at"] == "2026-02-01T00:00:00+00:00"


def test_claim_creation_and_deduplication(tmp_path: Path) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec = make_test_record(
        plant_id=25,
        ayurvedic_name="Ashwagandha",
        botanical_name="Withania somnifera",
        family="Solanaceae",
        vernacular={"Hindi": ["अश्वगंधा", "असगंध"], "English": ["Indian Ginseng"]},
        attributes={
            "Parts Used.Name": ["Mula (Root)"],
            "Therapeutic Usage.Name": ["Kasa"],
        },
        dosha_expressions=["VataKaphahara"],
    )

    herb_id = db.insert_record(rec)
    claims_first = db.herb_claims(herb_id)
    assert len(claims_first) > 0

    claim_types = {c["claim_type"] for c in claims_first}
    assert "herb_name" in claim_types
    assert "taxonomy_name" in claim_types
    assert "attribute" in claim_types
    assert "dosha_expression" in claim_types

    # Re-inserting the exact same record must not produce duplicate claims
    db.insert_record(rec)
    claims_second = db.herb_claims(herb_id)
    assert len(claims_second) == len(claims_first)


def test_preservation_of_original_source_wording_and_normalized_values(
    tmp_path: Path,
) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec = make_test_record(
        plant_id=30,
        ayurvedic_name="Kāsa-Hara",
        botanical_name="Ocimum tenuiflorum L.",
        family="Lamiaceae",
        vernacular={"Hindi": ["तुलसी"]},
    )

    herb_id = db.insert_record(rec)
    with db.connect() as conn:
        names = conn.execute(
            "SELECT name_text, normalized_text, script_code, name_type, is_preferred "
            "FROM herb_names WHERE herb_id = ? ORDER BY herb_name_id",
            (herb_id,),
        ).fetchall()
        name_dict = {row["name_text"]: row for row in names}

        assert "Kāsa-Hara" in name_dict
        assert name_dict["Kāsa-Hara"]["is_preferred"] == 1
        assert name_dict["Kāsa-Hara"]["name_type"] == "ayurvedic"

        assert "तुलसी" in name_dict
        assert name_dict["तुलसी"]["script_code"] == "Deva"
        assert name_dict["तुलसी"]["name_type"] == "vernacular"

        taxa = conn.execute(
            "SELECT scientific_name, normalized_name, rank FROM taxa ORDER BY taxon_id"
        ).fetchall()
        taxa_names = {t["scientific_name"]: t for t in taxa}
        assert "Ocimum tenuiflorum L." in taxa_names
        assert taxa_names["Ocimum tenuiflorum L."]["rank"] == "unknown"
        assert "Lamiaceae" in taxa_names
        assert taxa_names["Lamiaceae"]["rank"] == "family"


def test_changed_source_content_creates_superseded_claim_history(
    tmp_path: Path,
) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec1 = make_test_record(
        plant_id=40,
        ayurvedic_name="Tulasi",
        botanical_name="Ocimum sanctum L.",
    )
    herb_id = db.insert_record(rec1)

    rec2 = make_test_record(
        plant_id=40,
        ayurvedic_name="Tulsi",
        botanical_name="Ocimum tenuiflorum L.",
    )
    db.insert_record(rec2)

    with db.connect() as conn:
        botanical_claims = conn.execute(
            """
            SELECT source_claim_id, source_expression, verification_status, supersedes_claim_id
            FROM source_claims
            WHERE claim_type = 'taxonomy_name' AND source_field = 'scientific_profile.botanical_name'
            ORDER BY source_claim_id
            """
        ).fetchall()
        assert len(botanical_claims) == 2
        old_claim, new_claim = botanical_claims[0], botanical_claims[1]
        assert old_claim["source_expression"] == "Ocimum sanctum L."
        assert old_claim["verification_status"] == "superseded"
        assert new_claim["source_expression"] == "Ocimum tenuiflorum L."
        assert new_claim["verification_status"] == "unreviewed"
        assert new_claim["supersedes_claim_id"] == old_claim["source_claim_id"]

        ayurvedic_claims = conn.execute(
            """
            SELECT source_claim_id, source_expression, verification_status, supersedes_claim_id
            FROM source_claims
            WHERE claim_type = 'herb_name' AND source_field = 'heading.ayurvedic_name'
            ORDER BY source_claim_id
            """
        ).fetchall()
        assert len(ayurvedic_claims) == 2
        assert ayurvedic_claims[0]["verification_status"] == "superseded"
        assert ayurvedic_claims[1]["supersedes_claim_id"] == ayurvedic_claims[0]["source_claim_id"]

        preferred_names = conn.execute(
            """
            SELECT name_text, is_preferred
            FROM herb_names
            WHERE herb_id = ? AND name_type = 'ayurvedic'
            ORDER BY herb_name_id
            """,
            (herb_id,),
        ).fetchall()
        assert len(preferred_names) == 2
        assert preferred_names[0]["name_text"] == "Tulasi"
        assert preferred_names[0]["is_preferred"] == 0
        assert preferred_names[1]["name_text"] == "Tulsi"
        assert preferred_names[1]["is_preferred"] == 1


def test_missing_or_incomplete_source_fields(tmp_path: Path) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=50,
        source_url="https://dravya.ccras.org.in/plant/50",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Minimal Plant",
        botanical_name=None,
        family=None,
        attributes={},
        source_values={},
        dosha_expressions=[],
    ).clean()

    herb_id = db.insert_record(rec)
    claims = db.herb_claims(herb_id)
    assert len(claims) >= 1
    assert all(c["claim_type"] != "taxonomy_name" for c in claims)
    sr = db.herb_source_record(herb_id)
    assert sr is not None
    assert sr["external_record_key"] == "50"


def test_transaction_rollback_and_orphan_prevention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec = make_test_record(plant_id=60, ayurvedic_name="FailPlant")

    def broken_sync(*args, **kwargs):
        raise RuntimeError("simulated disk failure during provenance sync")

    monkeypatch.setattr(AyurvedicAlmanac, "_sync_attribute_claims", broken_sync)

    with pytest.raises(RuntimeError, match="simulated disk failure"):
        db.insert_record(rec)

    with db.connect() as conn:
        herbs = conn.execute("SELECT * FROM herbs WHERE source_record_id = 60").fetchall()
        assert len(herbs) == 0
        records = conn.execute(
            "SELECT * FROM source_records WHERE external_record_key = '60'"
        ).fetchall()
        assert len(records) == 0
        claims = conn.execute(
            "SELECT * FROM source_claims WHERE source_expression = 'FailPlant'"
        ).fetchall()
        assert len(claims) == 0


def test_manual_curation_survives_subsequent_scraping(tmp_path: Path) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    herb_id = db.add_herb(
        "Ashwagandha",
        botanical_name="Withania somnifera",
        family="Solanaceae",
    )
    illness_id = db.add_illness("Fatigue")
    db.add_treatment(herb_id, illness_id)

    # Scrape another plant
    scraped_rec = make_test_record(
        plant_id=70,
        ayurvedic_name="Shatavari",
        attributes={"Therapeutic Usage.Name": ["Fatigue"]},
    )
    scraped_id = db.insert_record(scraped_rec)

    # Verify manual herb treatment is untouched
    details = db.treatment_details(herb_id)
    assert len(details) == 1
    assert details[0]["english_name"] == "Fatigue"
    assert details[0]["source"] == "manual"

    # Verify manual herb has a valid source record
    sr = db.herb_source_record(herb_id)
    assert sr is not None
    assert sr["source_key"] == "manual"
    assert sr["raw_artifact_ref"] == f"legacy_herb_id:{herb_id}"


def test_migration_from_populated_legacy_database(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE herbs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_name TEXT NOT NULL,
                original_name TEXT,
                source TEXT,
                source_record_id INTEGER,
                source_url TEXT,
                retrieved_at TEXT,
                botanical_name TEXT,
                family TEXT,
                search_key TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO herbs
                (english_name, original_name, source, source_record_id,
                 source_url, retrieved_at, botanical_name, family)
            VALUES ('Brahmi', 'ब्राह्मी', 'CCRAS DRAVYA', 100,
                    'https://dravya.ccras.org.in/plant/100',
                    '2025-01-01T00:00:00+00:00', 'Bacopa monnieri', 'Plantaginaceae')
            """
        )

    db = AyurvedicAlmanac(db_path)
    db.create_database()

    with db.connect() as conn:
        # Check Migration 1 backfill
        sr = conn.execute(
            "SELECT * FROM source_records WHERE external_record_key = '100'"
        ).fetchone()
        assert sr is not None
        claim = conn.execute(
            "SELECT * FROM source_claims WHERE source_record_id = ?",
            (sr["source_record_id"],),
        ).fetchone()
        assert claim is not None
        assert claim["source_expression"] == "ब्राह्मी"

        # Check Migration 2 backfill
        taxa = conn.execute("SELECT scientific_name FROM taxa").fetchall()
        scientific_names = {t["scientific_name"] for t in taxa}
        assert "Bacopa monnieri" in scientific_names
        assert "Plantaginaceae" in scientific_names

    # Ingest a new plant on the migrated database
    new_rec = make_test_record(plant_id=101, ayurvedic_name="Guduchi")
    db.insert_record(new_rec)

    with db.connect() as conn:
        sr_new = conn.execute(
            "SELECT * FROM source_records WHERE external_record_key = '101'"
        ).fetchone()
        assert sr_new is not None
        claims_new = conn.execute(
            "SELECT * FROM source_claims WHERE source_record_id = ?",
            (sr_new["source_record_id"],),
        ).fetchall()
        assert len(claims_new) > 0


def test_public_provenance_inspection_api(tmp_path: Path) -> None:
    db = AyurvedicAlmanac(tmp_path / "provenance.db")
    rec = make_test_record(
        plant_id=80,
        ayurvedic_name="Pippali",
        botanical_name="Piper longum",
        vernacular={"Hindi": ["पिप्पली"]},
    )
    herb_id = db.insert_record(rec)

    claims = db.herb_claims(herb_id)
    assert len(claims) >= 3

    expressions = {c["source_expression"] for c in claims}
    assert "Pippali" in expressions
    assert "Piper longum" in expressions
    assert "पिप्पली" in expressions

    sr = db.herb_source_record(herb_id)
    assert sr is not None
    assert sr["source_key"] == "CCRAS DRAVYA"
    assert sr["external_record_key"] == "80"
    assert sr["source_url"] == "https://dravya.ccras.org.in/plant/80"
    assert sr["source_title"] == "CCRAS DRAVYA Portal"
