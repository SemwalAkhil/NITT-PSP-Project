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
import re
import sqlite3
import urllib.parse
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

    # HTML Stage C status view was removed (meaningless to outside users) -> 404
    res_stc = client.get("/stage-c/status")
    assert res_stc.status_code == 404

    # JSON API is kept
    res_api = client.get("/api/stage-c/status")
    assert res_api.status_code == 200
    assert res_api.json()["schema_version"] == 2

    # Trigger Stage C upgrade from GUI (redirects to dashboard /)
    res_upg = client.post(
        "/stage-c/upgrade",
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=True,
    )
    assert res_upg.status_code == 200

    # JSON API now reports Version 3
    res_api3 = client.get("/api/stage-c/status")
    assert res_api3.status_code == 200
    assert res_api3.json()["schema_version"] == 3


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
    herb_direct = {"id": 1, "source": "CCRAS DRAVYA", "source_record_id": 13, "botanical_name": "Adhatoda vasica"}
    url = herb_image_url(herb_direct)
    assert url == "https://dravya.ccras.org.in/resources/views/admin/required/upload/13.jpg"

    # Inferred via botanical name from herb_names.csv (CCRAS source -> uses ccras_id 15)
    herb_inferred = {"id": 99, "source": "CCRAS DRAVYA", "source_record_id": None, "botanical_name": "Adhatoda vasica"}
    url2 = herb_image_url(herb_inferred)
    assert url2 == "https://dravya.ccras.org.in/resources/views/admin/required/upload/15.jpg"

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
    assert herb_1.get_name("hi") in ("तालीसपत्र", "Talispatra")
    assert herb_1.get_name("ta") in ("தாளிசபத்திரி", "Talisapatri")

    # Resolve by botanical name
    herb_adh = resolve_herb("Adhatoda vasica")
    assert herb_adh is not None
    assert herb_adh.id == 13
    assert herb_adh.get_name("hi") in ("अडूसा", "Adusa")

    # Search in Tamil
    tamil_results = search_herb_glossary("ஆடாதொடை", language="ta") or search_herb_glossary("Adathodai", language="ta")
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
    assert "Adusa" in result.stdout or "अडूसा" in result.stdout



# ============================================================================
# 8. Milestone F Tests: Image Proxy, Photo Upload, Language Bar, Cache Warmer
# ============================================================================

