from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from herbal_almanac.cleaning import PlantRecord
from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.herb_view import group_attributes
from herbal_almanac.web_app import create_app


def _make_record(source_record_id: int, attrs: dict[str, list[str]]) -> PlantRecord:
    return PlantRecord(
        ayurvedic_name="Āmra",
        transliterated_name="Amra",
        botanical_name="Mangifera indica",
        family="Anacardiaceae",
        source="CCRAS DRAVYA",
        source_record_id=source_record_id,
        source_url=f"https://dravya.ccras.org.in/plant/{source_record_id}/mangifera-indica",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        attributes=attrs,
        dosha_expressions=[],
        source_values={},
    )


def test_parts_used_mahakashaya_vipaka_guna_preserve_insertion_order(tmp_path: Path) -> None:
    """ORDER BY a.field_name, a.rowid preserves source insertion order so triples stay aligned."""
    db_path = tmp_path / "aligned.db"
    almanac = AyurvedicAlmanac(db_path)

    # Deliberately choose values where alphabetical order differs across English / IAST / Hindi
    # e.g. Endosperm(E) < Flower(F) < Fruit(Fr) < Leaf(L),
    # while IAST: Bījamajjā(B) < Patra(Pa) < Phala(Ph) < Puṣpa(Pu) (Patra sorts before Phala & Puṣpa!)
    # and Hindi: पत्र(प) < पुष्प(पु) < फल(फ) < बीजमज्जा(ब) (बीजमज्जा sorts LAST in Devanagari!)
    rec = _make_record(
        231,
        {
            "Parts Used.Name": ["Endosperm", "Flower/ inflorescence", "Fruit", "Leaf"],
            "Parts Used.Part Used(Diacritical)": ["Bījamajjā", "Puṣpa", "Phala", "Patra"],
            "Parts Used.उपयोगी हिस्सा(हिन्दी)": ["बीजमज्जा", "पुष्प", "फल", "पत्र"],
            "Mahakashaya.Name": ["Mutrasangrahaniya", "Chhardinigrahana"],
            "Mahakashaya.Mahakashaya(Diacritical)": ["Mūtrasaṅgrahaṇīya", "Chhardinigrahaṇa"],
            "Mahakashaya.महाकषाय(हिन्दी)": ["मूत्रसंग्रहणीय", "छर्दिनिग्रहण"],
            "Vipaka.Name": ["Madhura", "Amla"],
            "Vipaka.Vipaka(Diacritical)": ["Madhura", "Amla"],
            "Vipaka.विपाक(हिन्दी)": ["मधुर", "अम्ल"],
            "Guna.Name": ["Snigdha", "Guru"],
            "Guna.Guna(Diacritical)": ["Snigdha", "Guru"],
            "Guna.गुण(हिन्दी)": ["स्निग्ध", "गुरु"],
        },
    )
    herb_id = almanac.insert_record(rec)
    attrs = almanac.herb_attributes(herb_id)
    grouped = group_attributes(attrs)

    assert grouped["parts_used"]["aligned"] is True
    assert grouped["parts_used"]["rows"] == [
        {"english": "Endosperm", "iast": "Bījamajjā", "hindi": "बीजमज्जा"},
        {"english": "Flower/ inflorescence", "iast": "Puṣpa", "hindi": "पुष्प"},
        {"english": "Fruit", "iast": "Phala", "hindi": "फल"},
        {"english": "Leaf", "iast": "Patra", "hindi": "पत्र"},
    ]

    raw_by_name = {g["group_name"]: g for g in grouped["raw_dravyaguna_groups"]}
    assert raw_by_name["Mahakashaya"]["rows"] == [
        {"english": "Mutrasangrahaniya", "iast": "Mūtrasaṅgrahaṇīya", "hindi": "मूत्रसंग्रहणीय"},
        {"english": "Chhardinigrahana", "iast": "Chhardinigrahaṇa", "hindi": "छर्दिनिग्रहण"},
    ]
    assert raw_by_name["Vipaka"]["rows"] == [
        {"english": "Madhura", "iast": "Madhura", "hindi": "मधुर"},
        {"english": "Amla", "iast": "Amla", "hindi": "अम्ल"},
    ]
    assert raw_by_name["Guna"]["rows"] == [
        {"english": "Snigdha", "iast": "Snigdha", "hindi": "स्निग्ध"},
        {"english": "Guru", "iast": "Guru", "hindi": "गुरु"},
    ]

    # Also verify all_records() preserves rowid order
    all_attrs = [a for a in almanac.all_records()["attributes"] if a["herb_id"] == herb_id]
    grouped_all = group_attributes(all_attrs)
    assert grouped_all["parts_used"]["rows"] == grouped["parts_used"]["rows"]


def test_mismatched_length_triple_group_renders_unaligned_note(tmp_path: Path) -> None:
    """When English/IAST/Hindi lengths differ, _merge_triple_group refuses to mis-pair and renders note."""
    db_path = tmp_path / "unaligned.db"
    almanac = AyurvedicAlmanac(db_path)
    rec = _make_record(
        231,
        {
            "Parts Used.Name": ["Root", "Leaf", "Bark"],
            "Parts Used.Part Used(Diacritical)": ["Mūla", "Patra"],
            "Parts Used.उपयोगी हिस्सा(हिन्दी)": ["मूल", "पत्र"],
        },
    )
    herb_id = almanac.insert_record(rec)
    grouped = group_attributes(almanac.herb_attributes(herb_id))

    assert grouped["parts_used"]["aligned"] is False
    assert grouped["parts_used"]["rows"] == []
    assert grouped["parts_used"]["english_list"] == ["Root", "Leaf", "Bark"]
    assert grouped["parts_used"]["iast_list"] == ["Mūla", "Patra"]
    assert grouped["parts_used"]["hindi_list"] == ["मूल", "पत्र"]

    app = create_app(db_path)
    client = TestClient(app)
    res = client.get(f"/herbs/{herb_id}")
    assert res.status_code == 200
    assert "Values could not be aligned row-by-row in the source" in res.text
    assert "Bark" in res.text
