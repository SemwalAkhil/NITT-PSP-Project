"""
Herbal Almanac — Herb Detail Presentation View-Model Layer (P0-2).

Pure functions for web presentation deduplication, domain grouping,
and attribute classification without database dependencies or mutating
repository_api return shapes.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime
from typing import Any

# Devanagari Unicode character range (\u0900-\u097F)
DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")

FIXED_DOMAIN_ORDER = ("rasa", "guna", "virya", "vipaka", "prabhava", "karma")

# ISO 639-1 language code mappings for vernacular names table
VERNACULAR_LANG_CODES: dict[str, str] = {
    "assamese": "as",
    "bengali": "bn",
    "english": "en",
    "gujarati": "gu",
    "hindi": "hi",
    "kannada": "kn",
    "malayalam": "ml",
    "marathi": "mr",
    "odia": "or",
    "oriya": "or",
    "punjabi": "pa",
    "sanskrit": "sa",
    "tamil": "ta",
    "telugu": "te",
    "urdu": "ur",
}


# ============================================================================
# 1. Botanical Identity & Timestamp Formatting
# ============================================================================

def clean_family(value: str | None) -> str:
    """Dedupe comma-separated repeated botanical family strings.

    Example:
        'Acanthaceae, Acanthaceae' -> 'Acanthaceae'
    """
    if not value:
        return "Not recorded"
    parts = [p.strip() for p in value.split(",") if p.strip()]
    unique = list(dict.fromkeys(parts))
    return ", ".join(unique) if unique else "Not recorded"


def format_retrieved(iso_ts: str | None) -> str:
    """Format ISO-8601 timestamp into readable date (e.g. '19 Nov 2026')."""
    if not iso_ts:
        return "Not recorded"
    cleaned = iso_ts.strip()
    try:
        ts_for_parse = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_for_parse)
        return dt.strftime("%d %b %Y")
    except Exception:
        # Fallback regex date extraction
        match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", cleaned)
        if match:
            y, m, d = match.groups()
            months = [
                "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
            ]
            try:
                m_int = int(m)
                if 1 <= m_int <= 12:
                    return f"{int(d)} {months[m_int]} {y}"
            except Exception:
                pass
        return cleaned


# ============================================================================
# 2. Stage C Properties Deduplication & Grouping
# ============================================================================

def dedupe_properties(properties: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Group properties by (domain, concept_code, part_concept_code).

    Preserves first display_label, canonical Sanskrit references (Devanagari + IAST),
    claim_count, and distinct source expressions.
    Never merges entries with different concepts or distinct is_disputed status.
    """
    if not properties:
        return []

    groups: dict[tuple[str, str, str | None, bool], list[dict[str, Any]]] = {}
    group_order: list[tuple[str, str, str | None, bool]] = []

    for prop in properties:
        domain = str(prop.get("domain", "")).lower()
        c_code = str(prop.get("concept_code", ""))
        p_code = prop.get("part_concept_code")
        is_disp = bool(prop.get("is_disputed", False))

        key = (domain, c_code, p_code, is_disp)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(prop)

    deduped: list[dict[str, Any]] = []
    for key in group_order:
        items = groups[key]
        first = items[0]
        merged = dict(first)

        merged["claim_count"] = len(items)
        distinct_sources: list[str] = []
        for it in items:
            expr = it.get("source_expression")
            if expr and expr not in distinct_sources:
                distinct_sources.append(expr)
        merged["source_expressions"] = distinct_sources
        deduped.append(merged)

    return deduped


