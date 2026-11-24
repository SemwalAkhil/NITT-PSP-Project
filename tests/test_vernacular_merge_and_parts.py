from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from herbal_almanac.cleaning import PlantRecord
from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.herb_view import VERNACULAR_LANG_CODES, dedupe_plant_parts
from herbal_almanac.web_app import create_app


def test_all_15_vernacular_lang_codes_including_nepali() -> None:
    expected = {
        "english": "en",
        "assamese": "as",
        "bengali": "bn",
        "gujarati": "gu",
        "hindi": "hi",
        "kannada": "kn",
        "malayalam": "ml",
        "marathi": "mr",
        "nepali": "ne",
        "odia": "or",
        "punjabi": "pa",
        "sanskrit": "sa",
        "tamil": "ta",
        "telugu": "te",
        "urdu": "ur",
    }
    for lang, code in expected.items():
        assert VERNACULAR_LANG_CODES.get(lang) == code


def test_merged_vernacular_card_single_table_and_nepali_lang(tmp_path: Path) -> None:
    db_path = tmp_path / "merged_v.db"
    almanac = AyurvedicAlmanac(db_path)
    rec = PlantRecord(
        ayurvedic_name="Āmra",
        transliterated_name="Amra",
        botanical_name="Mangifera indica",
        family="Anacardiaceae",
        source="CCRAS DRAVYA",
        source_record_id=231,
        source_url="https://dravya.ccras.org.in/plant/231/mangifera-indica",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        attributes={
            "Vernacular Names.Hindi": ["Aam", "Amba"],
            "Vernacular Names.Tamil": ["Ma"],
            "Vernacular Names.Nepali": ["Aanp"],
        },
        dosha_expressions=[],
        source_values={"Vernacular Names.Hindi": "CCRAS monograph p.231"},
    )
    herb_id = almanac.insert_record(rec)
    almanac.upgrade_to_stage_c()
    almanac.run_stage_c_backfill()

    app = create_app(db_path)
    client = TestClient(app)
    res = client.get(f"/herbs/{herb_id}?language=hi")
    assert res.status_code == 200
    html = res.text

    assert html.count('id="multilingual-vernacular-names"') == 1
    assert "<h2>Vernacular names</h2>" in html
    assert "Vernacular &amp; Regional Names" not in html
    assert "Vernacular & Regional Names" not in html
    assert "Curated name (glossary)" in html
    assert "Names in source" in html
    assert 'lang="ne"' in html
    assert 'dir="rtl"' in html
    assert "Aam, Amba" in html
    assert "CCRAS monograph p.231" in html
    assert "vernacular-row-selected" in html


def test_dedupe_plant_parts_and_template_rendering(tmp_path: Path) -> None:
    parts = [
        {"concept_code": "PART_LEAF", "display_label": "Leaf", "canonical_sanskrit_deva": "पत्र", "canonical_sanskrit_iast": "Patra", "is_disputed": False},
        {"concept_code": "PART_LEAF", "display_label": "Leaf", "canonical_sanskrit_deva": "पत्र", "canonical_sanskrit_iast": "Patra", "is_disputed": False},
        {"concept_code": "PART_LEAF", "display_label": "Leaf", "canonical_sanskrit_deva": "पत्र", "canonical_sanskrit_iast": "Patra", "is_disputed": False},
        {"concept_code": "PART_FRUIT", "display_label": "Fruit", "canonical_sanskrit_deva": "फल", "canonical_sanskrit_iast": "Phala", "is_disputed": False},
    ]
    deduped = dedupe_plant_parts(parts)
    assert len(deduped) == 2
    assert deduped[0]["concept_code"] == "PART_LEAF"
    assert deduped[0]["claim_count"] == 3
    assert deduped[1]["concept_code"] == "PART_FRUIT"
    assert deduped[1]["claim_count"] == 1

    db_path = tmp_path / "parts_v3.db"
    almanac = AyurvedicAlmanac(db_path)
    rec = PlantRecord(
        ayurvedic_name="Āmra",
        transliterated_name="Amra",
        botanical_name="Mangifera indica",
        family="Anacardiaceae",
        source="CCRAS DRAVYA",
        source_record_id=231,
        source_url="https://dravya.ccras.org.in/plant/231/mangifera-indica",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        attributes={
            "Parts Used.Name": ["Leaf"],
            "Parts Used.Part Used(Diacritical)": ["Patra"],
            "Parts Used.उपयोगी हिस्सा(हिन्दी)": ["पत्र"],
        },
        dosha_expressions=[],
        source_values={},
    )
    herb_id = almanac.insert_record(rec)
    almanac.upgrade_to_stage_c()
    almanac.run_stage_c_backfill()

    app = create_app(db_path)
    client = TestClient(app)
    res = client.get(f"/herbs/{herb_id}")
    assert res.status_code == 200
    assert res.text.count("part-card-item") == 1
    assert "×3" in res.text