def test_herb_image_route_serves_cached_file(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Tulsi", source="CCRAS DRAVYA", botanical_name="Ocimum sanctum", source_record_id=99)
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
    herb_id = int(herb_url.split("/")[-1].split("?")[0])

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
    herb_id = db.add_herb("TestHerb", source="CCRAS DRAVYA", source_record_id=123)

    # Simulate already cached file
    cache_dir = tmp_path / "herbal_almanac_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{herb_id}.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    stats = warm_cache(database_path=db_file, delay=0.0)
    assert stats["total"] == 1
    assert stats["skipped"] == 1
    assert stats["cached"] == 0


def test_favicon_route_and_link(tmp_path: Path):
    client, _ = make_test_client(tmp_path)
    res_ico = client.get("/favicon.ico")
    assert res_ico.status_code == 200
    assert "image/svg+xml" in res_ico.headers["content-type"]
    assert b"<svg" in res_ico.content

    res_dash = client.get("/")
    assert res_dash.status_code == 200
    assert '<link rel="icon" type="image/svg+xml"' in res_dash.text
    assert 'styles.css?v=' in res_dash.text


def test_multilingual_herb_names_and_language_bar_on_herbs_page(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    # Add herb 1 (Talisha / Abies webbiana)
    h_tal = db.add_herb("Talisha", botanical_name="Abies webbiana")
    # Add herb with botanical name Aegle marmelos (Bael / Bilva, ID 16 in glossary)
    h_bael = db.add_herb("Bael", botanical_name="Aegle marmelos")
    # Add a fictional herb that has no glossary translation
    h_none = db.add_herb("Fictional Herb XYZ", botanical_name="Nonexistent species")

    # 1. /herbs?language=hi renders Devanagari 'बेल' with lang="hi"
    res_hi = client.get("/herbs?language=hi")
    assert res_hi.status_code == 200
    assert 'lang="hi"' in res_hi.text
    assert "बेल" in res_hi.text
    assert '<input type="hidden" name="language" value="hi">' in res_hi.text

    # 2. /herbs?language=ta renders Tamil script 'வில்வம்' with lang="ta"
    res_ta = client.get("/herbs?language=ta")
    assert res_ta.status_code == 200
    assert 'lang="ta"' in res_ta.text
    assert "வில்வம்" in res_ta.text
    assert "(name not available in Tamil)" in res_ta.text

    # 3. /herbs/1?language=ur contains dir="rtl" on the Urdu name span
    res_ur = client.get("/herbs/1?language=ur")
    assert res_ur.status_code == 200
    assert 'dir="rtl"' in res_ur.text
    assert "تالیس پتر" in res_ur.text

    # 4. Pagination links keep language param
    for i in range(15):
        db.add_herb(f"Fever Herb {i}", botanical_name=f"Fever species {i}")

    res_page = client.get("/herbs?language=hi&q=fever")
    assert res_page.status_code == 200
    assert "language=hi" in res_page.text


def test_text_scaling_rem_and_accessibility_font_size(tmp_path: Path):
    from herbal_almanac.web_app import STYLESHEET_PATH

    css = STYLESHEET_PATH.read_text(encoding="utf-8")

    # 1. Assert NO font-size: \d+px in styles.css
    px_matches = re.findall(r"font-size:\s*\d+(?:\.\d+)?px", css)
    assert px_matches == [], f"Found hardcoded font-size px values in styles.css: {px_matches}"

    # 2. Assert root html rules for data-font-size exist and change font size
    assert 'html[data-font-size="xl"]' in css
    assert 'html[data-font-size="sm"]' in css
    assert 'html[data-font-size="md"]' in css
    assert 'html[data-font-size="lg"]' in css

    # 3. Assert base sidebar width uses rem (responsive scaling)
    assert ".sidebar{width:18rem;" in css
    assert ".main-area{margin-left:18rem;" in css


def test_inline_svg_icons_and_no_emojis_in_base_nav():
    from jinja2 import Environment, FileSystemLoader

    templates_dir = Path(__file__).resolve().parent.parent / "src" / "herbal_almanac" / "templates"
    env = Environment(loader=FileSystemLoader(templates_dir))

    # 1. Test _icons.html renders valid SVG for all defined icon names
    icon_template = env.from_string("{% from '_icons.html' import icon %}{{ icon(name, size=size) }}")
    icon_names = [
        "home",
        "book-open",
        "leaf",
        "heart-pulse",
        "link",
        "file-text",
        "database",
        "plus",
        "search",
        "arrow-up-right",
        "accessibility",
        "download",
        "upload",
        "trash",
    ]
    for name in icon_names:
        rendered = icon_template.render(name=name, size=18)
        assert "<svg" in rendered
        assert "</svg>" in rendered
        assert f'class="icon icon-{name}' in rendered
        assert 'viewBox="0 0 24 24"' in rendered
        assert 'aria-hidden="true"' in rendered

    # 2. Test base.html sidebar nav does not contain emojis
    base_html = (templates_dir / "base.html").read_text(encoding="utf-8")
    sidebar_match = re.search(r'<aside class="sidebar".*?</aside>', base_html, re.DOTALL)
    assert sidebar_match is not None
    sidebar_text = sidebar_match.group(0)

    # Emoji unicode ranges: Miscellaneous Symbols and Pictographs, Emoticons, Transport/Map, Supplemental Symbols
    emoji_pattern = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
    emojis_found = emoji_pattern.findall(sidebar_text)
    assert emojis_found == [], f"Found emoji characters in sidebar nav: {emojis_found}"


def test_template_duplicate_attributes_linter(tmp_path: Path):
    from scripts.lint_templates import lint_all_pages

    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Bilva", botanical_name="Aegle marmelos", source_record_id=16)
    illness_id = db.add_illness("KAsa")
    db.add_treatment(herb_id, illness_id)

    errors = lint_all_pages(client, herb_id, illness_id)
    assert errors == [], f"Found duplicate HTML attributes: {errors}"


def test_no_emojis_in_any_templates():
    templates_dir = Path(__file__).resolve().parent.parent / "src" / "herbal_almanac" / "templates"
    emoji_pattern = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
    allowed_plain_arrows = {"\u2192", "\u2197", "\u2190", "\u2191", "\u2193", "→", "↗", "←", "↑", "↓"}
    violations: list[str] = []

    for template_file in templates_dir.glob("*.html"):
        content = template_file.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            matches = emoji_pattern.findall(line)
            real_matches = [m for m in matches if m not in allowed_plain_arrows]
            if real_matches:
                violations.append(f"{template_file.name}:{i} contains {real_matches}")

    assert violations == [], f"Found emojis in templates: {violations}"


def test_multilingual_herb_search_regression(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    db.add_herb("Bael", botanical_name="Aegle marmelos", source_record_id=16)
    db.add_herb("Neem", botanical_name="Azadirachta indica", source_record_id=47)

    # 1. Search Hindi "बेल" -> returns Bael, not Neem
    res_hi = client.get("/herbs?q=" + urllib.parse.quote("बेल") + "&language=hi")
    assert res_hi.status_code == 200
    assert "बेल" in res_hi.text or "Bael" in res_hi.text
    assert "Neem" not in res_hi.text

    # 2. Search Tamil "வில்வம்" -> returns Bael, not Neem
    res_ta = client.get("/herbs?q=" + urllib.parse.quote("வில்வம்") + "&language=ta")
    assert res_ta.status_code == 200
    assert "வில்வம்" in res_ta.text or "Bael" in res_ta.text
    assert "Neem" not in res_ta.text

    # 3. Search Telugu "మారేడు" -> returns Bael, not Neem
    res_te = client.get("/herbs?q=" + urllib.parse.quote("మారేడు") + "&language=te")
    assert res_te.status_code == 200
    assert "మారేడు" in res_te.text or "Bael" in res_te.text
    assert "Neem" not in res_te.text

    # 4. Search Hindi "नीम" -> returns Neem, not Bael
    res_neem = client.get("/herbs?q=" + urllib.parse.quote("नीम") + "&language=hi")
    assert res_neem.status_code == 200
    assert "नीम" in res_neem.text or "Neem" in res_neem.text
    assert "Bael" not in res_neem.text


def test_treatments_multilingual_herb_names_in_glossary(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb("Bael", botanical_name="Aegle marmelos", source_record_id=16)
    illness_id = db.add_illness("KAsa")
    db.add_treatment(herb_id, illness_id)

    res = client.get("/treatments?language=hi")
    assert res.status_code == 200
    assert "बेल" in res.text


def test_url_query_encoding_and_clear_search_preserves_language(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    db.add_herb("Bael", botanical_name="Aegle marmelos", source_record_id=16)
    db.add_illness("KAsa")

    raw_query = "a & b#c ü"
    enc_q = urllib.parse.quote(raw_query)

    # Export links and pagination encode characters safely
    res_herbs = client.get(f"/herbs?q={enc_q}&language=hi")
    assert res_herbs.status_code == 200
    csv_match = re.search(r'href="(/export/herbs\.csv\?[^"]+)"', res_herbs.text)
    assert csv_match is not None, "CSV export link not found"
    parsed_csv = urllib.parse.urlsplit(csv_match.group(1))
    qs_csv = urllib.parse.parse_qs(parsed_csv.query)
    assert qs_csv["q"][0] == raw_query

    # /illnesses "Clear search" preserves current_language
    res_ill = client.get(f"/illnesses?q={enc_q}&language=ta")
    assert res_ill.status_code == 200
    clear_match = re.search(r'href="([^"]*illnesses\?[^"]+)">Clear search', res_ill.text)
    assert clear_match is not None, "Clear search link not found on illnesses"
    parsed_clear = urllib.parse.urlsplit(clear_match.group(1))
    qs_clear = urllib.parse.parse_qs(parsed_clear.query)
    assert qs_clear["language"][0] == "ta"


def test_user_visible_a11y_string_absent(tmp_path: Path):
    client, db = make_test_client(tmp_path)
    db.add_herb("Bael", botanical_name="Aegle marmelos", source_record_id=16)

    for path in ["/", "/herbs", "/illnesses", "/treatments", "/attributes", "/records", "/guide"]:
        res = client.get(path)
        assert res.status_code == 200
        # Assert user-visible string 'A11y' does not appear anywhere in rendered HTML
        assert "A11y" not in res.text, f"'A11y' found in rendered HTML of {path}"


def test_stop_source_id_collision_non_ccras_source(tmp_path: Path):
    """(1) herb with source 'https://mytestwebsite.com/' and source_record_id=1
    -> get_plant_id is None, no Hindi/Tamil CCRAS names on /herbs?language=hi,
    search_herbs('Himalayan Silver Fir') and ('तालीसपत्र') do NOT return it,
    its image URL is the placeholder."""
    from herbal_almanac.herb_glossary import get_herb_glossary_store
    from herbal_almanac.herb_view import herb_image_url

    client, db = make_test_client(tmp_path)
    # Plant 1 in CCRAS glossary is Talisha / Himalayan Silver Fir / तालीसपत्र
    herb_id = db.add_herb(
        english_name="My Custom Herb",
        source="https://mytestwebsite.com/",
        source_record_id=1,
    )
    herb = db.get_herb(herb_id)

    # 1. get_plant_id is None
    store = get_herb_glossary_store()
    assert store.get_plant_id(herb) is None

    # 2. image URL is None / image endpoint returns SVG placeholder
    assert herb_image_url(herb) is None
    img_res = client.get(f"/herbs/{herb_id}/image")
    assert img_res.status_code == 200
    assert "image/svg+xml" in img_res.headers["content-type"]

    # 3. No Hindi/Tamil CCRAS names on /herbs?language=hi
    res_hi = client.get("/herbs?language=hi")
    assert res_hi.status_code == 200
    assert "तालीसपत्र" not in res_hi.text

    # 4. search_herbs('Himalayan Silver Fir') and ('तालीसपत्र') do NOT return it
    assert not any(h["id"] == herb_id for h in db.search_herbs("Himalayan Silver Fir"))
    assert not any(h["id"] == herb_id for h in db.search_herbs("तालीसपत्र"))


def test_ccras_source_resolves_to_glossary_row_1(tmp_path: Path):
    """(2) herb with source 'CCRAS DRAVYA' and source_record_id=1
    still resolves to glossary row 1 (names, search, image URL)."""
    from herbal_almanac.herb_glossary import get_herb_glossary_store
    from herbal_almanac.herb_view import herb_image_url

    client, db = make_test_client(tmp_path)
    herb_id = db.add_herb(
        english_name="Talisha",
        source="CCRAS DRAVYA",
        source_record_id=1,
    )
    herb = db.get_herb(herb_id)

    store = get_herb_glossary_store()
    assert store.get_plant_id(herb) == 1
    assert herb_image_url(herb) == "https://dravya.ccras.org.in/resources/views/admin/required/upload/1.jpg"

    matches = db.search_herbs("तालीसपत्र")
    assert any(h["id"] == herb_id for h in matches)


def test_manual_herb_matching_botanical_name_resolves(tmp_path: Path):
    """(3) manual herb with botanical_name 'Abies webbiana' still matches by botanical name."""
    from herbal_almanac.herb_glossary import get_herb_glossary_store

    _, db = make_test_client(tmp_path)
    herb_id = db.add_herb(
        english_name="My Garden Conifer",
        botanical_name="Abies webbiana",
        source="manual",
    )
    herb = db.get_herb(herb_id)

    store = get_herb_glossary_store()
    assert store.get_plant_id(herb) == 1


def test_post_add_herb_ignores_posted_source_record_id_and_redirects_with_id(tmp_path: Path):
    """(4) POST /herbs/add ignores a posted source_record_id.
    (5) new herb redirect shows the assigned ID."""
    client, db = make_test_client(tmp_path)

    res_post = client.post(
        "/herbs/add",
        data={
            "english_name": "Test Mint",
            "botanical_name": "Mentha spicata",
            "source": "manual",
            "source_record_id": 9999,  # must be ignored!
            "source_url": "https://example.com/mint",
        },
        headers={"origin": "http://testserver", "host": "testserver"},
        follow_redirects=False,
    )
    assert res_post.status_code == 303
    loc = res_post.headers["location"]
    assert loc.startswith("/herbs/")

    # Parse herb_id from redirect URL
    herb_id = int(loc.split("/herbs/")[1].split("?")[0])
    herb = db.get_herb(herb_id)
    assert herb["source_record_id"] is None, "source_record_id must be None for manual herbs"
    assert herb["source"] == "manual"

    # Follow redirect and verify assigned Almanac ID is shown in success message
    res_detail = client.get(loc)
    assert res_detail.status_code == 200
    assert f"Herb added with ID {herb_id}" in res_detail.text







