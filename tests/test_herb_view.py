"""
Unit tests for herb_view presentation view-model layer (P0-2).

Verifies pure functions for property deduplication, 3-dosha synthesis,
attribute variant grouping, Virya consensus, family cleaning, and date formatting.
"""

from __future__ import annotations

import pytest
from herbal_almanac.herb_view import (
    clean_family,
    format_retrieved,
    dedupe_properties,
    group_properties_by_domain,
    virya_consensus,
    dedupe_dosha_effects,
    classify_subfield_variant,
    group_attributes,
)


def test_clean_family():
    assert clean_family("Acanthaceae, Acanthaceae") == "Acanthaceae"
    assert clean_family("Lamiaceae, Fabaceae, Lamiaceae") == "Lamiaceae, Fabaceae"
    assert clean_family("") == "Not recorded"
    assert clean_family(None) == "Not recorded"


def test_format_retrieved():
    assert format_retrieved("2026-11-19T17:25:00Z") == "19 Nov 2026"
    assert format_retrieved("2026-11-19") == "19 Nov 2026"
    assert format_retrieved(None) == "Not recorded"
    assert format_retrieved("") == "Not recorded"


def test_dedupe_properties():
    # Triple variant claims for Tikta Rasa
    props = [
        {
            "domain": "rasa",
            "concept_code": "RASA_TIKTA",
            "display_label": "Bitter",
            "part_concept_code": None,
            "source_expression": "Tikta",
            "is_disputed": False,
        },
        {
            "domain": "rasa",
            "concept_code": "RASA_TIKTA",
            "display_label": "Bitter",
            "part_concept_code": None,
            "source_expression": "Tikta (Diacritical)",
            "is_disputed": False,
        },
        {
            "domain": "rasa",
            "concept_code": "RASA_TIKTA",
            "display_label": "Bitter",
            "part_concept_code": None,
            "source_expression": "तिक्त",
            "is_disputed": False,
        },
        {
            "domain": "rasa",
            "concept_code": "RASA_KASHAYA",
            "display_label": "Astringent",
            "part_concept_code": None,
            "source_expression": "Kashaya",
            "is_disputed": False,
        },
    ]

    deduped = dedupe_properties(props)
    assert len(deduped) == 2

    tikta = deduped[0]
    assert tikta["concept_code"] == "RASA_TIKTA"
    assert tikta["claim_count"] == 3
    assert len(tikta["source_expressions"]) == 3
    assert "Tikta" in tikta["source_expressions"]

    kashaya = deduped[1]
    assert kashaya["concept_code"] == "RASA_KASHAYA"
    assert kashaya["claim_count"] == 1


def test_dedupe_properties_preserves_disputed_separation():
    props = [
        {"domain": "virya", "concept_code": "VIRYA_USHNA", "is_disputed": False, "source_expression": "Ushna 1"},
        {"domain": "virya", "concept_code": "VIRYA_USHNA", "is_disputed": True, "source_expression": "Ushna 2 (disputed)"},
    ]
    deduped = dedupe_properties(props)
    assert len(deduped) == 2
    assert not deduped[0]["is_disputed"]
    assert deduped[1]["is_disputed"]


def test_group_properties_by_domain():
    props = [
        {"domain": "rasa", "concept_code": "RASA_TIKTA"},
        {"domain": "guna", "concept_code": "GUNA_LAGHU"},
        {"domain": "karma", "concept_code": "KARMA_DIPANA"},
    ]
    grouped = group_properties_by_domain(props)
    assert list(grouped.keys()) == ["rasa", "guna", "virya", "vipaka", "prabhava", "karma"]
    assert len(grouped["rasa"]) == 1
    assert len(grouped["guna"]) == 1
    assert len(grouped["virya"]) == 0
    assert len(grouped["vipaka"]) == 0
    assert len(grouped["prabhava"]) == 0
    assert len(grouped["karma"]) == 1


def test_virya_consensus():
    # 1. No virya data
    assert virya_consensus([]) is None

    # 2. Consensus: all claims agree
    agreeing = [
        {"domain": "virya", "concept_code": "VIRYA_SHITA", "display_label": "Cold", "canonical_sanskrit_iast": "Śīta", "claim_count": 3},
    ]
    res_agree = virya_consensus(agreeing)
    assert res_agree is not None
    assert res_agree["agrees"] is True
    assert "All 3 source claims agree" in res_agree["text"]
    assert "Śīta (Cold)" in res_agree["text"]

    # 3. Divergence: multiple concepts
    differing = [
        {"domain": "virya", "concept_code": "VIRYA_USHNA", "display_label": "Hot", "claim_count": 2},
        {"domain": "virya", "concept_code": "VIRYA_SHITA", "display_label": "Cold", "claim_count": 1},
    ]
    res_diff = virya_consensus(differing)
    assert res_diff is not None
    assert res_diff["agrees"] is False
    assert res_diff["text"] == "Sources differ"


