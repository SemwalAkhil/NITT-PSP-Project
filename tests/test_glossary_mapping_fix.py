from __future__ import annotations

import csv
from pathlib import Path

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.herb_glossary import (
    HerbGlossaryStore,
    get_herb_glossary_store,
    normalize_binomial,
)
from herbal_almanac.herb_view import herb_image_url, herb_name, herb_vernacular_table


def test_shipped_herb_names_csv_integrity() -> None:
    """Shipped herb_names.csv has 347 rows, unique ccras_id ints, and every row resolves back."""
    csv_path = Path(__file__).resolve().parent.parent / "src" / "herbal_almanac" / "data" / "herb_names.csv"
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 347
    ccras_ids = [int(r["ccras_id"]) for r in rows]
    assert len(set(ccras_ids)) == 347

    get_herb_glossary_store.cache_clear()
    store = get_herb_glossary_store()
    assert len(store.all_herbs) == 347
    assert len(store.by_ccras_id) == 347

    # Spot-check canonical ccras_ids
    assert store.by_ccras_id[1].botanical_name == "Abies webbiana"
    assert store.by_ccras_id[231].botanical_name == "Mangifera indica"
    assert store.by_ccras_id[266].botanical_name == "Paspalum scrobiculatum"

    # Every row's binomial resolves back to itself (or duplicate binomial with same original_name)
    for r in rows:
        row_id = int(r["id"])
        resolved = store.resolve_herb(
            {
                "source": "manual",
                "botanical_name": r["botanical_name"],
                "original_name": r["original_name"],
            }
        )
        assert resolved is not None, f"Row {row_id} ({r['botanical_name']}) failed to resolve"
        if resolved.id != row_id:
            # Must be one of the documented duplicate-binomial rows
            assert normalize_binomial(resolved.botanical_name) == normalize_binomial(r["botanical_name"])
            assert resolved.original_name == r["original_name"]


def test_glossary_toleration_without_ccras_id_column() -> None:
    """Loader tolerates legacy CSV rows that omit the ccras_id column."""
    store = HerbGlossaryStore(
        [
            {
                "id": "1",
                "original_name": "Āmra",
                "botanical_name": "Mangifera indica",
                "English": "Mango",
                "Hindi": "आम",
            }
        ]
    )
    assert len(store.all_herbs) == 1
    assert store.by_ccras_id == {}
    res = store.resolve_herb({"source": "manual", "botanical_name": "Mangifera indica"})
    assert res is not None
    assert res.get_name("hi") == "आम"


def test_amra_mango_and_kodrava_kodo_millet_mapping(tmp_path: Path) -> None:
    """CCRAS Amra (source_record_id=231) gets Mango names; Kodrava (266) gets Kodo Millet; Talisha (1) gets Silver Fir."""
    db = AyurvedicAlmanac(tmp_path / "test.db")
    amra_id = db.add_herb(
        english_name="Amra",
        botanical_name="Mangifera indica",
        source="CCRAS DRAVYA",
        source_record_id=231,
    )
    kodrava_id = db.add_herb(
        english_name="Kodrava",
        botanical_name="Paspalum scrobiculatum",
        source="CCRAS DRAVYA",
        source_record_id=266,
    )
    talisha_id = db.add_herb(
        english_name="Talisha",
        botanical_name="Abies webbiana",
        source="CCRAS DRAVYA",
        source_record_id=1,
    )

    amra = db.get_herb(amra_id)
    kodrava = db.get_herb(kodrava_id)
    talisha = db.get_herb(talisha_id)

    # Amra -> Mango (NOT Kodo Millet!)
    assert herb_name(amra, "en") == "Mango"
    assert herb_name(amra, "hi") == "आम"
    assert herb_name(amra, "ta") == "மா"
    assert herb_image_url(amra) == "https://dravya.ccras.org.in/resources/views/admin/required/upload/231.jpg"
    amra_langs = {r["language"]: r["name"] for r in herb_vernacular_table(amra)}
    assert amra_langs["Hindi"] == "आम"
    assert amra_langs["Tamil"] == "மா"

    # Kodrava -> Kodo Millet
    assert herb_name(kodrava, "en") == "Kodo Millet"
    assert herb_name(kodrava, "hi") == "कोदो"
    assert herb_image_url(kodrava) == "https://dravya.ccras.org.in/resources/views/admin/required/upload/266.jpg"

    # Talisha -> Himalayan Silver Fir
    assert herb_name(talisha, "en") == "Himalayan Silver Fir"
    assert herb_name(talisha, "hi") == "तालीसपत्र"
    assert herb_image_url(talisha) == "https://dravya.ccras.org.in/resources/views/admin/required/upload/1.jpg"

    # Multilingual search isolation
    mango_hits_hi = db.search_herbs("आम")
    assert [h["id"] for h in mango_hits_hi] == [amra_id]
    mango_hits_en = db.search_herbs("Mango")
    assert [h["id"] for h in mango_hits_en] == [amra_id]
    kodo_hits = db.search_herbs("कोदो")
    assert [h["id"] for h in kodo_hits] == [kodrava_id]


def test_manual_herb_source_record_id_ignored_but_botanical_matches(tmp_path: Path) -> None:
    """Manual herb with source_record_id=1 gets nothing by ID, but resolves by botanical name."""
    db = AyurvedicAlmanac(tmp_path / "manual.db")
    no_bot_id = db.add_herb(
        english_name="Unknown Manual Plant",
        source="https://mytestwebsite.com/",
        source_record_id=1,
    )
    mango_manual_id = db.add_herb(
        english_name="Garden Mango",
        botanical_name="Mangifera indica",
        source="https://mytestwebsite.com/",
        source_record_id=2,
    )
    variant_id = db.add_herb(
        english_name="Kampilla Variant",
        botanical_name="Mallotus philippinensis Muell",
        source="manual",
    )

    store = get_herb_glossary_store()
    assert store.resolve_herb(db.get_herb(no_bot_id)) is None
    assert herb_name(db.get_herb(no_bot_id), "hi") is None

    mango_manual = db.get_herb(mango_manual_id)
    assert herb_name(mango_manual, "en") == "Mango"
    assert herb_name(mango_manual, "hi") == "आम"
    assert herb_image_url(mango_manual) is None

    variant = db.get_herb(variant_id)
    assert herb_name(variant, "en") == "Kamala Tree"
    assert herb_name(variant, "hi") == "कमीला"
