"""Hermetic unit tests for the multilingual illness glossary and resolution engine."""

import csv
import importlib.resources as pkg_resources

import pytest

from herbal_almanac.illness_glossary import (
    ORDERED_LANGUAGE_CODES,
    SUPPORTED_LANGUAGES,
    get_catalog_csv_conflicts,
    get_glossary_store,
    resolve_illness,
    search_glossary,
    tolerant_illness_key,
)


EXPECTED_HEADERS = [
    "Original_Term", "English", "Assamese", "Bengali", "Gujarati", "Hindi",
    "Kannada", "Malayalam", "Marathi", "Nepali", "Odia", "Punjabi",
    "Sanskrit", "Tamil", "Telugu", "Urdu",
]

LANG_SCRIPT_RANGES = {
    "Hindi": (0x0900, 0x097F),       # Devanagari
    "Sanskrit": (0x0900, 0x097F),    # Devanagari
    "Marathi": (0x0900, 0x097F),     # Devanagari
    "Nepali": (0x0900, 0x097F),      # Devanagari
    "Assamese": (0x0980, 0x09FF),    # Bengali/Assamese
    "Bengali": (0x0980, 0x09FF),     # Bengali
    "Gujarati": (0x0A80, 0x0AFF),    # Gujarati
    "Punjabi": (0x0A00, 0x0A7F),     # Gurmukhi
    "Odia": (0x0B00, 0x0B7F),        # Odia
    "Tamil": (0x0B80, 0x0BFF),       # Tamil
    "Telugu": (0x0C00, 0x0C7F),      # Telugu
    "Kannada": (0x0C80, 0x0CFF),     # Kannada
    "Malayalam": (0x0D00, 0x0D7F),   # Malayalam
    "Urdu": (0x0600, 0x06FF),        # Arabic
}


def test_csv_integrity():
    """Verifies that illness_glossary.csv satisfies all structural and phonetic invariants."""
    data_res = pkg_resources.files("herbal_almanac").joinpath("data", "illness_glossary.csv")
    with data_res.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == EXPECTED_HEADERS, f"Header mismatch: {reader.fieldnames}"
        rows = list(reader)

    # 1. 227 rows
    assert len(rows) == 227, f"Expected 227 rows, found {len(rows)}"

    # 2. No empty cells
    for row_idx, r in enumerate(rows, 1):
        for col in EXPECTED_HEADERS:
            val = r.get(col, "")
            assert val and val.strip(), f"Empty cell found at row {row_idx}, column '{col}'"

    # 3. Unique normalized keys across rows
    keys = [r["Original_Term"].strip().lower() for r in rows]
    assert len(keys) == len(set(keys)), "Duplicate Original_Term keys found in CSV"

    # 4. Each language column contains characters from its expected Unicode script block
    for lang, (start, end) in LANG_SCRIPT_RANGES.items():
        for row_idx, r in enumerate(rows, 1):
            val = r[lang]
            has_script = any(start <= ord(c) <= end for c in val)
            assert has_script, f"Row {row_idx} column '{lang}' lacks characters in range U+{start:04X}-U+{end:04X}: '{val}'"


def test_resolve_illness_spelling_variants_and_compound():
    """Tests fault-tolerant resolution across Sanskrit transliteration variants and compounds."""
    # 1. Visarga and capitalization
    r1 = resolve_illness("KAsa")
    r2 = resolve_illness("kasaH")
    r3 = resolve_illness("kāsa")
    assert r1.matched and r2.matched and r3.matched
    assert r1.key == r2.key == r3.key
    assert r1.english == "Cough"

    # 2. Sanskrit w vs v tolerance
    r_jvara = resolve_illness("jvaraH")
    r_jwara = resolve_illness("jwarah")
    assert r_jvara.matched and r_jwara.matched
    assert r_jvara.english == "Fever"
    assert r_jwara.english == "Fever"

    # 3. Sibilant tolerance (z vs sh vs s)
    r_zotha = resolve_illness("Zotha")
    r_shothah = resolve_illness("shothah")
    assert r_zotha.matched and r_shothah.matched
    assert r_zotha.english == "Edema"
    assert r_shothah.english == "Edema"

    # 4. Svasa vs Shwasa tolerance
    r_svasa = resolve_illness("Svasa")
    r_shwasah = resolve_illness("shwasah")
    assert r_svasa.matched and r_shwasah.matched
    assert r_svasa.english == "Dyspnea"
    assert r_shwasah.english == "Dyspnea"

    # 5. Compound term splits
    r_compound = resolve_illness("ArtavadoSaH/ArtavaduSTiH/rajodoSaH")
    r_part1 = resolve_illness("ArtavadoSaH")
    r_part2 = resolve_illness("ArtavaduSTiH")
    r_part3 = resolve_illness("rajodoSaH")
    assert r_compound.matched
    assert r_part1.matched and r_part2.matched and r_part3.matched
    assert r_compound.key == r_part1.key == r_part2.key == r_part3.key