def test_dedupe_dosha_effects():
    # 3 claims asserting Vata decrease and Kapha decrease
    effects = [
        {"dosha_concept_code": "DOSHA_VATA", "effect_concept_code": "EFF_DECREASE", "source_expression": "KaphaVatahara"},
        {"dosha_concept_code": "DOSHA_VATA", "effect_concept_code": "EFF_DECREASE", "source_expression": "कफवातहर"},
        {"dosha_concept_code": "DOSHA_KAPHA", "effect_concept_code": "EFF_DECREASE", "source_expression": "KaphaVatahara"},
    ]

    res = dedupe_dosha_effects(effects)
    assert len(res["unique_effects"]) == 2

    # Verify 3-dosha complete view
    three = res["three_doshas"]
    assert len(three) == 3
    assert [d["dosha"] for d in three] == ["Vata", "Pitta", "Kapha"]

    vata = three[0]
    assert vata["recorded"] is True
    assert vata["effect"] == "Pacifies / Decreases"
    assert vata["claim_count"] == 2
    assert len(vata["source_expressions"]) == 2

    pitta = three[1]
    assert pitta["recorded"] is False
    assert pitta["effect"] == "Not recorded"
    assert pitta["claim_count"] == 0

    kapha = three[2]
    assert kapha["recorded"] is True
    assert kapha["effect"] == "Pacifies / Decreases"
    assert kapha["claim_count"] == 1


def test_classify_subfield_variant():
    assert classify_subfield_variant("Name") == "english"
    assert classify_subfield_variant("Guna(Diacritical)") == "iast"
    assert classify_subfield_variant("गुण(हिन्दी)") == "hindi"
    assert classify_subfield_variant("रस (हिन्दी)") == "hindi"
    assert classify_subfield_variant("Dosage(Form)") == "Dosage(Form)"


def test_group_attributes_and_source_deduping():
    raw_attrs = [
        # Vernacular Names
        {"field_name": "Vernacular Names.Hindi", "value": "तुलसी", "source_text": "CCRAS 1"},
        {"field_name": "Vernacular Names.English", "value": "Holy Basil", "source_text": "CCRAS 1"},
        # Guna triple variant with repeated source text
        {"field_name": "Guna.Name", "value": "Laghu", "source_text": "CCRAS 1"},
        {"field_name": "Guna.Guna(Diacritical)", "value": "Laghu", "source_text": "CCRAS 1"},
        {"field_name": "Guna.गुण(हिन्दी)", "value": "लघु", "source_text": "CCRAS 1"},
        {"field_name": "Guna.Name", "value": "Tikshna", "source_text": "CCRAS 2"},
        {"field_name": "Guna.Guna(Diacritical)", "value": "Tīkṣṇa", "source_text": "CCRAS 2"},
        {"field_name": "Guna.गुण(हिन्दी)", "value": "तीक्ष्ण", "source_text": "CCRAS 2"},
        # Unknown fallback group
        {"field_name": "CustomGroup.CustomField", "value": "CustomVal", "source_text": "CCRAS 3"},
    ]

    grouped = group_attributes(raw_attrs)

    # 1. Vernacular names table
    v_names = grouped["vernacular_names"]
    assert len(v_names) == 2
    assert v_names[0]["language"] == "English"
    assert v_names[0]["lang_code"] == "en"
    assert v_names[1]["language"] == "Hindi"
    assert v_names[1]["lang_code"] == "hi"

    # 2. Raw dravyaguna groups merged
    raw_dg = grouped["raw_dravyaguna_groups"]
    assert len(raw_dg) == 1
    guna_grp = raw_dg[0]
    assert guna_grp["group_name"] == "Guna"
    assert len(guna_grp["rows"]) == 2
    assert guna_grp["rows"][0]["english"] == "Laghu"
    assert guna_grp["rows"][0]["iast"] == "Laghu"
    assert guna_grp["rows"][0]["hindi"] == "लघु"
    # Verify source deduplication
    assert guna_grp["sources"] == ["CCRAS 1", "CCRAS 2"]

    # 3. Fallback for custom group
    assert len(grouped["other_groups"]) == 1
    assert grouped["other_groups"][0]["group_name"] == "CustomGroup"
    assert grouped["other_groups"][0]["rows"][0]["field"] == "CustomField"
    assert grouped["other_groups"][0]["rows"][0]["value"] == "CustomVal"
