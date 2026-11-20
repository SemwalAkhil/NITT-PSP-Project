from fastapi.testclient import TestClient

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.web_app import create_app


def make_client(tmp_path):
    database_path = tmp_path / "web-gui.db"
    database = AyurvedicAlmanac(database_path)
    database.create_database()
    return TestClient(create_app(database_path)), database


def test_dashboard_shows_database_counts_and_recent_herbs(tmp_path):
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    h2 = database.add_herb("Neem", botanical_name="Azadirachta indica")
    i1 = database.add_illness("KAsa")
    i2 = database.add_illness("Jvara")
    database.add_treatment(h1, i1)
    database.add_treatment(h2, i1)
    database.add_treatment(h1, i2)

    summary = database.dashboard_summary()
    assert "top_illnesses" in summary
    assert len(summary["top_illnesses"]) == 2
    assert summary["top_illnesses"][0]["english_name"] == "KAsa"
    assert summary["top_illnesses"][0]["herb_count"] == 2
    assert summary["top_illnesses"][1]["english_name"] == "Jvara"
    assert summary["top_illnesses"][1]["herb_count"] == 1

    response = client.get("/")

    assert response.status_code == 200
    assert "Herbal Almanac" in response.text
    assert "Ocimum tenuiflorum" in response.text
    assert "Frequent conditions in your collection" in response.text
    assert "Cough" in response.text
    assert "Original: KAsa" in response.text
    assert "2 linked herbs" in response.text
    assert f"/illnesses/{i1}" in response.text
    assert "View all illnesses" in response.text


def test_herb_explorer_lists_and_searches_records(tmp_path):
    client, database = make_client(tmp_path)
    database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    database.add_herb("Neem", botanical_name="Azadirachta indica")

    response = client.get("/herbs")
    assert response.status_code == 200
    assert "Tulsi" in response.text
    assert "Neem" in response.text

    search_response = client.get("/herbs", params={"q": "tulsi"})
    assert search_response.status_code == 200
    assert "Tulsi" in search_response.text
    assert "Neem" not in search_response.text


def test_herb_detail_shows_identity_attributes_doshas_and_treatments(tmp_path):
    client, database = make_client(tmp_path)
    herb_id = database.add_herb(
        "Tulsi", botanical_name="Ocimum tenuiflorum", family="Lamiaceae"
    )
    illness_id = database.add_illness("Cough")
    database.add_treatment(herb_id, illness_id)

    response = client.get(f"/herbs/{herb_id}")

    assert response.status_code == 200
    assert "Ocimum tenuiflorum" in response.text
    assert "Lamiaceae" in response.text
    assert "Cough" in response.text
    assert "Plant characteristics" in response.text
    assert "Dosha effects" in response.text