def group_properties_by_domain(
    properties: list[dict[str, Any]] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Group deduped properties into fixed dictionary in classical order.

    Order: rasa, guna, virya, vipaka, prabhava, karma.
    Missing domains contain empty lists.
    """
    grouped: dict[str, list[dict[str, Any]]] = {
        domain: [] for domain in FIXED_DOMAIN_ORDER
    }
    if not properties:
        return grouped

    deduped = dedupe_properties(properties)
    for prop in deduped:
        d = str(prop.get("domain", "")).lower()
        if d in grouped:
            grouped[d].append(prop)
        else:
            grouped.setdefault(d, []).append(prop)

    return grouped


def virya_consensus(properties: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Evaluate Virya consensus across source claims.

    If all Virya claims map to one concept:
        'All N source claims agree: Śīta (Cold)'
    If several concepts:
        'Sources differ'
    If none:
        Returns None to hide the card.
    """
    if not properties:
        return None

    virya_props = [
        p for p in properties if str(p.get("domain", "")).lower() == "virya"
    ]
    if not virya_props:
        return None

    # Calculate total claim count across virya properties
    total_claims = sum(p.get("claim_count", 1) for p in virya_props)
    unique_concept_codes = list(dict.fromkeys(p.get("concept_code", "") for p in virya_props))

    if len(unique_concept_codes) == 1:
        first = virya_props[0]
        label = first.get("display_label") or unique_concept_codes[0]
        iast = first.get("canonical_sanskrit_iast")
        display = f"{iast} ({label})" if (iast and iast != label) else label
        return {
            "status": "consensus",
            "agrees": True,
            "text": f"All {total_claims} source claims agree: {display}",
            "concept_code": unique_concept_codes[0],
            "claim_count": total_claims,
        }
    else:
        return {
            "status": "divergent",
            "agrees": False,
            "text": "Sources differ",
            "concept_codes": unique_concept_codes,
            "claim_count": total_claims,
        }


# ============================================================================
# 3. Dosha Effects Deduplication & 3-Dosha Matrix
# ============================================================================

def dedupe_dosha_effects(
    effects: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Dedupe dosha effects by (dosha, effect) and synthesize complete 3-dosha view.

    Returns:
        {
            "unique_effects": list of deduped (dosha, effect) records,
            "three_doshas": [
                {"dosha": "Vata", "effect": ..., "claim_count": ..., "source_expressions": [...]},
                {"dosha": "Pitta", ...},
                {"dosha": "Kapha", ...},
            ]
        }
    Note: When nothing is recorded for a Dosha, effect is 'Not recorded' (never 'no effect').
    """
    if not effects:
        effects = []

    # Map effects by dosha name
    dosha_groups: dict[str, dict[str, Any]] = {
        "Vata": {"dosha": "Vata", "effect": "Not recorded", "claim_count": 0, "source_expressions": [], "recorded": False},
        "Pitta": {"dosha": "Pitta", "effect": "Not recorded", "claim_count": 0, "source_expressions": [], "recorded": False},
        "Kapha": {"dosha": "Kapha", "effect": "Not recorded", "claim_count": 0, "source_expressions": [], "recorded": False},
    }

    unique_pairs: dict[tuple[str, str], dict[str, Any]] = {}

    for eff in effects:
        # Normalize dosha name
        d_code = str(eff.get("dosha_concept_code", ""))
        d_label = str(eff.get("dosha_display_label", "") or eff.get("dosha", ""))
        if "VATA" in d_code.upper() or "vata" in d_label.lower():
            dosha_key = "Vata"
        elif "PITTA" in d_code.upper() or "pitta" in d_label.lower():
            dosha_key = "Pitta"
        elif "KAPHA" in d_code.upper() or "kapha" in d_label.lower():
            dosha_key = "Kapha"
        else:
            dosha_key = d_label.capitalize() or "Unknown"

        # Normalize effect label
        e_code = str(eff.get("effect_concept_code", ""))
        e_label = str(eff.get("effect_display_label", "") or eff.get("effect", ""))
        if "DECREASE" in e_code.upper() or "shamana" in e_label.lower() or "pacif" in e_label.lower() or "decrease" in e_label.lower():
            effect_text = "Pacifies / Decreases"
            effect_kind = "decrease"
        elif "INCREASE" in e_code.upper() or "vardhaka" in e_label.lower() or "aggravat" in e_label.lower() or "increase" in e_label.lower():
            effect_text = "Aggravates / Increases"
            effect_kind = "increase"
        else:
            effect_text = e_label or "Unspecified effect"
            effect_kind = "unspecified"

        pair_key = (dosha_key, effect_text)
        src_expr = eff.get("source_expression")

        if pair_key not in unique_pairs:
            unique_pairs[pair_key] = {
                "dosha": dosha_key,
                "effect": effect_text,
                "effect_kind": effect_kind,
                "claim_count": 0,
                "source_expressions": [],
            }
        unique_pairs[pair_key]["claim_count"] += 1
        if src_expr and src_expr not in unique_pairs[pair_key]["source_expressions"]:
            unique_pairs[pair_key]["source_expressions"].append(src_expr)

        # Update 3-dosha view
        if dosha_key in dosha_groups:
            dg = dosha_groups[dosha_key]
            dg["recorded"] = True
            dg["effect"] = effect_text
            dg["effect_kind"] = effect_kind
            dg["claim_count"] += 1
            if src_expr and src_expr not in dg["source_expressions"]:
                dg["source_expressions"].append(src_expr)

    return {
        "unique_effects": list(unique_pairs.values()),
        "three_doshas": [dosha_groups["Vata"], dosha_groups["Pitta"], dosha_groups["Kapha"]],
    }


# ============================================================================
# 4. Legacy Herb Attributes Classifier & Grouping
# ============================================================================

def classify_subfield_variant(subfield: str) -> str:
    """Classify an attribute subfield variant into english, iast, hindi, or custom.

    Rules:
        - Exactly 'Name' or ends with '.Name' -> 'english'
        - Contains '(Diacritical)' or 'Diacritical' -> 'iast'
        - Contains Devanagari characters -> 'hindi'
        - Otherwise -> lowercase sanitized subfield identifier
    """
    s = subfield.strip()
    if s == "Name" or s.endswith(".Name"):
        return "english"
    if "(Diacritical)" in s or "Diacritical" in s or "diacritical" in s.lower():
        return "iast"
    if DEVANAGARI_REGEX.search(s):
        return "hindi"
    return s


def group_attributes(attributes: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Group raw herb_attributes rows into structured domain models.

    Organizes attributes into dedicated sections:
        - vernacular_names: Language | Names table with lang= attributes
        - parts_used: merged English | IAST | Devanagari table
        - dosage_formulations: Name, Form, Reference table
        - dose: list of dose statements
        - doshakarma: merged English | IAST | Devanagari table (if needed)
        - therapeutic_usage: list of condition strings
        - etymology_and_pharmacopoeia: collapsed references, vargas, verses
        - raw_dravyaguna: Rasa/Guna/Virya/Vipaka raw records collapsed
        - other_groups: any other unrecognized attributes
    Each group contains a single deduped list of sources.
    """
    if not attributes:
        attributes = []

    # Partition raw attributes by primary group
    raw_by_group: dict[str, list[dict[str, Any]]] = {}
    for attr in attributes:
        fname = str(attr.get("field_name", "")).strip()
        if "." in fname:
            grp, sub = fname.split(".", 1)
        else:
            grp, sub = fname, "Name"
        grp = grp.strip()
        sub = sub.strip()

        item = {
            "group": grp,
            "subfield": sub,
            "variant": classify_subfield_variant(sub),
            "value": str(attr.get("value", "")).strip(),
            "source_text": str(attr.get("source_text", "")).strip(),
            "source_language": attr.get("source_language"),
        }
        raw_by_group.setdefault(grp, []).append(item)

    # 1. Vernacular Names
    vernacular_names: list[dict[str, str]] = []
    vernacular_sources: list[str] = []
    if "Vernacular Names" in raw_by_group:
        lang_dict: dict[str, list[str]] = {}
        for item in raw_by_group["Vernacular Names"]:
            lang = item["subfield"]
            val = item["value"]
            if val:
                lang_dict.setdefault(lang, []).append(val)
            src = item["source_text"]
            if src and src not in vernacular_sources:
                vernacular_sources.append(src)

        for lang, vals in sorted(lang_dict.items()):
            code = VERNACULAR_LANG_CODES.get(lang.lower(), "en")
            vernacular_names.append({
                "language": lang,
                "lang_code": code,
                "names": ", ".join(vals),
            })

    # Helper: Merge triple variant groups (English | IAST | Hindi)
    def _merge_triple_group(grp_name: str) -> dict[str, Any]:
        items = raw_by_group.get(grp_name, [])
        sources = list(dict.fromkeys(it["source_text"] for it in items if it["source_text"]))

        eng_vals = [it["value"] for it in items if it["variant"] == "english" and it["value"]]
        iast_vals = [it["value"] for it in items if it["variant"] == "iast" and it["value"]]
        hin_vals = [it["value"] for it in items if it["variant"] == "hindi" and it["value"]]

        max_len = max(len(eng_vals), len(iast_vals), len(hin_vals), 0)
        rows: list[dict[str, str]] = []
        for i in range(max_len):
            rows.append({
                "english": eng_vals[i] if i < len(eng_vals) else "",
                "iast": iast_vals[i] if i < len(iast_vals) else "",
                "hindi": hin_vals[i] if i < len(hin_vals) else "",
            })
        return {"group_name": grp_name, "rows": rows, "sources": sources}

    # 2. Parts Used
    parts_used = _merge_triple_group("Parts Used")

    # 3. Dosage Formulation
    dosage_formulations: list[dict[str, Any]] = []
    dosage_references: list[str] = []
    dosage_sources: list[str] = []
    if "Dosage Formulation" in raw_by_group:
        df_items = raw_by_group["Dosage Formulation"]
        dosage_sources = list(dict.fromkeys(it["source_text"] for it in df_items if it["source_text"]))

        names = [it["value"] for it in df_items if it["subfield"] == "Name" and it["value"]]
        forms = [it["value"] for it in df_items if "Form" in it["subfield"] and it["value"]]
        refs = [it["value"] for it in df_items if "Reference" in it["subfield"] and it["value"]]

        dosage_references = list(dict.fromkeys(refs))
        max_df = max(len(names), len(forms), 0)
        for i in range(max_df):
            n = names[i] if i < len(names) else ""
            f = forms[i] if i < len(forms) else ""
            r = refs[i] if i < len(refs) else ""
            dosage_formulations.append({"name": n, "form": f, "reference": r})

    # 4. Dose
    dose_items = [it["value"] for it in raw_by_group.get("Dose", []) if it["value"]]
    dose_sources = list(dict.fromkeys(it["source_text"] for it in raw_by_group.get("Dose", []) if it["source_text"]))

    # 5. Doshakarma & Karma summaries
    doshakarma_merged = _merge_triple_group("Doshakarma")
    karma_merged = _merge_triple_group("Karma")

    # 6. Therapeutic Usage
    therapeutic_usages = [
        it["value"] for it in raw_by_group.get("Therapeutic Usage", []) if it["value"]
    ]
    therapeutic_sources = list(
        dict.fromkeys(it["source_text"] for it in raw_by_group.get("Therapeutic Usage", []) if it["source_text"])
    )

    # 7. Etymology and Pharmacopoeial Status
    etymology_merged = _merge_triple_group("Etymology")
    varga_merged = _merge_triple_group("Varga")
    pharm_status_items = raw_by_group.get("Pharmacopoeial Status", [])
    pharm_status_sources = list(dict.fromkeys(it["source_text"] for it in pharm_status_items if it["source_text"]))
    pharm_records: list[dict[str, str]] = [
        {"field": it["subfield"], "value": it["value"]} for it in pharm_status_items if it["value"]
    ]

    # 8. Raw Dravyaguna properties (Rasa, Guna, Virya, Vipaka) for collapsed display
    raw_dravyaguna_groups: list[dict[str, Any]] = []
    for g_name in ("Rasa", "Guna", "Virya", "Vipaka", "Prabhava", "Mahakashaya", "Skandha"):
        if g_name in raw_by_group:
            raw_dravyaguna_groups.append(_merge_triple_group(g_name))

    # 9. Other unrecognized groups (fallback)
    handled_groups = {
        "Vernacular Names", "Parts Used", "Dosage Formulation", "Dose",
        "Doshakarma", "Karma", "Therapeutic Usage", "Etymology",
        "Pharmacopoeial Status", "Varga", "Rasa", "Guna", "Virya", "Vipaka",
        "Prabhava", "Mahakashaya", "Skandha",
    }
    other_groups: list[dict[str, Any]] = []
    for g_name, items in raw_by_group.items():
        if g_name not in handled_groups:
            sources = list(dict.fromkeys(it["source_text"] for it in items if it["source_text"]))
            rows = [{"field": it["subfield"], "value": it["value"]} for it in items]
            other_groups.append({
                "group_name": g_name,
                "rows": rows,
                "sources": sources,
            })

    return {
        "vernacular_names": vernacular_names,
        "vernacular_sources": vernacular_sources,
        "parts_used": parts_used,
        "dosage_formulations": dosage_formulations,
        "dosage_references": dosage_references,
        "dosage_sources": dosage_sources,
        "dose_items": dose_items,
        "dose_sources": dose_sources,
        "doshakarma_merged": doshakarma_merged,
        "karma_merged": karma_merged,
        "therapeutic_usages": therapeutic_usages,
        "therapeutic_sources": therapeutic_sources,
        "etymology_merged": etymology_merged,
        "varga_merged": varga_merged,
        "pharmacopoeial_records": pharm_records,
        "pharmacopoeial_sources": pharm_status_sources,
        "raw_dravyaguna_groups": raw_dravyaguna_groups,
        "other_groups": other_groups,
    }


# ============================================================================
# 5. Herb Images & Multilingual Vernacular Helpers
# ============================================================================

def herb_image_url(herb: dict[str, Any] | None) -> str | None:
    """Return CCRAS plant image URL or None if plant ID cannot be resolved.

    URL structure:
        https://dravya.ccras.org.in/resources/views/admin/required/upload/<plant_id>.jpg
    Only built for CCRAS-source herbs.
    """
    if not herb:
        return None
    from .herb_glossary import get_herb_glossary_store, is_ccras_source

    if not is_ccras_source(herb.get("source")):
        return None

    plant_id = get_herb_glossary_store().get_plant_id(herb)
    if plant_id and plant_id > 0:
        return f"https://dravya.ccras.org.in/resources/views/admin/required/upload/{plant_id}.jpg"
    return None


def herb_vernacular_table(herb: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return list of vernacular names for herb across Indian languages."""
    if not herb:
        return []
    from .herb_glossary import get_herb_glossary_store

    store = get_herb_glossary_store()
    plant_id = store.get_plant_id(herb)
    if not plant_id:
        return []
    resolved = store.resolve_by_id(plant_id)
    if not resolved:
        return []
    rows: list[dict[str, str]] = []
    for lang, name in resolved.vernacular_names.items():
        if name and name != "N/A":
            rows.append({
                "language": lang,
                "name": name,
                "lang_code": VERNACULAR_LANG_CODES.get(lang.lower(), "en"),
            })
    return rows


def herb_name(herb: dict[str, Any] | None, lang: str | None = "en") -> str | None:
    """Return herb name in the requested language code ('hi', 'ta', 'ur', 'en', etc.).

    Resolves the herb via HerbGlossaryStore (by plant ID or fallback match).
    If lang is 'en': returns glossary English name if available, else herb['english_name'].
    If lang != 'en': returns native script name if available and not 'N/A', else None.
    """
    if not herb:
        return None
    from .herb_glossary import get_herb_glossary_store

    store = get_herb_glossary_store()
    plant_id = store.get_plant_id(herb)
    resolved = store.resolve_by_id(plant_id) if plant_id else None
    if not resolved:
        resolved = store.resolve_herb(
            herb.get("botanical_name") or herb.get("original_name") or herb.get("english_name")
        )

    target_lang = (lang or "en").lower()
    if resolved:
        val = resolved.get_name(target_lang)
        if val and val.strip() and val.strip() != "N/A":
            return val.strip()

    if target_lang == "en":
        val = herb.get("english_name")
        if val and val.strip() and val.strip() != "N/A":
            return val.strip()
        orig = herb.get("original_name")
        if orig and orig.strip() and orig.strip() != "N/A":
            return orig.strip()

    return None


def qs(*args: dict[str, Any], **params: Any) -> str:
    """Build a safe URL query string ('?a=1&b=2', or '' if nothing).

    Drops parameters whose value is None or empty string (""), and drops falsy
    flags like include_disputed=False / "false".
    Preserves meaningful 0 values.
    Encodes all keys and values safely with urllib.parse.urlencode.
    """
    merged: dict[str, Any] = {}
    for arg in args:
        if isinstance(arg, dict):
            merged.update(arg)
    merged.update(params)

    cleaned: list[tuple[str, Any]] = []
    for k, v in merged.items():
        if v is None or v == "":
            continue
        if isinstance(v, bool) and not v:
            continue
        if k in ("include_disputed", "include_provisional") and str(v).lower() in ("false", "0", ""):
            continue
        cleaned.append((k, str(v)))

    if not cleaned:
        return ""
    return "?" + urllib.parse.urlencode(cleaned, doseq=True)



