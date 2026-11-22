"""Herbal Almanac — Web Parity, Exports, Multilingual Herb Glossary & Accessibility Tests.

Hermetic offline tests covering:
1. Web forms for adding herb, illness, and treatment links with validation and CSRF checks.
2. Treatment explorer, attributes explorer, records hub, and Stage C status views.
3. CSV and JSON export endpoints with formula injection protection and UTF-8 BOM encoding.
4. Herb images URL helper and SVG placeholder verification.
5. Multilingual herb glossary loader, resolver, search_herbs integration, and CLI language filter.
6. Accessibility landmarks, skip link, and user preference controls.
7. Coverage script verification.
"""

from __future__ import annotations

import io
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.herb_glossary import (
    get_herb_glossary_store,
    resolve_herb,
    search_herb_glossary,
    tolerant_herb_key,
)
from herbal_almanac.herb_view import herb_image_url, herb_vernacular_table
from herbal_almanac.web_app import create_app, sanitize_csv_cell
import herbal_almanac.cli as cli
from scripts.herb_name_coverage import audit_herb_coverage


def make_test_client(tmp_path: Path) -> tuple[TestClient, AyurvedicAlmanac]:
    db_path = tmp_path / "test_parity.db"
    db = AyurvedicAlmanac(db_path)
    db.create_database()
    app = create_app(db_path)
    client = TestClient(app)
    return client, db


# ============================================================================
# 1. Web Form Tests (Add Herb, Illness, Treatment)
# ============================================================================