def test_missing_herb_returns_not_found(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/herbs/999")

    assert response.status_code == 404


def test_herb_search_rejects_unreasonably_long_query(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/herbs", params={"q": "x" * 101})

    assert response.status_code == 422


def test_dashboard_handles_empty_database(tmp_path):
    client, database = make_client(tmp_path)
    summary = database.dashboard_summary()
    assert summary["top_illnesses"] == []

    response = client.get("/")

    assert response.status_code == 200
    assert "Your library is ready to grow" in response.text
    assert "No therapeutic links recorded yet" in response.text

def test_stylesheet_is_served_with_css_content_type(tmp_path):
    client, _ = make_client(tmp_path)

    page = client.get("/")
    stylesheet_url = "/static/styles.css"

    assert page.status_code == 200
    assert stylesheet_url in page.text

    response = client.get(stylesheet_url)

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ":root" in response.text
    assert "--paper:" in response.text
    assert ".sidebar" in response.text


def test_herb_pagination_with_many_records(tmp_path):
    client, database = make_client(tmp_path)
    # Seed 35 herbs so we span 3 pages (PAGE_SIZE=12: 12, 12, 11)
    for i in range(1, 36):
        name = f"Tulsi Specimen {i:02d}" if i <= 25 else f"Neem Specimen {i:02d}"
        database.add_herb(name, botanical_name=f"Botanical {i:02d}")

    # 1. Page 1 (/herbs)
    r1 = client.get("/herbs")
    assert r1.status_code == 200
    assert "Showing 1–12 of 35" in r1.text
    assert "page=2" in r1.text
    assert "Page 1 of 3" in r1.text

    # 2. Page 2 (/herbs?page=2)
    r2 = client.get("/herbs?page=2")
    assert r2.status_code == 200
    assert "Showing 13–24 of 35" in r2.text
    assert "page=1" in r2.text
    assert "page=3" in r2.text
    assert "Page 2 of 3" in r2.text

    # 3. Page 3 (/herbs?page=3)
    r3 = client.get("/herbs?page=3")
    assert r3.status_code == 200
    assert "Showing 25–35 of 35" in r3.text
    assert "page=2" in r3.text
    assert "Page 3 of 3" in r3.text

    # 4. Search query spanning multiple pages (/herbs?q=Tulsi)
    # 25 Tulsi herbs span 3 pages: 12, 12, 1
    rq1 = client.get("/herbs?q=Tulsi")
    assert rq1.status_code == 200
    assert "Showing 1–12 of 25" in rq1.text
    assert "q=Tulsi" in rq1.text
    assert "page=2" in rq1.text

    rq2 = client.get("/herbs?q=Tulsi&page=2")
    assert rq2.status_code == 200
    assert "Showing 13–24 of 25" in rq2.text
    assert "q=Tulsi" in rq2.text
    assert "page=1" in rq2.text
    assert "page=3" in rq2.text

    # 5. Out-of-range page clamps safely and returns 200
    r_out = client.get("/herbs?page=999")
    assert r_out.status_code == 200
    assert "Showing 25–35 of 35" in r_out.text
    assert "Page 3 of 3" in r_out.text


def test_illness_explorer_lists_illnesses_with_counts(tmp_path):
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    h2 = database.add_herb("Neem", botanical_name="Azadirachta indica")
    i1 = database.add_illness("Cough")
    i2 = database.add_illness("Fever")
    database.add_treatment(h1, i1)
    database.add_treatment(h2, i1)
    database.add_treatment(h1, i2)

    response = client.get("/illnesses")
    assert response.status_code == 200
    assert "Illness explorer" in response.text
    assert "Cough" in response.text
    assert "Fever" in response.text
    assert "2 herbs" in response.text
    assert "1 herb" in response.text
    assert "Associations are scraped from the CCRAS DRAVYA source, are unverified, and are not medical advice." in response.text


def test_illness_explorer_search_by_name_and_alias(tmp_path):
    client, database = make_client(tmp_path)
    i1 = database.add_illness("Cough")
    i2 = database.add_illness("Jvara")

    # 1. Search by exact name
    r_name = client.get("/illnesses", params={"q": "cough"})
    assert r_name.status_code == 200
    assert "<strong>Cough</strong>" in r_name.text
    assert "<strong>Jvara</strong>" not in r_name.text

    # 2. Search by alias ("fever" -> "jvara")
    r_alias = client.get("/illnesses", params={"q": "fever"})
    assert r_alias.status_code == 200
    assert "<strong>Fever</strong>" in r_alias.text
    assert "<code>Jvara</code>" in r_alias.text
    assert "<strong>Cough</strong>" not in r_alias.text


def test_illness_detail_shows_herbs_and_distinguishes_manual(tmp_path):
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    h2 = database.add_herb("Neem", botanical_name="Azadirachta indica")
    illness_id = database.add_illness("Cough")
    database.add_treatment(h1, illness_id)  # manual treatment link

    # Also add a scraped treatment link to verify link_source distinction
    with database._connection() as conn:
        conn.execute("INSERT INTO treatment (herb_id, illness_id, source) VALUES (?, ?, 'scraped')", (h2, illness_id))

    response = client.get(f"/illnesses/{illness_id}")
    assert response.status_code == 200
    assert "Cough" in response.text
    assert "Tulsi" in response.text
    assert "Neem" in response.text
    assert "Manual" in response.text
    assert "Scraped" in response.text
    assert f"/herbs/{h1}" in response.text
    assert "Associations are scraped from the CCRAS DRAVYA source, are unverified, and are not medical advice." in response.text


def test_missing_illness_returns_404(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/illnesses/9999")
    assert response.status_code == 404
    assert "Illness not found" in response.text


def test_api_illness_endpoints(tmp_path):
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    i1 = database.add_illness("Cough")
    i2 = database.add_illness("Jvara")
    database.add_treatment(h1, i1)

    # 1. GET /api/illnesses
    r_list = client.get("/api/illnesses")
    assert r_list.status_code == 200
    data = r_list.json()
    assert len(data) == 2
    names = [item["english_name"] for item in data]
    assert "Cough" in names
    assert "Jvara" in names
    # Verify P0-4 API multilingual and provenance fields
    jvara_item = next(item for item in data if item["english_name"] == "Jvara")
    assert jvara_item["english"] == "Fever"
    assert "ज्वर" in jvara_item["hindi"]
    assert "ज्वर" in jvara_item["sanskrit"]
    assert jvara_item["origin"] == "machine_generated"
    assert jvara_item["verification"] == "unverified"

    # 2. GET /api/illnesses?q=fever (alias search) & Hindi search ?q=बुखार
    r_search = client.get("/api/illnesses", params={"q": "fever"})
    assert r_search.status_code == 200
    s_data = r_search.json()
    assert len(s_data) == 1
    assert s_data[0]["english_name"] == "Jvara"

    r_search_hi = client.get("/api/illnesses", params={"q": "बुखार", "language": "hi"})
    assert r_search_hi.status_code == 200
    hi_data = r_search_hi.json()
    assert len(hi_data) == 1
    assert hi_data[0]["english_name"] == "Jvara"
    assert "ज्वर" in hi_data[0]["label"]

    # 3. GET /api/illnesses/{id}/herbs
    r_herbs = client.get(f"/api/illnesses/{i1}/herbs", params={"language": "hi"})
    assert r_herbs.status_code == 200
    h_data = r_herbs.json()
    assert len(h_data) == 1
    assert h_data[0]["english_name"] == "Tulsi"
    assert h_data[0]["link_source"] == "manual"
    assert h_data[0]["english"] == "Cough"
    assert "कास" in h_data[0]["hindi"]
    assert h_data[0]["origin"] == "machine_generated"
    assert h_data[0]["verification"] == "unverified"

    # 4. Unknown illness 404
    r_unknown = client.get("/api/illnesses/9999/herbs")
    assert r_unknown.status_code == 404


def test_herb_explorer_devanagari_sanskrit_and_botanical_search(tmp_path):
    client, database = make_client(tmp_path)
    from herbal_almanac.cleaning import PlantRecord
    rec = PlantRecord(
        ayurvedic_name="तुलसी",
        transliterated_name="Tulsi",
        source="ccras_dravya",
        source_record_id=101,
        source_url="https://example.com/plant/101",
        botanical_name="Ocimum tenuiflorum",
        family="Lamiaceae",
        retrieved_at="2025-01-01T12:00:00Z",
    )
    database.insert_record(rec)

    # 1. Search by Devanagari Sanskrit name
    res_deva = client.get("/herbs", params={"q": "तुलसी"})
    assert res_deva.status_code == 200
    assert "तुलसी" in res_deva.text
    assert "Browse illnesses" in res_deva.text

    # 2. Search by transliterated English name
    res_en = client.get("/herbs", params={"q": "Tulsi"})
    assert res_en.status_code == 200
    assert "तुलसी" in res_en.text

    # 3. Search by botanical name
    res_bot = client.get("/herbs", params={"q": "Ocimum"})
    assert res_bot.status_code == 200
    assert "Ocimum tenuiflorum" in res_bot.text


def test_format_readable_illness_unit():
    from herbal_almanac.web_app import format_readable_illness

    assert format_readable_illness("KAsa") == "Kasa"
    assert format_readable_illness("AgnimAndya") == "Agnimandya"
    assert format_readable_illness("khAlityam/khalati") == "Khalityam/Khalati"
    assert format_readable_illness("arditaH") == "Arditah"
    assert format_readable_illness("rAjayakSmA") == "Rajayaksma"
    assert format_readable_illness("KAsa Roga") == "Kasa Roga"
    assert format_readable_illness("Cough") == "Cough"
    assert format_readable_illness("") == ""
    assert format_readable_illness("   ") == ""
    assert format_readable_illness(None) == ""


def test_readable_illness_rendered_in_templates_without_altering_db(tmp_path):
    client, database = make_client(tmp_path)

    herb_id = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    i1 = database.add_illness("KAsa")
    i2 = database.add_illness("AgnimAndya")
    i3 = database.add_illness("SpecialUnmatchedTerm")
    database.add_treatment(herb_id, i1)

    # Stored database names must remain untouched
    with database._connection() as conn:
        row1 = conn.execute("SELECT english_name FROM illness WHERE id = ?", (i1,)).fetchone()
        row2 = conn.execute("SELECT english_name FROM illness WHERE id = ?", (i2,)).fetchone()
        assert row1[0] == "KAsa"
        assert row2[0] == "AgnimAndya"

    # Template list view renders English name as main heading + original term in small text
    r_list = client.get("/illnesses")
    assert r_list.status_code == 200
    assert "<strong>Cough</strong>" in r_list.text
    assert "<strong>Weak digestive fire</strong>" in r_list.text
    assert "Original term · <code>KAsa</code>" in r_list.text
    assert "Specialunmatchedterm" in r_list.text
    assert "(translation not available)" in r_list.text

    # Detail view renders English heading and back-link
    r_detail = client.get(f"/illnesses/{i1}")
    assert r_detail.status_code == 200
    assert "<h1>Cough</h1>" in r_detail.text
    assert "<title>Cough · Illness Explorer · Herbal Almanac</title>" in r_detail.text
    assert "Original term · <code>KAsa</code>" in r_detail.text

    # Herb detail renders English primary condition link
    r_herb = client.get(f"/herbs/{herb_id}")
    assert r_herb.status_code == 200
    assert "Cough" in r_herb.text
    assert "· KAsa" in r_herb.text

    # DB records remain unchanged after template rendering
    with database._connection() as conn:
        assert conn.execute("SELECT english_name FROM illness WHERE id = ?", (i1,)).fetchone()[0] == "KAsa"


def test_illness_multilingual_language_selector_and_disclaimer(tmp_path):
    client, database = make_client(tmp_path)
    i1 = database.add_illness("KAsa")

    # 1. English (default) has no machine translation notice
    r_en = client.get("/illnesses")
    assert r_en.status_code == 200
    assert "Translations are machine-generated (Gemini) and not clinically verified." not in r_en.text
    assert "<strong>Cough</strong>" in r_en.text

    # 2. Hindi language parameter
    r_hi = client.get("/illnesses", params={"language": "hi"})
    assert r_hi.status_code == 200
    assert "Translations are machine-generated (Gemini) and not clinically verified." in r_hi.text
    assert "कास (खांसी)" in r_hi.text
    assert 'lang="hi"' in r_hi.text

    # 3. Tamil language parameter on detail page
    r_ta = client.get(f"/illnesses/{i1}", params={"language": "ta"})
    assert r_ta.status_code == 200
    assert "Translations are machine-generated (Gemini) and not clinically verified." in r_ta.text
    assert "இருமல்" in r_ta.text
    assert 'lang="ta"' in r_ta.text

    # 4. Unknown language parameter falls back to 'en' cleanly without error
    r_fallback = client.get("/illnesses", params={"language": "unknown_code"})
    assert r_fallback.status_code == 200
    assert "Translations are machine-generated (Gemini) and not clinically verified." not in r_fallback.text
    assert "<strong>Cough</strong>" in r_fallback.text


def test_global_search_box_routes_illness_query_to_illnesses(tmp_path):
    client, database = make_client(tmp_path)
    database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    database.add_illness("KAsa")

    # 1. Searching a herb name stays on /herbs
    r_herb = client.get("/herbs", params={"q": "Tulsi"}, follow_redirects=False)
    assert r_herb.status_code == 200
    assert "Tulsi" in r_herb.text

    # 2. Searching an illness term on /herbs (0 herb matches) redirects to /illnesses
    r_illness = client.get("/herbs", params={"q": "cough"}, follow_redirects=False)
    assert r_illness.status_code == 303
    assert "/illnesses?q=cough" in r_illness.headers["location"]

    # Following redirect yields illness explorer results
    r_followed = client.get("/herbs", params={"q": "cough"}, follow_redirects=True)
    assert r_followed.status_code == 200
    assert "Illness explorer" in r_followed.text
    assert "Cough" in r_followed.text


def test_guide_renders_with_and_without_database(tmp_path):
    # 1. With existing seeded database
    client, database = make_client(tmp_path)
    database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    res_seeded = client.get("/guide")
    assert res_seeded.status_code == 200
    assert "User Guide" in res_seeded.text
    assert "Ayurvedic Concepts" in res_seeded.text

    # 2. Without database (missing file)
    missing_path = tmp_path / "nonexistent" / "absent.db"
    client_no_db = TestClient(create_app(missing_path))
    res_no_db = client_no_db.get("/guide")
    assert res_no_db.status_code == 200
    assert "What is this site?" in res_no_db.text


def test_guide_contains_all_glossary_terms_and_anchors(tmp_path):
    client, _ = make_client(tmp_path)
    res = client.get("/guide")
    assert res.status_code == 200
    body = res.text

    # Verify required anchor IDs
    required_anchors = ["what-is-this", "how-to-use", "glossary", "data-sources", "limits"]
    for anchor in required_anchors:
        assert f'id="{anchor}"' in body, f"Anchor id='{anchor}' missing from /guide"

    # Verify TOC links point to existing anchors
    for anchor in required_anchors:
        assert f'href="#{anchor}"' in body, f"TOC link href='#{anchor}' missing from /guide"

    # Verify required glossary terms
    required_terms = [
        "Ayurveda",
        "Dravya",
        "Dravyaguna",
        "Rasa",
        "Guna",
        "Virya",
        "Vipaka",
        "Prabhava",
        "Dosha",
        "dosha effects",
        "Karma",
        "Part used",
        "Preparation",
        "Indication",
        "Vernacular name",
        "Concept",
        "Claim",
        "Source",
        "provenance",
        "Reconciliation",
        "Unreviewed",
        "unverified",
        "machine-generated",
        "Original term",
    ]
    for term in required_terms:
        assert term.lower() in body.lower(), f"Glossary term '{term}' missing from /guide"

    # Verify 15 supported languages rendered with native scripts
    assert "हिन्दी" in body
    assert "संस्कृतम्" in body
    assert "தமிழ்" in body
    assert "اردو" in body
    assert "বাংলা" in body


def test_guide_navigation_and_cross_links(tmp_path):
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    i1 = database.add_illness("KAsa")
    database.add_treatment(h1, i1)
    database.upgrade_to_stage_c()
    database.run_stage_c_backfill()

    # 1. Nav active state on /guide
    res_guide = client.get("/guide")
    assert res_guide.status_code == 200
    assert 'class="active"' in res_guide.text
    assert "/guide" in res_guide.text
    assert "Guide &amp; About" in res_guide.text

    # 2. Dashboard contains link to guide
    res_dash = client.get("/")
    assert res_dash.status_code == 200
    assert "/guide" in res_dash.text
    assert "New here? Read the guide" in res_dash.text

    # 3. Virya reconciliation links to guide glossary
    res_recon = client.get(f"/stage-c/reconciliation/{h1}")
    assert res_recon.status_code == 200
    assert '/guide#glossary' in res_recon.text

    # 4. Herb detail semantic links to guide glossary
    res_herb = client.get(f"/herbs/{h1}")
    assert res_herb.status_code == 200
    assert '/guide#glossary' in res_herb.text

    # 5. Illness explorer and illness detail link to guide limits
    res_illnesses = client.get("/illnesses")
    assert res_illnesses.status_code == 200
    assert '/guide#limits' in res_illnesses.text

    res_ill_detail = client.get(f"/illnesses/{i1}")
    assert res_ill_detail.status_code == 200
    assert '/guide#limits' in res_ill_detail.text


def test_guide_internal_links_resolve_with_seeded_db(tmp_path):
    import re
    from urllib.parse import urlparse

    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    i1 = database.add_illness("KAsa")
    database.add_treatment(h1, i1)
    database.upgrade_to_stage_c()
    database.run_stage_c_backfill()

    res = client.get("/guide")
    assert res.status_code == 200

    # Extract all hrefs
    hrefs = re.findall(r'href="([^"]+)"', res.text)
    checked_paths = set()

    for href in hrefs:
        if href.startswith("#"):
            continue
        parsed = urlparse(href)
        path = parsed.path
        if not path or path.startswith("http") or path.startswith("//"):
            continue
        if path in checked_paths:
            continue
        checked_paths.add(path)

        target_res = client.get(path)
        assert target_res.status_code == 200, f"Internal link '{path}' in /guide returned status {target_res.status_code}"

    assert "/herbs" in checked_paths
    assert "/illnesses" in checked_paths








def test_herb_detail_presentation_restructure_and_deduplication(tmp_path):
    """Verifies P0-3/P1 herb detail presentation layer requirements on Stage C:
    - Unique property chips in single 6-column matrix (Tikta appears once in table with xN count)
    - Exactly 6 column headers in fixed classical order
    - 3-row Dosha table with Vata, Pitta, Kapha always present
    - No repeated 'Source:' echo
    - 'Laghu/ Aguru' resolves solely to Light
    - Botanical family deduped and retrieval date formatted
    - Attribute groups render cleanly including unknown fallback groups
    """
    import re
    from herbal_almanac.cleaning import PlantRecord

    client, database = make_client(tmp_path)
    database.upgrade_to_stage_c()

    record = PlantRecord(
        source="CCRAS_DRAVYA",
        source_record_id=101,
        source_url="https://example.org/vasa",
        retrieved_at="2026-11-19T14:30:00Z",
        ayurvedic_name="Vāsā",
        botanical_name="Adhatoda vasica Nees",
        family="Acanthaceae, Acanthaceae",
        dosha_expressions=["Kapha-pitta shamana"],
        attributes={
            # Rasa triple variant
            "Rasa.Name": ["Tikta, Kashaya"],
            "Rasa.Rasa (Diacritical)": ["Tikta, Kaṣāya"],
            "Rasa.रस (हिन्दी)": ["तिक्त, कषाय"],
            # Guna with privative aguru
            "Guna.Name": ["Laghu/ Aguru, Ruksha"],
            "Guna.Guna (Diacritical)": ["Laghu/ Aguru, Rūkṣa"],
            "Guna.गुण (हिन्दी)": ["लघु/ अगुरु, रूक्ष"],
            # Virya
            "Virya.Name": ["Sheeta"],
            "Virya.Virya (Diacritical)": ["Śīta"],
            "Virya.वीर्य (हिन्दी)": ["शीत"],
            # Vernacular names
            "Vernacular Names.Hindi": ["अड़ूसा"],
            "Vernacular Names.English": ["Malabar Nut"],
            # Parts used
            "Parts Used.Name": ["Leaf"],
            "Parts Used.Parts Used (Diacritical)": ["Patra"],
            "Parts Used.प्रयोज्याङ्ग (हिन्दी)": ["पत्र"],
            # Dosage formulation
            "Dosage Formulation.Name": ["Vasa Avaleha"],
            "Dosage Formulation.Dosage(Form)": ["Avaleha"],
            "Dosage Formulation.Dosage(Reference)": ["AFI Part I"],
            # Dose
            "Dose.Dose": ["10-20 ml juice"],
            # Unknown group fallback
            "CustomVoucher.SpecimenID": ["HERB-VAS-2026"],
        },
    )
    herb_id = database.insert_record(record)
    database.run_stage_c_backfill()

    res = client.get(f"/herbs/{herb_id}")
    assert res.status_code == 200
    html = res.text

    # 1. Family deduped: "Acanthaceae" present, "Acanthaceae, Acanthaceae" not in identity grid
    assert "<dd>Acanthaceae</dd>" in html
    assert "Acanthaceae, Acanthaceae" not in html

    # 2. Retrieved date formatted
    assert "<dd>19 Nov 2026</dd>" in html

    # 3. Exactly 6 column headers in fixed order
    headers = re.findall(r'<table class="props-table">.*?<thead>.*?<tr>(.*?)</tr>.*?</thead>', html, re.DOTALL)
    assert len(headers) == 1
    th_matches = re.findall(r'<th>(.*?)</th>', headers[0])
    assert len(th_matches) == 6
    assert "Rasa" in th_matches[0]
    assert "Guna" in th_matches[1]
    assert "Virya" in th_matches[2]
    assert "Vipaka" in th_matches[3]
    assert "Prabhava" in th_matches[4]
    assert "Karma" in th_matches[5]

    # 4. Single body row in props table
    tbody_rows = re.findall(r'<table class="props-table">.*?<tbody>(.*?)</tbody>', html, re.DOTALL)
    assert len(tbody_rows) == 1
    body_tr_matches = re.findall(r'<tr>(.*?)</tr>', tbody_rows[0], re.DOTALL)
    assert len(body_tr_matches) == 1

    # 5. Tikta appears as unique chip (claim count badge xN)
    assert "Bitter" in tbody_rows[0]
    assert "×3" in tbody_rows[0] or "×2" in tbody_rows[0]

    # 6. "Laghu/ Aguru" displays only Light, never Heavy
    assert "Light" in tbody_rows[0]
    assert "Heavy" not in tbody_rows[0]

    # 7. 3-row Dosha table with Vata, Pitta, Kapha always present
    dosha_tbody = re.findall(r'<table class="dosha-table">.*?<tbody>(.*?)</tbody>', html, re.DOTALL)
    assert len(dosha_tbody) == 1
    dosha_rows = re.findall(r'<tr>(.*?)</tr>', dosha_tbody[0], re.DOTALL)
    assert len(dosha_rows) == 3
    assert "Vata" in dosha_rows[0]
    assert "Pitta" in dosha_rows[1]
    assert "Kapha" in dosha_rows[2]
    # Vata should be Not recorded since Kapha-pitta shamana was specified
    assert "Not recorded" in dosha_rows[0]
    assert "Pacifies / Decreases" in dosha_rows[1]
    assert "Pacifies / Decreases" in dosha_rows[2]

    # 8. No repeated "Source:" echo
    assert "Source: Leaf" not in html

    # 9. Every attribute group renders cleanly
    assert "Vernacular & Regional Names" in html
    assert "अड़ूसा" in html
    assert "Malabar Nut" in html
    assert "Parts Used (Prayojyāṅga)" in html
    assert "Patra" in html
    assert "पत्र" in html
    assert "Preparations & Dosage Forms" in html
    assert "Vasa Avaleha" in html
    assert "10-20 ml juice" in html
    assert "CustomVoucher" in html
    assert "HERB-VAS-2026" in html


def test_herb_detail_schema_v2_renders_cleanly(tmp_path):
    """Verifies that a Schema Version 2 database renders cleanly with 3-row doshas and banner."""
    client, database = make_client(tmp_path)
    h_id = database.add_herb(
        "Tulsi",
        botanical_name="Ocimum tenuiflorum",
        family="Lamiaceae, Lamiaceae",
    )
    # Add legacy dosha
    with database._connection() as conn:
        conn.execute("INSERT INTO herb_doshas (herb_id, dosha, effect, source_expression) VALUES (?, 'Kapha', 'decrease', 'Kaphahara')", (h_id,))

    res = client.get(f"/herbs/{h_id}")
    assert res.status_code == 200
    # Capability banner
    assert "STAGE C CAPABILITY STATUS" in res.text
    # Family deduped
    assert "<dd>Lamiaceae</dd>" in res.text
    # 3-row dosha table present
    assert "Vata" in res.text
    assert "Pitta" in res.text
    assert "Kapha" in res.text
    assert "Not recorded" in res.text


def test_herb_search_vernacular_devanagari(tmp_path):
    """Verifies search_herbs and GET /herbs query matching vernacular/Devanagari names."""
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    h2 = database.add_herb("Neem", botanical_name="Azadirachta indica")

    # Add vernacular attribute for Tulsi
    with database._connection() as conn:
        conn.execute(
            "INSERT INTO herb_attributes (herb_id, field_name, value, source_text) VALUES (?, 'Vernacular Names.Hindi', 'तुलसी', 'CCRAS')",
            (h1,),
        )

    # 1. Search in Python
    matches = database.search_herbs("तुलसी")
    assert len(matches) > 0
    assert matches[0]["id"] == h1

    # 2. Search in Web GUI
    import urllib.parse
    resp = client.get(f"/herbs?q={urllib.parse.quote('तुलसी')}")
    assert resp.status_code == 200
    assert "Tulsi" in resp.text
    assert "Neem" not in resp.text


def test_guide_renders_dynamic_examples_from_db(tmp_path):
    """Verifies /guide renders dynamic examples for herbs and conditions."""
    client, database = make_client(tmp_path)
    h1 = database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    h2 = database.add_herb("Vasa", botanical_name="Adhatoda vasica")
    i1 = database.add_illness("KAsa")
    database.add_treatment(h1, i1)
    database.add_treatment(h2, i1)

    res = client.get("/guide")
    assert res.status_code == 200
    assert f"/herbs/{h1}" in res.text
    assert f"/illnesses/{i1}" in res.text
    assert "Tulsi" in res.text or "Vasa" in res.text
