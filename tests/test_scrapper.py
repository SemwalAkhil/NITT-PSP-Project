from __future__ import annotations

import json

from bs4 import BeautifulSoup
import requests
import pytest

from cleaning import PlantRecord, ascii_text
from database_operator import AyurvedicAlmanac
import scrapper
from scrapper import (
    DiscoveryError,
    _discover_plants,
    _table_attributes,
    _vernacular_attributes,
    parse_plant,
)
from translation import enrich_record
from translation import GoogleNameTranslator, TranslationResult


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


def test_table_section_can_be_declared_on_table_and_malformed_tables_are_safe() -> None:
    html = """
    <table data-section="Parts Used">
      <tr><th>Name</th></tr><tr><td>leaf</td></tr>
    </table>
    <table><tr><td>missing header</td></tr></table>
    """
    attributes, _ = _table_attributes(BeautifulSoup(html, "html.parser"))
    assert attributes == {"Parts Used.Name": ["leaf"]}


def test_discovery_rejects_unbounded_pagination() -> None:
    class FakeSession:
        pass

    pages = {
        1: '<a href="/plant/1">one</a>',
        2: '<a href="/plant/1">one</a>',
        3: '<a href="/plant/1">one</a>',
    }

    def fake_fetch(session, url):
        page = int(url.rsplit("=", 1)[1])
        return pages[page]

    import scrapper
    original_fetch = scrapper.fetch
    scrapper.fetch = fake_fetch
    try:
        report = _discover_plants(FakeSession(), "https://example.test/all", max_pages=3)
    finally:
        scrapper.fetch = original_fetch

    assert report.total_discovered == 1
    assert report.pages == 3
    assert "no IDs" in report.termination


def test_fetch_surfaces_timeout_and_http_errors() -> None:
    class FakeResponse:
        text = "ignored"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("503 unavailable")

    class FakeSession:
        def get(self, url, timeout):
            return FakeResponse()

    with pytest.raises(requests.HTTPError, match="503"):
        scrapper.fetch(FakeSession(), "https://example.test", 1)

    class TimeoutSession:
        def get(self, url, timeout):
            raise requests.Timeout("request timed out")

    with pytest.raises(requests.Timeout, match="timed out"):
        scrapper.fetch(TimeoutSession(), "https://example.test", 1)


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


def test_retrieval_timestamp_and_fuzzy_search_are_persisted(tmp_path) -> None:
    record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=12,
        source_url="https://example.test/plant/12",
        retrieved_at="2026-10-14T19:00:00+00:00",
        ayurvedic_name="Tulsi",
    ).clean()
    database = AyurvedicAlmanac(tmp_path / "ayurvedic.db")
    herb_id = database.insert_record(record)

    herb = database.connect().execute(
        "SELECT retrieved_at FROM herbs WHERE id = ?", (herb_id,)
    ).fetchone()
    assert herb["retrieved_at"] == record.retrieved_at
    assert database.search_herbs("Tulsii")[0]["english_name"] == "Tulsi"


def test_ambiguous_therapeutic_values_are_not_treatments(tmp_path) -> None:
    record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=8,
        source_url="https://example.test/plant/8",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Test Herb",
        attributes={
            "Therapeutic Usage.Name": ["Kāsa", "Cooling property", "Kapha"],
        },
    ).clean()

    database = AyurvedicAlmanac(tmp_path / "ayurvedic.db")
    herb_id = database.insert_record(record)

    illnesses = database.treatment_details(herb_id)
    assert [row["english_name"] for row in illnesses] == ["Kasa"]
    stored_values = {
        row["value"] for row in database.herb_attributes(herb_id)
        if row["field_name"] == "Therapeutic Usage.Name"
    }
    assert stored_values == {"Kāsa", "Cooling property", "Kapha"}


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

    assert record.ayurvedic_name == "Kāsa"
    assert record.transliterated_name == "Kasa"
    assert record.attributes["Therapeutic Usage.Name"] == ["Kāsa"]
    assert record.attributes["Vernacular Names.Hindi"] == ["कास"]

    record.source_values["Translated Names.Hindi"] = "कास"
    record.clean()
    assert record.source_values["Translated Names.Hindi"] == "कास"


def test_non_latin_name_is_preserved_alongside_transliteration(tmp_path) -> None:
    record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=7,
        source_url="https://example.test/plant/7",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="कासा",
        attributes={"Therapeutic Usage.Name": ["श्वास"]},
    ).clean()

    assert record.ayurvedic_name == "कासा"
    assert record.transliterated_name == ""
    assert record.attributes["Therapeutic Usage.Name"] == ["श्वास"]

    database = AyurvedicAlmanac(tmp_path / "ayurvedic.db")
    herb_id = database.insert_record(record)
    herb = database.connect().execute(
        "SELECT english_name, original_name FROM herbs WHERE id = ?",
        (herb_id,),
    ).fetchone()

    assert herb["english_name"] == "कासा"
    assert herb["original_name"] == "कासा"


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


def test_translation_cache_persists_status_and_failure(tmp_path, monkeypatch) -> None:
    calls = 0

    def fail_translate(self, text: str) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("translator unavailable")

    monkeypatch.setattr("translation.GoogleTranslator.translate", fail_translate)
    cache_path = tmp_path / "translations.db"
    first = GoogleNameTranslator(minimum_interval=0, cache_path=cache_path)
    result = first.translate("Kasa", "hi")
    second = GoogleNameTranslator(minimum_interval=0, cache_path=cache_path)

    assert result.status == "failed"
    assert result.error == "translator unavailable"
    assert second.translate("Kasa", "hi") == result
    assert calls == 1


def test_machine_translations_are_marked_unverified(tmp_path) -> None:
    class FakeTranslator:
        def translate(self, text: str, target: str) -> TranslationResult:
            return TranslationResult(f"{target}:{text}", "success", None, "auto")

    record = PlantRecord(
        source="CCRAS DRAVYA",
        source_record_id=9,
        source_url="https://example.test/plant/9",
        retrieved_at="2026-01-01T00:00:00+00:00",
        ayurvedic_name="Kasa",
    ).clean()
    enrich_record(record, FakeTranslator())

    assert record.attribute_metadata["Translated Names.Hindi"] == {
        "source_language": "auto",
        "machine_generated": True,
        "verification_status": "unverified",
    }


def test_scrape_retries_failed_plants_and_writes_failure_report(tmp_path, monkeypatch) -> None:
    html = "<html><h1>Reliable Herb</h1></html>"
    monkeypatch.setattr(
        scrapper,
        "discover_plants",
        lambda session, max_pages=None: [
            (1, "https://example.test/plant/1"),
            (2, "https://example.test/plant/2"),
        ],
    )
    monkeypatch.setattr(
        scrapper,
        "fetch",
        lambda session, url, timeout: (
            (_ for _ in ()).throw(requests.RequestException("temporary outage"))
            if url.endswith("/2")
            else html
        ),
    )
    monkeypatch.setattr(scrapper, "enrich_record", lambda record, translator: record)

    report_path = tmp_path / "failures.json"
    report = scrapper.scrape(
        database_path=tmp_path / "ayurvedic.db",
        record_retries=1,
        failure_report_path=report_path,
    )

    assert report.processed == 1
    assert report.failures[0].plant_id == 2
    assert report.failures[0].url.endswith("/2")
    assert report.failures[0].attempts == 2
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["processed"] == 1
    assert saved["failed"] == 1