def test_catalog_precedence_and_conflicts():
    """Proves that Stage C catalog curated labels win on conflict over CSV translations."""
    r_kasa = resolve_illness("KAsa")
    assert r_kasa.matched
    assert r_kasa.catalog_code == "IND_KASA"
    assert r_kasa.english == "Cough"
    assert "Bronchitis" in r_kasa.english_synonyms
    assert r_kasa.labels["hi"].label == "कास (खांसी)"
    assert r_kasa.labels["sa"].label == "कास"
    # Preserves non-catalog language translations
    assert r_kasa.labels["ta"].label == "இருமல்"

    r_jvara = resolve_illness("jvaraH")
    assert r_jvara.matched
    assert r_jvara.catalog_code == "IND_JVARA"
    assert r_jvara.english == "Fever"
    assert "Pyrexia" in r_jvara.english_synonyms
    assert r_jvara.labels["hi"].label == "ज्वर (बुखार)"

    # Conflicts are recorded
    conflicts = get_catalog_csv_conflicts()
    assert len(conflicts) > 0
    kasa_conflicts = [c for c in conflicts if c["catalog_code"] == "IND_KASA"]
    assert len(kasa_conflicts) == 1


def test_unmatched_fallback():
    """Verifies that an unknown illness name falls back to readable text with a subtle note."""
    r_unmatched = resolve_illness("UnknownIllnessCondition")
    assert not r_unmatched.matched
    assert r_unmatched.note == "translation not available"
    assert r_unmatched.english == "Unknownillnesscondition"
    assert r_unmatched.origin == "machine_generated"
    assert r_unmatched.verification == "unverified"


def test_procedure_and_non_disease_kind_tag():
    """Verifies that procedure and non-disease concept terms receive appropriate kind tags."""
    r_yoni = resolve_illness("yonipuran")
    assert r_yoni.matched
    assert r_yoni.kind == "procedure"

    r_garbha = resolve_illness("Garbhanirodha")
    assert r_garbha.matched
    assert r_garbha.kind == "non-disease concept"

    r_medhya = resolve_illness("Medhya")
    assert r_medhya.matched
    assert r_medhya.kind == "non-disease concept"


def test_multilingual_search():
    """Verifies multilingual search across English, Hindi, Sanskrit, and various languages."""
    queries = [
        ("cough", "KAsa"),
        ("खांसी", "KAsa"),
        ("कास", "KAsa"),
        ("fever", "Jwara"),
        ("बुखार", "Jwara"),
        ("diabetes", "Madhumeha"),
        ("मधुमेह", "Madhumeha"),
        ("dyspepsia", "AgnimAndya"),
        ("piles", "Arsha"),
    ]
    for q, expected_term in queries:
        results = search_glossary(q)
        assert len(results) > 0, f"No results for query '{q}'"
        match_terms = [r.original_term for r in results]
        assert any(expected_term.lower() in t.lower() for t in match_terms), (
            f"Expected '{expected_term}' in results for '{q}', got: {match_terms}"
        )


def test_tolerant_illness_key():
    """Verifies phonetic tolerance helper function behavior."""
    assert tolerant_illness_key("KAsa") == "kasa"
    assert tolerant_illness_key("kasaH") == "kasa"
    assert tolerant_illness_key("kāsa") == "kasa"
    assert tolerant_illness_key("jvaraH") == "jvara"
    assert tolerant_illness_key("jwara") == "jvara"
    assert tolerant_illness_key("Shotha") == "sotha"
    assert tolerant_illness_key("Zotha") == "sotha"
    assert tolerant_illness_key("Shwasa") == "svasa"
    assert tolerant_illness_key("Svasa") == "svasa"
    assert tolerant_illness_key("Mutrakrichha") == "mutrakrica"
    assert tolerant_illness_key("") == ""
