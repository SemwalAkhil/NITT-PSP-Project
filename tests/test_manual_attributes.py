from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from herbal_almanac.cli import app as cli_app
from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.web_app import create_app


@pytest.fixture
def test_db(tmp_path: Path) -> AyurvedicAlmanac:
    db_file = tmp_path / "test_manual.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()
    return almanac


def test_add_herb_attributes_storage_and_idempotency(test_db: AyurvedicAlmanac) -> None:
    herb_id = test_db.add_herb("Shankhpushpi", source="manual")
    res = test_db.add_herb_attributes(
        herb_id,
        {
            "Rasa": ["Tikta", "Kashaya"],
            "Virya": ["Sheeta"],
            "Vipaka": ["Madhura"],
            "Doshakarma": ["Tridoshashamaka"],
            "Custom.Habitat": ["Rocky soils"],
        },
    )
    assert res["herb_id"] == herb_id
    assert res["attributes_added"] == 6

    attrs = test_db.herb_attributes(herb_id)
    assert len(attrs) == 6
    fields = {a["field_name"]: a["value"] for a in attrs}
    assert "Virya" in fields
    assert "Custom.Habitat" in fields

    doshas = test_db.herb_doshas(herb_id)
    assert len(doshas) == 3  # Vata, Pitta, Kapha from Tridoshashamaka

    # Idempotent second call: no new rows added
    res2 = test_db.add_herb_attributes(
        herb_id,
        {
            "Rasa": ["Tikta", "Kashaya"],
            "Virya": ["Sheeta"],
        },
    )
    assert res2["attributes_added"] == 0
    attrs2 = test_db.herb_attributes(herb_id)
    assert len(attrs2) == 6


def test_add_herb_attributes_validation_and_limits(test_db: AyurvedicAlmanac) -> None:
    herb_id = test_db.add_herb("TestHerb", source="manual")

    # 1. Non-existent herb
    with pytest.raises(ValueError, match="does not exist"):
        test_db.add_herb_attributes(99999, {"Rasa": ["Tikta"]})

    # 2. Invalid field prefix
    with pytest.raises(ValueError, match="Invalid attribute field"):
        test_db.add_herb_attributes(herb_id, {"UnknownField": ["val"]})

    # 3. Field name exceeds 80 characters
    long_field = "Custom." + "A" * 80
    with pytest.raises(ValueError, match="exceeds maximum length of 80"):
        test_db.add_herb_attributes(herb_id, {long_field: ["val"]})

    # 4. Value exceeds 300 characters
    long_val = "B" * 305
    with pytest.raises(ValueError, match="exceeds maximum length of 300"):
        test_db.add_herb_attributes(herb_id, {"Karma": [long_val]})

    # 5. More than 30 values for a field
    too_many = [f"Val{i}" for i in range(35)]
    with pytest.raises(ValueError, match="too many values"):
        test_db.add_herb_attributes(herb_id, {"Karma": too_many})


def test_add_herb_attributes_stage_c_backfill_on_v3(tmp_path: Path) -> None:
    db_file = tmp_path / "test_v3.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()
    almanac.upgrade_to_stage_c()

    herb_id = almanac.add_herb("Ashwagandha", source="manual")
    res = almanac.add_herb_attributes(
        herb_id,
        {
            "Rasa": ["Tikta", "Kashaya", "Madhura"],
            "Virya": ["Ushna"],
            "Vipaka": ["Madhura"],
            "Guna": ["Laghu", "Snigdha"],
            "Parts Used": ["Root"],
            "Dosage Formulation": ["Churna", "Kwatha"],
            "Therapeutic Usage": ["Kasa", "Shwasa"],
            "Doshakarma": ["Vata-Kapha shamaka"],
        },
    )
    assert res["stage_c_backfilled"] is True
    assert res["attributes_added"] > 0
    assert res["claims_added"] > 0

    # Verify Stage C semantic profile is populated
    with almanac.connect() as conn:
        props = conn.execute(
            """
            SELECT c.concept_code, p.source_presence_status
            FROM herb_dravyaguna_properties p
            JOIN concept_claim_mappings m ON m.mapping_id = p.mapping_id
            JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
            WHERE p.herb_id = ?
            """,
            (herb_id,),
        ).fetchall()
        concept_codes = {r[0] for r in props}
        assert "VIRYA_USHNA" in concept_codes
        assert "VIPAKA_MADHURA" in concept_codes
        assert "GUNA_LAGHU" in concept_codes

        # Check plant parts
        parts = conn.execute(
            "SELECT COUNT(*) FROM herb_plant_parts WHERE herb_id = ?", (herb_id,)
        ).fetchone()[0]
        assert parts > 0

        # Check preparations
        preps = conn.execute(
            "SELECT COUNT(*) FROM herb_preparations WHERE herb_id = ?", (herb_id,)
        ).fetchone()[0]
        assert preps > 0


def test_add_herb_attributes_v2_to_v3_upgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "test_upgrade.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()

    herb_id = almanac.add_herb("Guduchi", source="manual")
    almanac.add_herb_attributes(
        herb_id,
        {
            "Rasa": ["Tikta", "Kashaya"],
            "Virya": ["Ushna"],
            "Vipaka": ["Madhura"],
        },
    )

    # Upgrade to v3 and run backfill
    almanac.upgrade_to_stage_c()
    almanac.run_stage_c_backfill()

    with almanac.connect() as conn:
        props = conn.execute(
            """
            SELECT c.concept_code
            FROM herb_dravyaguna_properties p
            JOIN concept_claim_mappings m ON m.mapping_id = p.mapping_id
            JOIN dravyaguna_concepts c ON c.concept_id = m.concept_id
            WHERE p.herb_id = ?
            """,
            (herb_id,),
        ).fetchall()
        codes = {r[0] for r in props}
        assert "VIRYA_USHNA" in codes