def test_add_herb_form_and_post_success(tmp_path: Path):
    client, db = make_test_client(tmp_path)

    # GET form
    res_get = client.get("/herbs/add")
    assert res_get.status_code == 200
    assert "Add Herb Record" in res_get.text
    assert 'name="english_name"' in res_get.text

    # POST valid herb
    res_post = client.post(
        "/herbs/add",
        data={
            "english_name": "Ashwagandha",
            "botanical_name": "Withania somnifera",
            "family": "Solanaceae",
            "source": "manual",
            "source_record_id": 42,
            "source_url": "https://dravya.ccras.org.in/plant/42",
        },
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert res_post.status_code == 303
    assert res_post.headers["location"].startswith("/herbs/")

    # Follow redirect
    detail_res = client.get(res_post.headers["location"])
    assert detail_res.status_code == 200
    assert "Ashwagandha" in detail_res.text
    assert "Withania somnifera" in detail_res.text


def test_add_herb_validation_and_csrf_protection(tmp_path: Path):
    client, _ = make_test_client(tmp_path)

    # Empty name -> 400
    res_empty = client.post(
        "/herbs/add",
        data={"english_name": "   "},
        headers={"origin": "http://testserver", "host": "testserver"},
    )
    assert res_empty.status_code == 400
    assert "english_name cannot be empty" in res_empty.text

    # Malicious origin -> 403
    res_csrf = client.post(
        "/herbs/add",
        data={"english_name": "Tulsi"},
        headers={"origin": "http://evil-attacker.com", "host": "testserver"},
    )
    assert res_csrf.status_code == 403
    assert "Cross-site origin verification failed" in res_csrf.text


def test_add_illness_form_and_post_duplicate(tmp_path: Path):
    client, db = make_test_client(tmp_path)

    # GET form
    res_get = client.get("/illnesses/add")
    assert res_get.status_code == 200
    assert "Add Illness / Indication" in res_get.text

    # POST valid illness
    res_post = client.post(
        "/illnesses/add",
        data={"english_name": "Jvara"},
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert res_post.status_code == 303
    assert res_post.headers["location"].startswith("/illnesses/")

    # POST duplicate illness -> 400 with friendly message
    res_dup = client.post(
        "/illnesses/add",
        data={"english_name": "Jvara"},
        headers={"origin": "http://testserver", "host": "testserver"},
    )
    assert res_dup.status_code == 400
    assert "Error:" in res_dup.text


def test_add_treatment_form_and_post(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    h_id = db.add_herb("Vasa", botanical_name="Adhatoda vasica")
    i_id = db.add_illness("KAsa")

    # GET treatment form
    res_get = client.get(f"/treatments/add?herb_id={h_id}")
    assert res_get.status_code == 200
    assert "Link Herb to Illness" in res_get.text
    assert "Vasa" in res_get.text

    # POST link
    res_post = client.post(
        "/treatments/add",
        data={"herb_id": h_id, "illness_id": i_id},
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert res_post.status_code == 303
    assert res_post.headers["location"] == "/treatments"

    # Verify link exists in treatment details
    treatments = db.treatment_details(h_id)
    assert len(treatments) == 1
    assert treatments[0]["id"] == i_id


# ============================================================================
# 2. Explorer Views (Treatments, Attributes, Records, Stage C Status)
# ============================================================================

def test_treatments_explorer_view(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    h1 = db.add_herb("Tulsi", botanical_name="Ocimum sanctum")
    h2 = db.add_herb("Neem", botanical_name="Azadirachta indica")
    i1 = db.add_illness("Cough")
    i2 = db.add_illness("Fever")
    db.add_treatment(h1, i1)
    db.add_treatment(h2, i2)

    # List all
    res = client.get("/treatments")
    assert res.status_code == 200
    assert "Treatments Directory" in res.text
    assert "Tulsi" in res.text
    assert "Neem" in res.text

    # Filter
    res_filtered = client.get("/treatments?q=Tulsi")
    assert res_filtered.status_code == 200
    assert "Tulsi" in res_filtered.text
    assert "Neem" not in res_filtered.text


def test_attributes_explorer_and_herb_attributes_view(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    h_id = db.add_herb("Vasa", botanical_name="Adhatoda vasica")
    with db._connection() as conn:
        conn.execute(
            """
            INSERT INTO herb_attributes (herb_id, field_name, value, source_text, source_language, machine_generated, verification_status)
            VALUES (?, 'Rasa.Name', 'Tikta', 'Charaka Samhita', 'sa', 0, 'verified')
            """,
            (h_id,),
        )

    # Global attributes view
    res_global = client.get("/attributes")
    assert res_global.status_code == 200
    assert "Source Attributes Directory" in res_global.text
    assert "Tikta" in res_global.text

    # Herb-specific attributes view
    res_herb = client.get(f"/herbs/{h_id}/attributes")
    assert res_herb.status_code == 200
    assert "Source Attributes for Vasa" in res_herb.text
    assert "Tikta" in res_herb.text


def test_records_hub_and_stage_c_status_view(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    h_id = db.add_herb("Haritaki", botanical_name="Terminalia chebula")

    # Records hub
    res_rec = client.get("/records?group=herbs")
    assert res_rec.status_code == 200
    assert "Records &amp; Data Hub" in res_rec.text
    assert "Haritaki" in res_rec.text

    # Stage C status view
    res_stc = client.get("/stage-c/status")
    assert res_stc.status_code == 200
    assert "Stage C Dravyaguna Status" in res_stc.text
    assert "Schema Capability" in res_stc.text

    # Trigger Stage C upgrade from GUI
    res_upg = client.post(
        "/stage-c/upgrade",
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=True,
    )
    assert res_upg.status_code == 200
    assert "Stage C Active" in res_upg.text


# ============================================================================
# 3. Export Endpoints & CSV Formula Injection Protection
# ============================================================================

def test_csv_formula_injection_sanitization():
    # Dangerous prefixes =, +, -, @
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-5+2") == "'-5+2"
    assert sanitize_csv_cell("@SUM(1,2)") == "'@SUM(1,2)"
    # Safe values
    assert sanitize_csv_cell("Tulsi") == "Tulsi"
    assert sanitize_csv_cell(123) == "123"
    assert sanitize_csv_cell(None) == ""


def test_export_herbs_csv_and_json(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    db.add_herb("=DangerousHerb", botanical_name="Formula plant", family="Botanica")
    db.add_herb("NormalHerb", botanical_name="Safe plant")

    # CSV Export
    res_csv = client.get("/export/herbs.csv")
    assert res_csv.status_code == 200
    assert res_csv.headers["content-type"].startswith("text/csv")
    assert 'filename="herbs.csv"' in res_csv.headers["content-disposition"]
    # Check UTF-8 BOM
    assert res_csv.content.startswith(b"\xef\xbb\xbf")
    csv_text = res_csv.content.decode("utf-8")
    assert "'=DangerousHerb" in csv_text
    assert "NormalHerb" in csv_text

    # JSON Export
    res_json = client.get("/export/herbs.json")
    assert res_json.status_code == 200
    assert res_json.headers["content-type"].startswith("application/json")
    data = res_json.json()
    assert len(data) == 2
    names = [h["english_name"] for h in data]
    assert "=DangerousHerb" in names


def test_export_treatments_and_herb_detail(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    h_id = db.add_herb("Vasa", botanical_name="Adhatoda vasica")
    i_id = db.add_illness("KAsa")
    db.add_treatment(h_id, i_id)

    # Treatments CSV & JSON
    res_t_csv = client.get("/export/treatments.csv")
    assert res_t_csv.status_code == 200
    assert res_t_csv.content.startswith(b"\xef\xbb\xbf")
    assert "Vasa" in res_t_csv.content.decode("utf-8")

    res_t_json = client.get("/export/treatments.json")
    assert res_t_json.status_code == 200
    assert res_t_json.json()[0]["herb_name"] == "Vasa"

    # Single herb export
    res_h_csv = client.get(f"/herbs/{h_id}/export.csv")
    assert res_h_csv.status_code == 200
    res_h_json = client.get(f"/herbs/{h_id}/export.json")
    assert res_h_json.status_code == 200
    assert res_h_json.json()["herb"]["english_name"] == "Vasa"


# ============================================================================
# 4. Herb Images & SVG Placeholder
# ============================================================================

def test_herb_image_url_resolution():
    # Direct source_record_id
    herb_direct = {"id": 1, "source_record_id": 13, "botanical_name": "Adhatoda vasica"}
    url = herb_image_url(herb_direct)
    assert url == "https://dravya.ccras.org.in/resources/views/admin/required/upload/13.jpg"

    # Inferred via botanical name from herb_names.csv
    herb_inferred = {"id": 99, "source_record_id": None, "botanical_name": "Adhatoda vasica"}
    url2 = herb_image_url(herb_inferred)
    assert url2 == "https://dravya.ccras.org.in/resources/views/admin/required/upload/13.jpg"

    # Unknown herb returns None
    assert herb_image_url({"id": 100, "botanical_name": "Unknown species"}) is None


def test_placeholder_herb_svg_served(tmp_path: Path):
    client, _ = make_test_client(tmp_path)
    res = client.get("/static/placeholder-herb.svg")
    assert res.status_code == 200
    assert "svg" in res.headers["content-type"].lower()
    assert "<svg" in res.text


# ============================================================================
# 5. Multilingual Herb Glossary & Vernacular Search
# ============================================================================

def test_herb_glossary_loading_and_resolution():
    store = get_herb_glossary_store()
    assert len(store.all_herbs) > 300

    # Test key normalization
    assert tolerant_herb_key("Vāsā") == tolerant_herb_key("Vasa")
    assert tolerant_herb_key("Chinchā") == tolerant_herb_key("cinca")

    # Resolve by ID
    herb_1 = store.resolve_by_id(1)
    assert herb_1 is not None
    assert herb_1.botanical_name == "Abies webbiana"
    assert herb_1.get_name("hi") == "Talispatra"
    assert herb_1.get_name("ta") == "Talisapatri"

    # Resolve by botanical name
    herb_adh = resolve_herb("Adhatoda vasica")
    assert herb_adh is not None
    assert herb_adh.id == 13
    assert herb_adh.get_name("hi") == "Adusa"

    # Search in Tamil
    tamil_results = search_herb_glossary("Adathodai", language="ta")
    assert any(h.id == 13 for h in tamil_results)


def test_database_search_herbs_multilingual(tmp_path: Path):
    _, db = make_test_client(tmp_path)
    db.add_herb("Vasa", botanical_name="Adhatoda vasica", source_record_id=13)

    # Search in Hindi ("Adusa")
    matches_hi = db.search_herbs("Adusa")
    assert len(matches_hi) >= 1
    assert matches_hi[0]["english_name"] == "Vasa"

    # Search in Tamil ("Adathodai")
    matches_ta = db.search_herbs("Adathodai")
    assert len(matches_ta) >= 1
    assert matches_ta[0]["english_name"] == "Vasa"


def test_herb_vernacular_table():
    herb = {"id": 1, "source_record_id": 13, "botanical_name": "Adhatoda vasica"}
    table = herb_vernacular_table(herb)
    assert len(table) >= 10
    langs = [row["language"] for row in table]
    assert "Hindi" in langs
    assert "Tamil" in langs
    assert "Sanskrit" in langs


# ============================================================================
# 6. Accessibility & Layout
# ============================================================================

def test_accessibility_landmarks_and_controls(tmp_path: Path):
    client, _ = make_test_client(tmp_path)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Skip link
    assert 'class="skip-link"' in html
    assert 'href="#main-content"' in html

    # Semantic landmarks
    assert 'role="banner"' in html
    assert 'aria-label="Main navigation"' in html
    assert 'id="main-content"' in html
    assert 'role="main"' in html
    assert 'role="contentinfo"' in html

    # Accessibility drawer & attributes
    assert 'id="a11y-panel"' in html
    assert 'data-set-theme' in html
    assert 'data-set-font-size' in html
    assert 'data-set-contrast' in html
    assert 'data-set-font' in html


# ============================================================================
# 7. Coverage Script
# ============================================================================

def test_herb_coverage_script(tmp_path: Path):
    db_file = tmp_path / "coverage_test.db"
    db = AyurvedicAlmanac(db_file)
    db.create_database()
    db.add_herb("Vasa", botanical_name="Adhatoda vasica", source_record_id=13)
    db.add_herb("UnknownHerb", botanical_name="Mystery plant")

    report = audit_herb_coverage(db_file)
    assert report["total_herbs"] == 2
    assert report["resolved_count"] == 1
    assert report["unresolved_count"] == 1
    assert report["resolved_percentage"] == 50.0
    assert report["lang_counts"]["Hindi"] >= 1


def test_cli_herbs_language_option(tmp_path: Path):
    from typer.testing import CliRunner
    from herbal_almanac.cli import app
    db_file = tmp_path / "cli_lang.db"
    db = AyurvedicAlmanac(db_file)
    db.create_database()
    db.add_herb("Vasa", botanical_name="Adhatoda vasica", source_record_id=13)

    runner = CliRunner()
    result = runner.invoke(app, ["herbs", "--database", str(db_file), "--language", "hi"])
    assert result.exit_code == 0
    assert "Adusa" in result.stdout



# ============================================================================
# 8. Milestone F Tests: Image Proxy, Photo Upload, Language Bar, Cache Warmer
# ============================================================================

def test_herb_image_route_serves_cached_file(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Tulsi", botanical_name="Ocimum sanctum", source_record_id=99)
    cache_dir = tmp_path / "herbal_almanac_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    (cache_dir / f"{herb_id}.jpg").write_bytes(fake_jpeg)

    res = client.get(f"/herbs/{herb_id}/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content == fake_jpeg


def test_herb_image_route_fallback_placeholder(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("NoImageHerb")

    res = client.get(f"/herbs/{herb_id}/image")
    assert res.status_code == 200
    assert "image/svg+xml" in res.headers["content-type"]
    assert b"<svg" in res.content


def test_user_photo_upload_valid_jpeg_and_serving(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Vasa", botanical_name="Adhatoda vasica")

    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + (b"\x00" * 100)
    files = {"photo": ("vasa.jpg", valid_jpeg, "image/jpeg")}
    res = client.post(
        f"/herbs/{herb_id}/photo",
        files=files,
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == f"/herbs/{herb_id}"

    # Photo is now served by the image proxy route with priority over CCRAS
    img_res = client.get(f"/herbs/{herb_id}/image")
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/jpeg"
    assert img_res.content == valid_jpeg

    # Detail page reflects user photo credit
    detail_res = client.get(f"/herbs/{herb_id}")
    assert detail_res.status_code == 200
    assert "User-contributed photo" in detail_res.text


def test_user_photo_upload_rejects_spoofed_magic_bytes(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("FakeHerb")

    # Text content disguised as .jpg
    spoofed_file = b"<html><script>alert(1)</script></html>"
    files = {"photo": ("spoof.jpg", spoofed_file, "image/jpeg")}
    res = client.post(
        f"/herbs/{herb_id}/photo",
        files=files,
        headers={"origin": "http://testserver", "host": "testserver"},
    )
    assert res.status_code == 415
    assert "Unsupported image format" in res.text


def test_user_photo_delete(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Ashoka", botanical_name="Saraca asoca")

    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (b"\x00" * 50)
    client.post(
        f"/herbs/{herb_id}/photo",
        files={"photo": ("ashoka.png", valid_png, "image/png")},
        headers={"origin": "http://testserver", "host": "testserver"},
    )

    # Delete photo
    del_res = client.post(
        f"/herbs/{herb_id}/photo/delete",
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert del_res.status_code == 303

    # Subsequent image request falls back to placeholder
    img_res = client.get(f"/herbs/{herb_id}/image")
    assert img_res.status_code == 200
    assert "image/svg+xml" in img_res.headers["content-type"]


def test_add_herb_with_photo_creation(tmp_path: Path):
    client, _ = make_test_client(tmp_path)

    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + (b"\x00" * 60)
    res = client.post(
        "/herbs/add",
        data={"english_name": "Neem", "botanical_name": "Azadirachta indica"},
        files={"photo": ("neem.jpg", valid_jpeg, "image/jpeg")},
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    herb_url = res.headers["location"]
    herb_id = int(herb_url.split("/")[-1])

    # Photo was uploaded and is now available
    img_res = client.get(f"/herbs/{herb_id}/image")
    assert img_res.status_code == 200
    assert img_res.content == valid_jpeg


def test_language_bar_rendered_and_propagated(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Vasa", botanical_name="Adhatoda vasica")
    illness_id = db.add_illness("KAsa")
    db.add_treatment(herb_id, illness_id)

    # Herb detail language bar
    herb_res = client.get(f"/herbs/{herb_id}?language=hi")
    assert herb_res.status_code == 200
    assert 'class="language-bar"' in herb_res.text
    assert 'class="lang-pill active"' in herb_res.text or 'lang-pill active' in herb_res.text
    assert "हिन्दी" in herb_res.text

    # Illness detail language bar
    illness_res = client.get(f"/illnesses/{illness_id}?language=sa")
    assert illness_res.status_code == 200
    assert 'class="language-bar"' in illness_res.text
    assert "संस्कृतम्" in illness_res.text


def test_warm_image_cache_script(tmp_path: Path):
    from scripts.warm_image_cache import warm_cache
    db_file = tmp_path / "warm_test.db"
    db = AyurvedicAlmanac(db_file)
    db.create_database()
    herb_id = db.add_herb("TestHerb", source_record_id=123)

    # Simulate already cached file
    cache_dir = tmp_path / "herbal_almanac_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{herb_id}.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    stats = warm_cache(database_path=db_file, delay=0.0)
    assert stats["total"] == 1
    assert stats["skipped"] == 1
    assert stats["cached"] == 0
