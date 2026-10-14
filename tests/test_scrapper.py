from __future__ import annotations

from bs4 import BeautifulSoup

from cleaning import PlantRecord, ascii_text
from database_operator import AyurvedicAlmanac
from scrapper import _table_attributes, _vernacular_attributes, parse_plant
from translation import enrich_record


def test_table_attributes_use_section_headers() -> None:
    html = """
    <html><body>
    <div class="accordion-button">1. Parts Used</div>
    <table>
      <tr><th>1.1 Name</th><th>1.2 उपयोगी हिस्सा(हिन्दी)</th><th>1.3 Part Used(Diacritical)</th></tr>
      <tr><td>leaf</td><td>पत्ता</td><td>Patra</td></tr>
      <tr><td>root</td><td>जड़</td><td>Mūla</td></tr>
    </table>

    <div class="accordion-button">2. Therapeutic Usage</div>
    <table>
      <tr><th>2.1 Name</th></tr>
      <tr><td>Kāsa</td></tr>
      <tr><td>Agnimāndya</td></tr>
    </table>
    </body></html>
    """

    attributes, _ = _table_attributes(BeautifulSoup(html, "html.parser"))

    assert attributes["Parts Used.Name"] == ["leaf", "root"]
    assert attributes["Parts Used.उपयोगी हिस्सा(हिन्दी)"] == ["पत्ता", "जड़"]
    assert attributes["Therapeutic Usage.Name"] == ["Kāsa", "Agnimāndya"]


def test_vernacular_names_are_language_attributes_and_primary_name(tmp_path) -> None:
    html = """
    <div class="card">
        <div class="card-header"><h5>Vernacular Names</h5></div>
        <div class="card-body">
            <div class="col"><span class="badge">English</span><p>Himalayan silver</p></div>
            <div class="col"><span class="badge">Malyalam</span><p>Taleesapatri</p></div>
        </div>
    </div>
    """

    soup = BeautifulSoup(html, "html.parser")
    attributes, _ = _vernacular_attributes(soup)
    record = parse_plant(1, "https://example.test/plant/1", html)

    assert attributes["Vernacular Names.English"] == ["Himalayan silver"]
    assert attributes["Vernacular Names.Malayalam"] == ["Taleesapatri"]
    assert record.ayurvedic_name == "Himalayan silver"
    database = AyurvedicAlmanac(tmp_path / "ayurvedic.db")
    herb_id = database.insert_record(record)

    stored_attributes = database.herb_attributes(herb_id)
    stored_fields = {(row["field_name"], row["value"]) for row in stored_attributes}

    assert ("Vernacular Names.English", "Himalayan silver") in stored_fields
    assert ("Vernacular Names.Malayalam", "Taleesapatri") in stored_fields
    assert database.search_herbs("Himalayan silver")[0]["id"] == herb_id


def test_insert_record_refreshes_treatment_links(tmp_path) -> None:
    db_path = tmp_path / "ayurvedic.db"
    database = AyurvedicAlmanac(db_path)

    first_record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=1,
        source_url="https://example.test/plant/1",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Test Herb",
        attributes={"Therapeutic Usage.Name": ["Kāsa", "Agnimāndya"]},
        source_values={"Therapeutic Usage.Name": "Kāsa | Agnimāndya"},
    ).clean()
    second_record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=1,
        source_url="https://example.test/plant/1",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Test Herb",
        attributes={"Therapeutic Usage.Name": ["Kāsa"]},
        source_values={"Therapeutic Usage.Name": "Kāsa"},
    ).clean()

    database.insert_record(first_record)
    database.insert_record(second_record)

    herb_id = database.connect().execute(
        "SELECT id FROM herbs WHERE source = ? AND source_record_id = ?",
        ("CCRAS DRAVYA", 1),
    ).fetchone()["id"]

    illnesses = database.connect().execute(
        "SELECT i.english_name FROM treatment AS t JOIN illness AS i ON i.id = t.illness_id WHERE t.herb_id = ? ORDER BY i.english_name",
        (herb_id,),
    ).fetchall()

    assert [row["english_name"] for row in illnesses] == ["Kasa"]


def test_english_cleanup_removes_symbols_and_diacritics() -> None:
    assert ascii_text("📚 Etymology") == "Etymology"
    assert ascii_text("Kāsa") == "Kasa"

    record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=1,
        source_url="https://example.test/plant/1",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Kāsa",
        attributes={"Therapeutic Usage.Name": ["Kāsa"], "Vernacular Names.Hindi": ["कास"]},
    ).clean()

    assert record.ayurvedic_name == "Kasa"
    assert record.attributes["Therapeutic Usage.Name"] == ["Kasa"]
    assert record.attributes["Vernacular Names.Hindi"] == ["कास"]

    record.source_values["Translated Names.Hindi"] = "कास"
    record.clean()
    assert record.source_values["Translated Names.Hindi"] == "कास"


def test_translation_enrichment_adds_english_and_regional_attributes() -> None:
    class FakeTranslator:
        def translate(self, text: str, target: str) -> str:
            if target == "en":
                return "Cough"
            return f"{target}:{text}"

    record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=1,
        source_url="https://example.test/plant/1",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Kasa",
        attributes={"Vernacular Names.Hindi": ["कास"]},
    ).clean()

    enrich_record(record, FakeTranslator())

    assert record.attributes["Translated Names.Hindi"] == ["hi:Kasa"]
    assert record.attributes["Translated Names.English"] == ["Kasa", "Cough"]