def test_web_add_herb_with_attributes_flow(tmp_path: Path) -> None:
    db_file = tmp_path / "web_test.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()

    app = create_app(db_file)
    client = TestClient(app)

    res = client.post(
        "/herbs/add",
        data={
            "english_name": "Tulsi",
            "botanical_name": "Ocimum sanctum",
            "family": "Lamiaceae",
            "source": "manual",
            "rasa": ["Tikta", "Katu"],
            "virya": "Ushna",
            "vipaka": "Katu",
            "doshakarma": "Kapha-Vata shamaka",
            "parts_used": "Leaf, Seed",
            "custom_name": ["Altitude"],
            "custom_value": ["1500m"],
        },
        headers={"Host": "testserver", "Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    loc = res.headers["location"]
    herb_id = int(loc.split("/herbs/")[1].split("?")[0])

    # Check detail page
    res_detail = client.get(loc)
    assert res_detail.status_code == 200
    assert "User-entered" in res_detail.text
    assert "Altitude" in res_detail.text


def test_web_post_attributes_to_existing_herb(tmp_path: Path) -> None:
    db_file = tmp_path / "web_post_test.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()
    herb_id = almanac.add_herb("Brahmi", source="manual")

    app = create_app(db_file)
    client = TestClient(app)

    res = client.post(
        f"/herbs/{herb_id}/attributes",
        data={
            "rasa": ["Tikta"],
            "virya": "Sheeta",
            "vipaka": "Madhura",
            "karma": "Medhya, Rasayana",
            "custom_name": ["Wetland"],
            "custom_value": ["Marshy edges"],
        },
        headers={"Host": "testserver", "Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert f"/herbs/{herb_id}?msg=Attributes+added+successfully" in res.headers["location"]

    attrs = almanac.herb_attributes(herb_id)
    fields = {a["field_name"]: a["value"] for a in attrs}
    assert "Virya" in fields
    assert "Custom.Wetland" in fields


def test_web_post_attributes_csrf_and_404(tmp_path: Path) -> None:
    db_file = tmp_path / "web_csrf.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()
    herb_id = almanac.add_herb("Neem", source="manual")

    app = create_app(db_file)
    client = TestClient(app)

    # 1. 404 on missing herb
    res_404 = client.post(
        "/herbs/9999/attributes",
        data={"rasa": ["Tikta"]},
        headers={"Host": "testserver", "Origin": "http://testserver"},
    )
    assert res_404.status_code == 404

    # 2. 403 on CSRF / origin mismatch
    res_403 = client.post(
        f"/herbs/{herb_id}/attributes",
        data={"rasa": ["Tikta"]},
        headers={"Host": "testserver", "Origin": "http://evil.com"},
    )
    assert res_403.status_code == 403


def test_web_html_escaping_in_attributes(tmp_path: Path) -> None:
    db_file = tmp_path / "web_xss.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()
    herb_id = almanac.add_herb("XssHerb", source="manual")

    xss_name = "Custom.ScriptTest"
    xss_val = "<script>alert('xss')</script>"
    almanac.add_herb_attributes(herb_id, {xss_name: [xss_val]})

    app = create_app(db_file)
    client = TestClient(app)
    res = client.get(f"/herbs/{herb_id}")
    assert res.status_code == 200
    # Must NOT contain raw unescaped script tag
    assert "<script>alert('xss')</script>" not in res.text
    # Must contain HTML escaped representation
    assert "&lt;script&gt;" in res.text
    assert "&lt;/script&gt;" in res.text


def test_illness_and_treatment_duplicate_linking(test_db: AyurvedicAlmanac) -> None:
    herb_id = test_db.add_herb("Haritaki", source="manual")
    test_db.add_herb_attributes(herb_id, {"Therapeutic Usage": ["Kasa", "Shwasa"]})
    test_db.add_herb_attributes(herb_id, {"Therapeutic Usage": ["Kasa", "Jvara"]})

    with test_db.connect() as conn:
        treatments = conn.execute(
            "SELECT COUNT(*) FROM treatment WHERE herb_id = ?", (herb_id,)
        ).fetchone()[0]
        # Kasa, Shwasa, Jvara = 3 distinct links
        assert treatments == 3


def test_cli_add_herb_with_attributes(tmp_path: Path) -> None:
    db_file = tmp_path / "cli_test.db"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "herb",
            "Amalaki",
            "-d",
            str(db_file),
            "-a",
            "Rasa=Amla",
            "-a",
            "Virya=Sheeta",
            "-a",
            "Custom.SourceText=Charaka Samhita",
        ],
    )
    assert result.exit_code == 0
    assert "Inserted herb 1: Amalaki" in result.output

    almanac = AyurvedicAlmanac(db_file)
    attrs = almanac.herb_attributes(1)
    fields = {a["field_name"]: a["value"] for a in attrs}
    assert fields["Rasa"] == "Amla"
    assert fields["Virya"] == "Sheeta"
    assert fields["Custom.SourceText"] == "Charaka Samhita"
