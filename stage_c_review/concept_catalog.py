"""
Herbal Almanac — Stage C.2 Work Package 1 (WP-1)
Canonical Dravyaguna Concept Catalog and Namespace Validator
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, NamedTuple

from schema_capability_gate import require_stage_c_schema_v3


# ============================================================================
# 1. Concept Domain and Prefix Mapping (ADR Decision 1.B)
# ============================================================================

DOMAIN_PREFIX_MAP: dict[str, str] = {
    "rasa": "RASA_",
    "guna": "GUNA_",
    "virya": "VIRYA_",
    "vipaka": "VIPAKA_",
    "prabhava": "PRABHAVA_",
    "karma": "KARMA_",
    "dosha": "DOSHA_",
    "dosha_effect": "EFFECT_",
    "plant_part": "PART_",
    "preparation_form": "PREP_",
    "indication": "IND_",
}

CONCEPT_CODE_REGEX = re.compile(r"^[A-Z]+_[A-Z0-9_]+$")


def validate_concept_code_prefix(concept_code: str, concept_domain: str) -> None:
    """Validates that a concept code conforms to namespace naming conventions.
    
    Rules:
    1. Both concept_code and concept_domain must be non-empty strings.
    2. concept_code must match ^[A-Z]+_[A-Z0-9_]+$.
    3. concept_domain must be one of the 11 accepted Stage C domains.
    4. concept_code must start with the exact prefix assigned to concept_domain.
    
    Raises:
        ValueError: If any validation rule is violated.
    """
    if not isinstance(concept_code, str) or not concept_code.strip():
        raise ValueError(f"Concept code must be a non-empty string; got {concept_code!r}")
    
    if not isinstance(concept_domain, str) or not concept_domain.strip():
        raise ValueError(f"Concept domain must be a non-empty string; got {concept_domain!r}")
    
    if not CONCEPT_CODE_REGEX.match(concept_code):
        raise ValueError(
            f"Concept code {concept_code!r} does not match required pattern ^[A-Z]+_[A-Z0-9_]+$ "
            f"(must be uppercase ASCII alphanumeric with underscores and at least one underscore separator)."
        )
    
    if concept_domain not in DOMAIN_PREFIX_MAP:
        raise ValueError(
            f"Unknown concept domain {concept_domain!r}. Must be one of: {sorted(DOMAIN_PREFIX_MAP.keys())}"
        )
    
    expected_prefix = DOMAIN_PREFIX_MAP[concept_domain]
    if not concept_code.startswith(expected_prefix):
        raise ValueError(
            f"Concept code {concept_code!r} invalid for domain {concept_domain!r}. "
            f"Expected prefix {expected_prefix!r}."
        )


def normalize_label(label: str) -> str:
    """Normalizes label text for natural unique key deduplication."""
    return unicodedata.normalize("NFC", label.strip().lower())


# ============================================================================
# 2. Seed Data Models
# ============================================================================

class LabelSeed(NamedTuple):
    language_code: str
    script_code: str
    label_text: str
    label_type: str
    translation_origin: str
    is_preferred: int = 1
    normalized_label: str | None = None

    def get_normalized(self) -> str:
        return self.normalized_label or normalize_label(self.label_text)


class CitationSeed(NamedTuple):
    authority_citation: str
    citation_type: str = "classical_text"
    citation_notes: str | None = None
    target_language: str = "sa"
    target_script: str = "Deva"


class ConceptSeed(NamedTuple):
    concept_code: str
    concept_domain: str
    status: str
    parent_concept_code: str | None
    labels: list[LabelSeed]
    citations: list[CitationSeed]


# ============================================================================
# 3. Canonical Concept Seed Dataset
# ============================================================================

CANONICAL_CONCEPTS: list[ConceptSeed] = [
    # ------------------------------------------------------------------------
    # 1. RASA (6 active concepts)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "RASA_MADHURA", "rasa", "active", None,
        [
            LabelSeed("sa", "Deva", "मधुर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Madhura", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "मधुर", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Sweet", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.42", "classical_text", "Canonical definition of Madhura rasa")]
    ),
    ConceptSeed(
        "RASA_AMLA", "rasa", "active", None,
        [
            LabelSeed("sa", "Deva", "अम्ल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Amla", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "अम्ल", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Sour", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.43", "classical_text", "Canonical definition of Amla rasa")]
    ),
    ConceptSeed(
        "RASA_LAVANA", "rasa", "active", None,
        [
            LabelSeed("sa", "Deva", "लवण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Lavaṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Lavana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "नमकीन (लवण)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Salty", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.44", "classical_text", "Canonical definition of Lavaṇa rasa")]
    ),
    ConceptSeed(
        "RASA_KATU", "rasa", "active", None,
        [
            LabelSeed("sa", "Deva", "कटु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kaṭu", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Katu", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कटु (तीखा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Pungent", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.45", "classical_text", "Canonical definition of Kaṭu rasa")]
    ),
    ConceptSeed(
        "RASA_TIKTA", "rasa", "active", None,
        [
            LabelSeed("sa", "Deva", "तिक्त", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Tikta", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "तिक्त (कड़वा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Bitter", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.46", "classical_text", "Canonical definition of Tikta rasa")]
    ),
    ConceptSeed(
        "RASA_KASHAYA", "rasa", "active", None,
        [
            LabelSeed("sa", "Deva", "कषाय", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kaṣāya", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kasaya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कषाय (कसैला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Astringent", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.47", "classical_text", "Canonical definition of Kaṣāya rasa")]
    ),

    # ------------------------------------------------------------------------
    # 2. GUNA (30 active concepts: 20 Gurvadi + 10 Paradi)
    # ------------------------------------------------------------------------
    # 20 Gurvadi Gunas
    ConceptSeed(
        "GUNA_GURU", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "गुरु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Guru", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "गुरु (भारी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Heavy", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_LAGHU", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "लघु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Laghu", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "लघु (हल्का)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Light", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SHITA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "शीत", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śīta", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sheeta", "synonym", "scholarly_reference", 0),
            LabelSeed("sa", "Latn", "Shita", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "शीत (ठंडा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Cold", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_USHNA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "उष्ण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Uṣṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ushna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "उष्ण (गर्म)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Hot", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SNIGDHA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "स्निग्ध", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Snigdha", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "स्निग्ध (चिकना)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Unctuous", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_RUKSHA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "रूक्ष", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rūkṣa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ruksha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "रूक्ष (रूखा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dry", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_MANDA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "मन्द", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Manda", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "मन्द (धीमा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dull / Slow", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_TIKSHNA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "तीक्ष्ण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Tīkṣṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Tikshna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "तीक्ष्ण (तीव्र)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Sharp / Penetrating", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_STHIRA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "स्थिर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sthira", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "स्थिर", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Stable / Static", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SARA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "सर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sara", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "सर (गतिशील)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Mobile / Fluid", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_MRIDU", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "मृदु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mṛdu", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mridu", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "मृदु (कोमल)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Soft", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_KATHINA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "कठिन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kaṭhina", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kathina", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कठिन (कठोर)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Hard", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_VISHADA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "विशद", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Viśada", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vishada", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "विशद (स्वच्छ)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Clear / Non-slimy", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_PICCHILA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "पिच्छिल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Picchila", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "पिच्छिल (लुआबदार)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Slimy / Mucilaginous", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SHLAKSHNA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "श्लक्ष्ण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ślakṣṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Shlakshna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "श्लक्ष्ण (चिकना)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Smooth", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_KHARA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "खर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Khara", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "खर (खुरदरा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Rough", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SUKSHMA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "सूक्ष्म", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sūkṣma", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sukshma", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "सूक्ष्म (महीन)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Subtle / Minute", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_STHULA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "स्थूल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sthūla", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sthula", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "स्थूल (मोटा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Gross / Dense", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SANDRA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "सान्द्र", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sāndra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sandra", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "सान्द्र (गाढ़ा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Solid / Dense", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_DRAVA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "द्रव", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Drava", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "द्रव (तरल)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Liquid / Fluid", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-30", "classical_text", "Gurvadi Guna enumeration")]
    ),

    # 10 Paradi Gunas
    ConceptSeed(
        "GUNA_PARA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "पर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Para", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "पर (श्रेष्ठ)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Superior / Primary", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_APARA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "अपर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Apara", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "अपर (गौण)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Inferior / Secondary", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_YUKTI", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "युक्ति", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Yukti", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "युक्ति (तर्कसंगत योजना)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Rational Application / Propriety", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SAMKHYA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "संख्या", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Saṃkhyā", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Samkhya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "संख्या (गणना)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Number / Enumeration", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SAMYOGA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "संयोग", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Saṃyoga", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Samyoga", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "संयोग (मिलन)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Combination / Conjunction", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_VIBHAGA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "विभाग", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vibhāga", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vibhaga", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "विभाग (विभाजन)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Division / Disjunction", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_PRITHAKTVA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "पृथक्त्व", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pṛthaktva", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Prithaktva", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "पृथक्त्व (भिन्नता)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Separateness / Distinction", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_PARIMANA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "परिमाण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Parimāṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Parimana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "परिमाण (माप)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Measure / Dimension", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_SAMSKARA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "संस्कार", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Saṃskāra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Samskara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "संस्कार (प्रक्रिया)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Processing / Transformation", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),
    ConceptSeed(
        "GUNA_ABHYASA", "guna", "active", None,
        [
            LabelSeed("sa", "Deva", "अभ्यास", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Abhyāsa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Abhyasa", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अभ्यास (निरंतर प्रयोग)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Habituation / Constant Practice", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.29-31", "classical_text", "Paradi Guna enumeration")]
    ),

    # ------------------------------------------------------------------------
    # 3. VIRYA (2 active consensus + 7 provisional Ashta-Virya potencies)
    # ------------------------------------------------------------------------
    # 2 Active Dvividha Virya consensus
    ConceptSeed(
        "VIRYA_USHNA", "virya", "active", None,
        [
            LabelSeed("sa", "Deva", "उष्ण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Uṣṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ushna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "उष्ण वीर्य (गर्म प्रभाव)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Hot Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.65", "classical_text", "Dvividha Virya: Ushna virya")]
    ),
    ConceptSeed(
        "VIRYA_SHITA", "virya", "active", None,
        [
            LabelSeed("sa", "Deva", "शीत", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śīta", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sheeta", "synonym", "scholarly_reference", 0),
            LabelSeed("sa", "Latn", "Shita", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "शीत वीर्य (ठंडा प्रभाव)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Cold Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.65", "classical_text", "Dvividha Virya: Shita virya")]
    ),
    # 7 Provisional Ashta-Virya extended potencies (Adjudicated in WP-0 Section 14.2)
    ConceptSeed(
        "VIRYA_SNIGDHA", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "स्निग्ध", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Snigdha", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "स्निग्ध वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Unctuous Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 40.5", "classical_text", "Ashta-Virya potency model")]
    ),
    ConceptSeed(
        "VIRYA_RUKSHA", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "रूक्ष", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rūkṣa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ruksha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "रूक्ष वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dry Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 40.5", "classical_text", "Ashta-Virya potency model")]
    ),
    ConceptSeed(
        "VIRYA_GURU", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "गुरु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Guru", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "गुरु वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Heavy Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 40.5", "classical_text", "Ashta-Virya potency model")]
    ),
    ConceptSeed(
        "VIRYA_LAGHU", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "लघु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Laghu", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "लघु वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Light Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 40.5", "classical_text", "Ashta-Virya potency model")]
    ),
    ConceptSeed(
        "VIRYA_TIKSHNA", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "तीक्ष्ण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Tīkṣṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Tikshna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "तीक्ष्ण वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Sharp Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 40.5", "classical_text", "Ashta-Virya potency model")]
    ),
    ConceptSeed(
        "VIRYA_MRIDU", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "मृदु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mṛdu", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mridu", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "मृदु वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Soft Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 40.5", "classical_text", "Ashta-Virya variant: Mridu virya")]
    ),
    ConceptSeed(
        "VIRYA_MANDA", "virya", "provisional", None,
        [
            LabelSeed("sa", "Deva", "मन्द", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Manda", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "मन्द वीर्य", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dull Potency", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Aṣṭāṅga Hṛdaya / Nighaṇṭu commentaries", "classical_text", "Ashta-Virya variant: Manda virya substitution")]
    ),

    # ------------------------------------------------------------------------
    # 4. VIPAKA (3 active concepts)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "VIPAKA_MADHURA", "vipaka", "active", None,
        [
            LabelSeed("sa", "Deva", "मधुर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Madhura", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "मधुर विपाक", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Sweet Post-Digestive Effect", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.57", "classical_text", "Trividha Vipaka: Madhura vipaka")]
    ),
    ConceptSeed(
        "VIPAKA_AMLA", "vipaka", "active", None,
        [
            LabelSeed("sa", "Deva", "अम्ल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Amla", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "अम्ल विपाक", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Sour Post-Digestive Effect", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.58", "classical_text", "Trividha Vipaka: Amla vipaka")]
    ),
    ConceptSeed(
        "VIPAKA_KATU", "vipaka", "active", None,
        [
            LabelSeed("sa", "Deva", "कटु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kaṭu", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Katu", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कटु विपाक", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Pungent Post-Digestive Effect", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.59", "classical_text", "Trividha Vipaka: Katu vipaka")]
    ),

    # ------------------------------------------------------------------------
    # 5. DOSHA (3 active concepts)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "DOSHA_VATA", "dosha", "active", None,
        [
            LabelSeed("sa", "Deva", "वात", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vāta", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vata", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "वात दोष", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Vata Dosha", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 1.57", "classical_text", "Tridosha theory: Vata")]
    ),
    ConceptSeed(
        "DOSHA_PITTA", "dosha", "active", None,
        [
            LabelSeed("sa", "Deva", "पित्त", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pitta", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "पित्त दोष", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Pitta Dosha", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 1.57", "classical_text", "Tridosha theory: Pitta")]
    ),
    ConceptSeed(
        "DOSHA_KAPHA", "dosha", "active", None,
        [
            LabelSeed("sa", "Deva", "कफ", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kapha", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "श्लेष्मा", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Śleṣmā", "synonym", "classical_lexicon", 0),
            LabelSeed("hi", "Deva", "कफ दोष", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Kapha Dosha", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 1.57", "classical_text", "Tridosha theory: Kapha")]
    ),

    # ------------------------------------------------------------------------
    # 6. DOSHA EFFECT (2 active directional effect concepts)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "EFFECT_DECREASE", "dosha_effect", "active", None,
        [
            LabelSeed("sa", "Deva", "शमन / हर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śamana / Hara", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Shamana / Hara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "शामक (शांत करने वाला / घटाने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Pacifies / Decreases", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 1.62", "classical_text", "Dosha Shamana principle")]
    ),
    ConceptSeed(
        "EFFECT_INCREASE", "dosha_effect", "active", None,
        [
            LabelSeed("sa", "Deva", "प्रकोपक / वर्धक", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Prakopaka / Vardhaka", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kopana / Vriddhi", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "प्रकोपक (बढ़ाने वाला / कुपित करने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Aggravates / Increases", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 1.62", "classical_text", "Dosha Prakopa principle")]
    ),

    # ------------------------------------------------------------------------
    # 7. PRABHAVA (6 active core classical concepts)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "PRABHAVA_VISHAGHNA", "prabhava", "active", None,
        [
            LabelSeed("sa", "Deva", "विषघ्न", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Viṣaghna", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vishaghna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "विषघ्न (विषनाशक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Antitoxic / Anti-poisonous Action", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 26.70", "classical_text", "Classical Prabhava: Vishaghna action")]
    ),
    ConceptSeed(
        "PRABHAVA_MEDHYA", "prabhava", "active", None,
        [
            LabelSeed("sa", "Deva", "मेध्य", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Medhya", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "मेध्य (बुद्धिवर्धक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Intellect-Promoting / Nootropic Action", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 1.3", "classical_text", "Medhya Rasayana Prabhava")]
    ),
    ConceptSeed(
        "PRABHAVA_HRIDYA", "prabhava", "active", None,
        [
            LabelSeed("sa", "Deva", "हृद्य", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Hṛdya", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Hridya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "हृद्य (हृदय पोषक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Cardioprotective / Cardiac Tonic Action", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.10", "classical_text", "Hridya Prabhava")]
    ),
    ConceptSeed(
        "PRABHAVA_RASAYANA", "prabhava", "active", None,
        [
            LabelSeed("sa", "Deva", "रसायन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rasāyana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rasayana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "रसायन (कायाकल्प / पुनर्जीवन)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Rejuvenative Action", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 1.1", "classical_text", "Rasayana Prabhava")]
    ),
    ConceptSeed(
        "PRABHAVA_VAMAKA", "prabhava", "active", None,
        [
            LabelSeed("sa", "Deva", "वामक", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vāmaka", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vamaka", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "वामक (वमनकारी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Emetic Action", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Kalpasthāna 1.5", "classical_text", "Vamaka Prabhava")]
    ),
    ConceptSeed(
        "PRABHAVA_VIRECHAKA", "prabhava", "active", None,
        [
            LabelSeed("sa", "Deva", "विरेचक", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Virecaka", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Virechaka", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "विरेचक (दस्तावर)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Purgative Action", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Kalpasthāna 1.6", "classical_text", "Virechaka Prabhava")]
    ),

    # ------------------------------------------------------------------------
    # 8. KARMA (22 active canonical therapeutic actions)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "KARMA_DEEPANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "दीपन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Dīpana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Deepana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "दीपन (अग्निदीपक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Appetizer / Digestive Fire Stimulant", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.1", "classical_text", "Definition of Deepana karma")]
    ),
    ConceptSeed(
        "KARMA_PACHANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "पाचन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pācana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pachana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "पाचन (आमपाचक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Digestant / Ama Metabolizer", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.1", "classical_text", "Definition of Pachana karma")]
    ),
    ConceptSeed(
        "KARMA_ANULOMANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "अनुलोमन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Anulomana", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "अनुलोमन (वात अनुलोमक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Carminative / Peristalsis Normalizer", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.4", "classical_text", "Definition of Anulomana karma")]
    ),
    ConceptSeed(
        "KARMA_GRAHI", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "ग्राही", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Grāhī", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Grahi", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "ग्राही (मल संग्राहक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Bowel Binder / Fluid Absorber", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.8", "classical_text", "Definition of Grahi karma")]
    ),
    ConceptSeed(
        "KARMA_STAMBHANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "स्तम्भन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Stambhana", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "स्तम्भन (रोकने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Astringent / Hemostatic / Secretion Retarder", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.9", "classical_text", "Definition of Stambhana karma")]
    ),
    ConceptSeed(
        "KARMA_RECHANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "रेचन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Recana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rechana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "रेचन (दस्त कराने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Purgative / Evacuant", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.7", "classical_text", "Definition of Rechana karma")]
    ),
    ConceptSeed(
        "KARMA_BHEDANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "भेदन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Bhedana", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "भेदन (मल भेदक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Drastic Purgative / Fecal Mass Breaker", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.6", "classical_text", "Definition of Bhedana karma")]
    ),
    ConceptSeed(
        "KARMA_RASAYANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "रसायन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rasāyana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Rasayana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "रसायन कर्म", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Rejuvenative / Vitality Enhancer", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 1.1", "classical_text", "Rasayana karma")]
    ),
    ConceptSeed(
        "KARMA_VAJIKARANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "वाजीकरण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vājīkaraṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vajikarana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "वाजीकरण (वीर्यवर्धक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Aphrodisiac / Virility Enhancer", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 2.1", "classical_text", "Vajikarana karma")]
    ),
    ConceptSeed(
        "KARMA_BALYA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "बल्य", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Balya", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "बल्य (बलवर्धक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Strength Promoter / Tonic", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.7", "classical_text", "Balya mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_BRIMHANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "बृंहण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Bṛṃhaṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Brimhana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "बृंहण (पुष्टिकारक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Nourishing / Body Mass Promoter", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 22.10", "classical_text", "Shadvidhopakrama: Brimhana")]
    ),
    ConceptSeed(
        "KARMA_LANGHANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "लङ्घन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Laṅghana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Langhana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "लङ्घन (लघुताकारक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Lightening / Depleting", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 22.9", "classical_text", "Shadvidhopakrama: Langhana")]
    ),
    ConceptSeed(
        "KARMA_LEKHANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "लेखन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Lekhana", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "लेखन (मेदनाशक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Scraping / Lipid-Reducing", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.11", "classical_text", "Definition of Lekhana karma")]
    ),
    ConceptSeed(
        "KARMA_CHEDANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "छेदन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Chedana", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "छेदन (कफ विदारक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Expectorant / Adherent Dosha Detachment", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.10", "classical_text", "Definition of Chedana karma")]
    ),
    ConceptSeed(
        "KARMA_SHOTHAHARA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "शोथहर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śothahara", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Shothahara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "शोथहर (सूजन नाशक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Anti-inflammatory / Edema-Reducing", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.16", "classical_text", "Shothahara mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_JVARAGHNA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "ज्वरघ्न", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Jvaraghna", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "ज्वरघ्न (बुखार नाशक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Antipyretic / Febrifuge", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.39", "classical_text", "Jvaraghna mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_KASAHARA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "कासहर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kāsahara", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kasahara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कासहर (खांसी नाशक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Antitussive / Cough-Relieving", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.36", "classical_text", "Kasahara mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_KRIMIGHNA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "कृमिघ्न", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kṛmighna", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Krimighna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कृमिघ्न (कीड़े मारने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Anthelmintic / Anti-parasitic", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.15", "classical_text", "Krimighna mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_KUSHTHAGHNA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "कुष्ठघ्न", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kuṣṭhaghna", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kushthaghna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कुष्ठघ्न (त्वचारोग नाशक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dermatological Therapeutic / Skin-Alleviating", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.13", "classical_text", "Kushthaghna mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_VEDANASTHAPANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "वेदनास्थापन", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vedanāsthāpana", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vedanasthapana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "वेदनास्थापन (दर्द निवारक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Analgesic / Pain-Relieving", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.47", "classical_text", "Vedanasthapana mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_SANDHANIYA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "सन्धानीय", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sandhānīya", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sandhaniya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "सन्धानीय (जोड़ने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Healing / Tissue Union Promoter", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Sūtrasthāna 4.5", "classical_text", "Sandhaniya mahakashaya")]
    ),
    ConceptSeed(
        "KARMA_VRANAROPANA", "karma", "active", None,
        [
            LabelSeed("sa", "Deva", "व्रणरोपण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vraṇaropaṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vranaropana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "व्रणरोपण (घाव भरने वाला)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Wound-Healing / Vulnerary", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 37.15", "classical_text", "Vranaropana karma")]
    ),

    # ------------------------------------------------------------------------
    # 9. PLANT PART (16 active canonical morphological parts per API Part 1)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "PART_ROOT", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "मूल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mūla", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mula", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "जड़ (मूल)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Root", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_RHIZOME", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "प्रकन्द", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Prakanda", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "कन्द", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Kanda", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "प्रकन्द", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Rhizome", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_STEM", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "काण्ड", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kāṇḍa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kanda-Shakha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "तना (काण्ड)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Stem", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_STEM_BARK", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "काण्ड-त्वक्", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kāṇḍa-Tvak", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "त्वक्", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Tvak", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "छाल (काण्ड-त्वक)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Stem Bark", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_ROOT_BARK", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "मूल-त्वक्", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mūla-Tvak", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mula-Tvak", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "मूल छाल", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Root Bark", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_HEARTWOOD", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "सार", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sāra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Sara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "सारकाष्ठ (सार)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Heartwood", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_LEAF", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "पत्र", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Patra", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "पत्ती (पत्र)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Leaf", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_FLOWER", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "पुष्प", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Puṣpa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pushpa", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "फूल (पुष्प)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Flower", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_FRUIT", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "फल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Phala", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "फल", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Fruit", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_SEED", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "बीज", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Bīja", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Bija", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "बीज", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Seed", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_WHOLE_PLANT", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "पञ्चाङ्ग", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pañcāṅga", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Panchanga", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "पंचांग (संपूर्ण पौधा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Whole Plant", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_EXUDATE_RESIN", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "निर्यास", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Niryāsa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Niryasa", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "निर्यास (गोंद / राल)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Exudate / Resin", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_LATEX", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "क्षीर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kṣīra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kshira", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "क्षीर (दूध)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Latex", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_BULB", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "शल्क-कन्द", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śalka-Kanda", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Shalka-Kanda", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "शल्क-कन्द (गांठ)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Bulb", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_FRUIT_RIND", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "फल-त्वक्", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Phala-Tvak", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "फल छिलका", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Fruit Rind / Pericarp", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),
    ConceptSeed(
        "PART_ARIL", "plant_part", "active", None,
        [
            LabelSeed("sa", "Deva", "जातीपत्री", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Jātīpatrī", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Jatipatri", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "जावित्री", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Aril / Mace", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Pharmacopoeia of India (API) Part 1", "classical_text", "Official plant part monograph")]
    ),

    # ------------------------------------------------------------------------
    # 10. PREPARATION FORM (15 active canonical dosage forms per AFI / Sharngadhara)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "PREP_SWARASA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "स्वरस", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Svarasa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Swarasa", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "स्वरस (ताजा रस)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Fresh Expressed Juice", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 1.1", "classical_text", "Panchavidha Kashaya kalpana: Swarasa")]
    ),
    ConceptSeed(
        "PREP_KALKA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "कल्क", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kalka", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "कल्क (पेस्ट)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Herbal Paste / Bolus", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 5.1", "classical_text", "Panchavidha Kashaya kalpana: Kalka")]
    ),
    ConceptSeed(
        "PREP_KWATHA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "क्वाथ", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kvātha", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "कषाय", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Kwatha", "synonym", "scholarly_reference", 0),
            LabelSeed("sa", "Latn", "Kashaya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "क्वाथ (काढ़ा)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Decoction", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 2.1", "classical_text", "Panchavidha Kashaya kalpana: Kwatha")]
    ),
    ConceptSeed(
        "PREP_HIMA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "हिम", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Hima", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "शीत-कषाय", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Shita-Kashaya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "हिम (शीत कषाय)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Cold Infusion", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 3.1", "classical_text", "Panchavidha Kashaya kalpana: Hima")]
    ),
    ConceptSeed(
        "PREP_PHANTA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "फाण्ट", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Phāṇṭa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Phanta", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "फाण्ट (उष्ण कषाय)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Hot Infusion", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 4.1", "classical_text", "Panchavidha Kashaya kalpana: Phanta")]
    ),
    ConceptSeed(
        "PREP_CHURNA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "चूर्ण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Cūrṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Churna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "चूर्ण (पाउडर)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Fine Pulverized Powder", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 6.1", "classical_text", "Churna kalpana")]
    ),
    ConceptSeed(
        "PREP_VATI", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "वटी", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vaṭī", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "गुटिका", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Vati", "synonym", "scholarly_reference", 0),
            LabelSeed("sa", "Latn", "Gutika", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "वटी (गोली)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Tablet / Pill", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 7.1", "classical_text", "Vati / Gutika kalpana")]
    ),
    ConceptSeed(
        "PREP_AVALEHA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "अवलेह", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Avaleha", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Deva", "लेह", "synonym", "classical_lexicon", 0),
            LabelSeed("sa", "Latn", "Lehya", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अवलेह (चाटने योग्य पेस्ट)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Herbal Jam / Confection / Electuary", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 8.1", "classical_text", "Avaleha kalpana")]
    ),
    ConceptSeed(
        "PREP_GHRITA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "घृत", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ghṛta", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ghrita", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "घृत (सिद्ध घी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Medicated Clarified Butter / Ghee", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 9.1", "classical_text", "Sneha kalpana: Ghrita")]
    ),
    ConceptSeed(
        "PREP_TAILA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "तैल", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Taila", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "तैल (सिद्ध तेल)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Medicated Oil", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 9.1", "classical_text", "Sneha kalpana: Taila")]
    ),
    ConceptSeed(
        "PREP_ASAVA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "आसव", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Āsava", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Asava", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "आसव (किण्वित आसव)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Naturally Fermented Infusion", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 10.1", "classical_text", "Sandhana kalpana: Asava")]
    ),
    ConceptSeed(
        "PREP_ARISHTA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "अरिष्ट", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ariṣṭa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Arishta", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अरिष्ट (किण्वित क्वाथ)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Naturally Fermented Decoction", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 10.1", "classical_text", "Sandhana kalpana: Arishta")]
    ),
    ConceptSeed(
        "PREP_BHASMA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "भस्म", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Bhasma", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "भस्म (शोधित राख)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Calcinated Ash Preparation", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Rasataraṅgiṇī / AFI Part 1", "classical_text", "Bhasma kalpana")]
    ),
    ConceptSeed(
        "PREP_LEPA", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "लेप", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Lepa", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "लेप (बाह्य लेप)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Medicated External Poultice / Paste", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Śārṅgadhara Saṃhitā, Uttara Khaṇḍa 11.1", "classical_text", "Lepa kalpana")]
    ),
    ConceptSeed(
        "PREP_GUGGULU", "preparation_form", "active", None,
        [
            LabelSeed("sa", "Deva", "गुग्गुलु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Guggulu", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "गुग्गुलु कल्प", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Guggulu Resinous Compound Formulation", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Ayurvedic Formulary of India (AFI) Part 1", "classical_text", "Guggulu kalpana")]
    ),

    # ------------------------------------------------------------------------
    # 11. INDICATION (24 active canonical clinical conditions)
    # ------------------------------------------------------------------------
    ConceptSeed(
        "IND_JVARA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "ज्वर", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Jvara", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "ज्वर (बुखार)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Fever / Pyrexia", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Nidānasthāna 1", "classical_text", "Jvara nidana and cikitsa")]
    ),
    ConceptSeed(
        "IND_KASA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "कास", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kāsa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kasa", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कास (खांसी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Cough / Bronchitis", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 18", "classical_text", "Kasa cikitsa")]
    ),
    ConceptSeed(
        "IND_SHWASA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "श्वास", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śvāsa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Shwasa", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "श्वास (दमा / श्वास कष्ट)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dyspnea / Asthma", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 17", "classical_text", "Shwasa cikitsa")]
    ),
    ConceptSeed(
        "IND_PRAMEHA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "प्रमेह", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Prameha", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "प्रमेह (मधुमेह आदि)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Urinary Disorders / Diabetes Mellitus", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Nidānasthāna 4", "classical_text", "Prameha nidana")]
    ),
    ConceptSeed(
        "IND_ARSHA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "अर्श", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Arśas", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Arsha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अर्श (बवासीर)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Hemorrhoids / Piles", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 14", "classical_text", "Arsha cikitsa")]
    ),
    ConceptSeed(
        "IND_ATISARA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "अतिसार", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Atisāra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Atisara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अतिसार (दस्त)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Diarrhea", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 19", "classical_text", "Atisara cikitsa")]
    ),
    ConceptSeed(
        "IND_GRAHANI", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "ग्रहणी", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Grahaṇī", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Grahani", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "ग्रहणी (संग्रहणी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Malabsorption Syndrome / IBS", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 15", "classical_text", "Grahani-dosha cikitsa")]
    ),
    ConceptSeed(
        "IND_KAMALA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "कामला", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kāmalā", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kamala", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कामला (पीलिया)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Jaundice / Hepatitis", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 16", "classical_text", "Pandu-Kamala cikitsa")]
    ),
    ConceptSeed(
        "IND_PANDU", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "पाण्डु", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pāṇḍu", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Pandu", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "पाण्डु (रक्तअल्पता)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Anemia", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 16", "classical_text", "Pandu-roga cikitsa")]
    ),
    ConceptSeed(
        "IND_KUSHTHA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "कुष्ठ", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kuṣṭha", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kushtha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कुष्ठ (त्वचा रोग)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dermatological Disorders / Leprosy", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 7", "classical_text", "Kushtha cikitsa")]
    ),
    ConceptSeed(
        "IND_SHOTHA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "शोथ", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Śotha", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Shotha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "शोथ (सूजन)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Edema / Inflammation", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 12", "classical_text", "Shotha cikitsa")]
    ),
    ConceptSeed(
        "IND_AMAVATA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "आमवात", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Āmavāta", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Amavata", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "आमवात (गठिया)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Rheumatoid Arthritis / Amavata", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Mādhava Nidāna 25", "classical_text", "Amavata roga lakshana")]
    ),
    ConceptSeed(
        "IND_VATARAKTA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "वातरक्त", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vātarakta", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vatarakta", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "वातरक्त (गठिया / यूरिक एसिड विकार)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Gout / Vatarakta", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 29", "classical_text", "Vatarakta cikitsa")]
    ),
    ConceptSeed(
        "IND_AMLAPITTA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "अम्लपित्त", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Amlapitta", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "अम्लपित्त (एसिडिटी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Hyperacidity / Acid Peptic Disorder", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Mādhava Nidāna 51", "classical_text", "Amlapitta roga")]
    ),
    ConceptSeed(
        "IND_KRIMI", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "कृमि", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Kṛmi", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Krimi", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "कृमि रोग (पेट के कीड़े)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Helminthiasis / Worm Infestation", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Vimānasthāna 7", "classical_text", "Krimi roga")]
    ),
    ConceptSeed(
        "IND_MUTRAKRICCHRA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "मूत्रकृच्छ्र", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mūtrakṛcchra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Mutrakricchra", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "मूत्रकृच्छ्र (पेशाब में जलन / रुकावट)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Dysuria / Painful Micturition", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 26", "classical_text", "Mutrakricchra cikitsa")]
    ),
    ConceptSeed(
        "IND_ASHMARI", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "अश्मरी", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Aśmarī", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Ashmari", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अश्मरी (पथरी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Urinary Calculi / Kidney Stones", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Nidānasthāna 3", "classical_text", "Ashmari nidana")]
    ),
    ConceptSeed(
        "IND_VRANA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "व्रण", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vraṇa", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Vrana", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "व्रण (घाव / अल्सर)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Ulcer / Wound", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Suśruta Saṃhitā, Sūtrasthāna 21", "classical_text", "Vrana lakshana")]
    ),
    ConceptSeed(
        "IND_DAHA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "दाह", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Dāha", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Daha", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "दाह (जलन)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Burning Sensation", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 24", "classical_text", "Daha cikitsa")]
    ),
    ConceptSeed(
        "IND_CHARDI", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "छर्दि", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Chardi", "transliteration", "classical_lexicon", 1),
            LabelSeed("hi", "Deva", "छर्दि (उल्टी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Vomiting / Emesis", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 20", "classical_text", "Chardi cikitsa")]
    ),
    ConceptSeed(
        "IND_TRISHNA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "तृष्णा", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Tṛṣṇā", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Trishna", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "तृष्णा (अत्यधिक प्यास)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Polydipsia / Excessive Thirst", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 22", "classical_text", "Trishna cikitsa")]
    ),
    ConceptSeed(
        "IND_HRIDROGA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "हृद्रोग", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Hṛdroga", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Hridroga", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "हृद्रोग (हृदय रोग)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Cardiac Disorders", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Cikitsāsthāna 26", "classical_text", "Hridroga cikitsa")]
    ),
    ConceptSeed(
        "IND_UNMADA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "उन्माद", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Unmāda", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Unmada", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "उन्माद (मानसिक विकार)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Psychosis / Mental Disorders", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Nidānasthāna 7", "classical_text", "Unmada nidana")]
    ),
    ConceptSeed(
        "IND_APASMARA", "indication", "active", None,
        [
            LabelSeed("sa", "Deva", "अपस्मार", "canonical_sanskrit", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Apasmāra", "transliteration", "classical_lexicon", 1),
            LabelSeed("sa", "Latn", "Apasmara", "synonym", "scholarly_reference", 0),
            LabelSeed("hi", "Deva", "अपस्मार (मिर्गी)", "vernacular_equivalent", "human_curated", 1),
            LabelSeed("en", "Latn", "Epilepsy / Convulsive Disorder", "scholarly_translation", "scholarly_reference", 1),
        ],
        [CitationSeed("Caraka Saṃhitā, Nidānasthāna 8", "classical_text", "Apasmara nidana")]
    ),
]


# ============================================================================
# 4. Catalog Invariant Validator & Enum Whitelists
# ============================================================================

VALID_CONCEPT_STATUSES = {"active", "provisional", "deprecated"}

VALID_LABEL_TYPES = {
    "canonical_sanskrit",
    "transliteration",
    "vernacular_equivalent",
    "scholarly_translation",
    "synonym",
    "deprecated_alias",
}

VALID_TRANSLATION_ORIGINS = {
    "classical_lexicon",
    "statutory_pharmacopoeia",
    "scholarly_reference",
    "human_curated",
    "machine_unverified",
}

VALID_CITATION_TYPES = {
    "classical_text",
    "statutory_pharmacopoeia",
    "academic_lexicon",
    "multilateral_standard",
    "source_document",
}

REQUIRED_PREFERRED_TUPLES = {("en", "Latn"), ("hi", "Deva"), ("sa", "Deva"), ("sa", "Latn")}


def _validate_iso_utc_timestamp(ts: str) -> None:
    """Validates that a timestamp is a non-empty ISO-8601 string in UTC."""
    if not isinstance(ts, str) or not ts.strip():
        raise ValueError(f"Timestamp must be a non-empty string; got {ts!r}")
    s = ts.strip()
    if not (s.endswith("Z") or s.endswith("+00:00")):
        raise ValueError(f"Timestamp must be in UTC (ending in 'Z' or '+00:00'); got {ts!r}")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
            raise ValueError("Not UTC")
    except Exception as e:
        raise ValueError(f"Invalid ISO UTC timestamp {ts!r}: {e}") from e


def validate_catalog_dataset(concepts: list[ConceptSeed]) -> None:
    """Validates full catalog integrity before database insertion.
    
    Invariants checked:
    1. Concept status and domain conform to accepted DDL enums.
    2. Concept code prefix matches concept domain via validate_concept_code_prefix.
    3. Concept code uniqueness within the dataset.
    4. Parent concept hierarchy: parent_concept_code exists, is in the same domain,
       is not self-referential, and forms no cycles.
    5. Intra-concept normalized label uniqueness: (language_code, script_code, normalized_label)
       is unique within each concept.
    6. Multilingual representation and Single-Preferred-Label Invariant (ADR Decision 9.2):
       Every concept has EXACTLY ONE preferred label (is_preferred=1) for each required tuple:
       ('en', 'Latn'), ('hi', 'Deva'), ('sa', 'Deva'), ('sa', 'Latn').
       Any additional (language_code, script_code) tuple has at most one preferred label.
    7. Enum whitelists: is_preferred in (0, 1), label_type in VALID_LABEL_TYPES,
       translation_origin in VALID_TRANSLATION_ORIGINS, citation_type in VALID_CITATION_TYPES.
    8. Citation coverage: Every concept has at least one valid citation with non-empty text.
    """
    seen_codes: set[str] = set()
    concept_map: dict[str, ConceptSeed] = {c.concept_code: c for c in concepts}
    
    for concept in concepts:
        if concept.status not in VALID_CONCEPT_STATUSES:
            raise ValueError(
                f"Invalid status {concept.status!r} for concept {concept.concept_code}. "
                f"Must be one of: {sorted(VALID_CONCEPT_STATUSES)}"
            )
        
        validate_concept_code_prefix(concept.concept_code, concept.concept_domain)
        
        if concept.concept_code in seen_codes:
            raise ValueError(f"Duplicate concept code in seed dataset: {concept.concept_code}")
        seen_codes.add(concept.concept_code)
        
        # Check parent hierarchy
        if concept.parent_concept_code is not None:
            if concept.parent_concept_code not in concept_map:
                raise ValueError(
                    f"Concept {concept.concept_code} references non-existent parent concept: {concept.parent_concept_code}"
                )
            if concept.parent_concept_code == concept.concept_code:
                raise ValueError(
                    f"Concept {concept.concept_code} cannot reference itself as parent"
                )
            parent = concept_map[concept.parent_concept_code]
            if parent.concept_domain != concept.concept_domain:
                raise ValueError(
                    f"Concept {concept.concept_code} in domain {concept.concept_domain!r} has parent "
                    f"{concept.parent_concept_code} in different domain {parent.concept_domain!r}"
                )
            # Cycle check
            visited = {concept.concept_code}
            curr = concept.parent_concept_code
            while curr is not None:
                if curr in visited:
                    raise ValueError(
                        f"Cycle detected in parent hierarchy for concept {concept.concept_code}: cycle at {curr}"
                    )
                visited.add(curr)
                curr = concept_map[curr].parent_concept_code
        
        # Track normalized labels and preferred counts
        seen_norm_labels: set[tuple[str, str, str]] = set()
        preferred_counts: dict[tuple[str, str], int] = {}
        
        for lbl in concept.labels:
            if lbl.is_preferred not in (0, 1):
                raise ValueError(f"Invalid is_preferred value {lbl.is_preferred!r} for label {lbl.label_text!r} in {concept.concept_code}")
            if lbl.label_type not in VALID_LABEL_TYPES:
                raise ValueError(f"Invalid label_type {lbl.label_type!r} for label {lbl.label_text!r} in {concept.concept_code}")
            if lbl.translation_origin not in VALID_TRANSLATION_ORIGINS:
                raise ValueError(f"Invalid translation_origin {lbl.translation_origin!r} for label {lbl.label_text!r} in {concept.concept_code}")
            
            norm = lbl.get_normalized()
            norm_key = (lbl.language_code, lbl.script_code, norm)
            if norm_key in seen_norm_labels:
                raise ValueError(
                    f"Duplicate normalized label {norm!r} for ({lbl.language_code}, {lbl.script_code}) "
                    f"in concept {concept.concept_code}"
                )
            seen_norm_labels.add(norm_key)
            
            tuple_key = (lbl.language_code, lbl.script_code)
            if lbl.is_preferred == 1:
                preferred_counts[tuple_key] = preferred_counts.get(tuple_key, 0) + 1
                if preferred_counts[tuple_key] > 1:
                    raise ValueError(
                        f"Single-preferred-label invariant violated for concept {concept.concept_code} "
                        f"on tuple {tuple_key}: found {preferred_counts[tuple_key]} preferred labels."
                    )
        
        # Check required preferred tuples: each MUST have count == 1
        for req in REQUIRED_PREFERRED_TUPLES:
            count = preferred_counts.get(req, 0)
            if count != 1:
                raise ValueError(
                    f"Concept {concept.concept_code} missing required preferred label for "
                    f"({req[0]!r}, {req[1]!r}) (found {count} preferred labels)."
                )
        
        # Check citation coverage
        if not concept.citations:
            raise ValueError(f"Concept {concept.concept_code} has no citations.")
        for cit in concept.citations:
            if cit.citation_type not in VALID_CITATION_TYPES:
                raise ValueError(f"Invalid citation_type {cit.citation_type!r} for concept {concept.concept_code}")
            if not isinstance(cit.authority_citation, str) or not cit.authority_citation.strip():
                raise ValueError(f"Empty authority citation for concept {concept.concept_code}")


# ============================================================================
# 5. Catalog Seeder
# ============================================================================

def seed_canonical_concept_catalog(
    conn: sqlite3.Connection,
    now: str | None = None,
    dataset: list[ConceptSeed] | None = None,
) -> dict[str, int]:
    """Seeds the canonical Dravyaguna concept catalog idempotently.
    
    Args:
        conn: An open SQLite connection with Stage C schema (v3) initialized.
        now: Optional ISO-8601 UTC timestamp string.
        dataset: Optional list of ConceptSeed objects (defaults to CANONICAL_CONCEPTS).
        
    Returns:
        dict[str, int]: Counts of newly inserted records:
            {'concepts': int, 'labels': int, 'sources': int}
            If catalog was already seeded, returns {'concepts': 0, 'labels': 0, 'sources': 0}.
    """
    require_stage_c_schema_v3(conn)
    
    if dataset is None:
        dataset = CANONICAL_CONCEPTS
    
    validate_catalog_dataset(dataset)
    
    if now is None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        _validate_iso_utc_timestamp(now)
    
    fk_on = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    if fk_on != 1:
        if conn.in_transaction:
            raise RuntimeError("PRAGMA foreign_keys must be ON before starting a transaction")
        conn.execute("PRAGMA foreign_keys = ON;")
    
    # Track counts
    inserted_concepts = 0
    inserted_labels = 0
    inserted_sources = 0
    
    conn.execute("SAVEPOINT wp1_seed;")
    try:
        # Pass 1: Insert concepts
        concept_id_map: dict[str, int] = {}
        
        for c in dataset:
            cur = conn.execute(
                "SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = ?",
                (c.concept_code,),
            )
            row = cur.fetchone()
            if row is not None:
                concept_id_map[c.concept_code] = row[0]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO dravyaguna_concepts (
                        concept_code, concept_domain, parent_concept_id, status, created_at
                    ) VALUES (?, ?, NULL, ?, ?)
                    """,
                    (c.concept_code, c.concept_domain, c.status, now),
                )
                cid = cur.lastrowid
                concept_id_map[c.concept_code] = cid
                inserted_concepts += 1
        
        # Pass 2: Set parent_concept_id for concepts with parent_concept_code
        for c in dataset:
            if c.parent_concept_code is not None:
                cid = concept_id_map[c.concept_code]
                parent_cid = concept_id_map[c.parent_concept_code]
                conn.execute(
                    """
                    UPDATE dravyaguna_concepts
                    SET parent_concept_id = ?
                    WHERE concept_id = ? AND (parent_concept_id IS NULL OR parent_concept_id != ?)
                    """,
                    (parent_cid, cid, parent_cid),
                )
        
        # Pass 3: Insert labels
        # All seeded labels start as 'unreviewed' with verified_by=NULL, verified_at=NULL
        for c in dataset:
            cid = concept_id_map[c.concept_code]
            for lbl in c.labels:
                norm = lbl.get_normalized()
                
                # Check for database-level single-preferred-label conflict
                if lbl.is_preferred == 1:
                    cur_pref = conn.execute(
                        """
                        SELECT concept_label_id, normalized_label FROM concept_labels
                        WHERE concept_id = ? AND language_code = ? AND script_code = ? AND is_preferred = 1
                        """,
                        (cid, lbl.language_code, lbl.script_code),
                    )
                    row_pref = cur_pref.fetchone()
                    if row_pref is not None and row_pref[1] != norm:
                        raise ValueError(
                            f"Single-preferred-label database conflict for concept {c.concept_code} ({cid}): "
                            f"already has preferred label id={row_pref[0]} ({row_pref[1]!r}) for "
                            f"({lbl.language_code}, {lbl.script_code}), cannot insert another preferred label {lbl.label_text!r}."
                        )
                
                cur = conn.execute(
                    """
                    SELECT concept_label_id FROM concept_labels
                    WHERE concept_id = ? AND language_code = ? AND script_code = ? AND normalized_label = ?
                    """,
                    (cid, lbl.language_code, lbl.script_code, norm),
                )
                row = cur.fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO concept_labels (
                            concept_id, language_code, script_code, label_text,
                            normalized_label, label_type, translation_origin,
                            verification_status, reviewed_by, reviewed_at,
                            verified_by, verified_at, reviewer_notes, is_preferred, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unreviewed', NULL, NULL, NULL, NULL, NULL, ?, ?)
                        """,
                        (
                            cid, lbl.language_code, lbl.script_code, lbl.label_text,
                            norm, lbl.label_type, lbl.translation_origin,
                            lbl.is_preferred, now
                        ),
                    )
                    inserted_labels += 1
        
        # Pass 4: Insert citations in concept_label_sources
        # We attach each citation to the matching preferred label for the concept
        for c in dataset:
            cid = concept_id_map[c.concept_code]
            for cit in c.citations:
                cur = conn.execute(
                    """
                    SELECT concept_label_id FROM concept_labels
                    WHERE concept_id = ? AND language_code = ? AND script_code = ? AND is_preferred = 1
                    ORDER BY concept_label_id ASC
                    LIMIT 1
                    """,
                    (cid, cit.target_language, cit.target_script),
                )
                row = cur.fetchone()
                if row is None:
                    cur = conn.execute(
                        "SELECT concept_label_id FROM concept_labels WHERE concept_id = ? ORDER BY is_preferred DESC, concept_label_id ASC LIMIT 1",
                        (cid,),
                    )
                    row = cur.fetchone()
                
                if row is not None:
                    label_id = row[0]
                    cur_check = conn.execute(
                        """
                        SELECT label_source_id FROM concept_label_sources
                        WHERE concept_label_id = ? AND authority_citation = ?
                        """,
                        (label_id, cit.authority_citation),
                    )
                    if cur_check.fetchone() is None:
                        conn.execute(
                            """
                            INSERT INTO concept_label_sources (
                                concept_label_id, source_id, authority_citation,
                                citation_type, verified_by, verified_at,
                                citation_notes, created_at
                            ) VALUES (?, NULL, ?, ?, NULL, NULL, ?, ?)
                            """,
                            (label_id, cit.authority_citation, cit.citation_type, cit.citation_notes, now),
                        )
                        inserted_sources += 1
        
        conn.execute("RELEASE SAVEPOINT wp1_seed;")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT wp1_seed;")
        conn.execute("RELEASE SAVEPOINT wp1_seed;")
        raise
    
    return {
        "concepts": inserted_concepts,
        "labels": inserted_labels,
        "sources": inserted_sources,
    }


# ============================================================================
# 6. Label Resolution Helpers (ADR Decision 3)
# ============================================================================

def resolve_concept_display_label(
    conn: sqlite3.Connection,
    concept_id: int,
    language: str = "en",
    allow_provisional: bool = False,
) -> dict[str, Any] | None:
    """Resolves the canonical display label for a concept following ADR Decision 3.
    
    Rules:
    1. Concept status check: If concept is not found, or is 'deprecated',
       or is 'provisional' when allow_provisional=False, returns None.
       Note: 'deprecated' concepts are strictly quarantined even if allow_provisional=True.
    2. Inter-language priority order:
       - language='hi': hi (Deva) -> en (Latn) -> sa (Deva) -> sa (Latn)
       - language='en': en (Latn) -> hi (Deva) -> sa (Deva) -> sa (Latn)
    3. Intra-language verification rank:
       - verified (0) > reviewed (1) > unreviewed (2)
       - is_preferred DESC (1 before 0)
       - concept_label_id ASC
    4. Exclusion of disputed/rejected:
       - Labels with verification_status IN ('disputed', 'rejected') are excluded.
    5. Fallback transparency:
       - If no eligible label exists across all ranks, falls back to concept_code
         with display_label_status = 'unreviewed' and is_fallback = True.
    """
    require_stage_c_schema_v3(conn)
    cur = conn.execute(
        "SELECT concept_code, status FROM dravyaguna_concepts WHERE concept_id = ?",
        (concept_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    
    concept_code, status = row[0], row[1]
    
    # Deprecated concepts are strictly quarantined
    if status == "deprecated":
        return None
    
    # Provisional concepts require explicit allow_provisional
    if status == "provisional" and not allow_provisional:
        return None
    
    # Priority tuples
    if language == "hi":
        t0, t1, t2, t3 = ("hi", "Deva"), ("en", "Latn"), ("sa", "Deva"), ("sa", "Latn")
    else:
        t0, t1, t2, t3 = ("en", "Latn"), ("hi", "Deva"), ("sa", "Deva"), ("sa", "Latn")
    
    query = """
    SELECT 
        concept_label_id,
        concept_id,
        language_code,
        script_code,
        label_text,
        normalized_label,
        label_type,
        translation_origin,
        verification_status,
        is_preferred,
        CASE 
            WHEN language_code = ? AND script_code = ? THEN 0
            WHEN language_code = ? AND script_code = ? THEN 1
            WHEN language_code = ? AND script_code = ? THEN 2
            WHEN language_code = ? AND script_code = ? THEN 3
            ELSE 4
        END AS lang_tier,
        CASE verification_status
            WHEN 'verified' THEN 0
            WHEN 'reviewed' THEN 1
            WHEN 'unreviewed' THEN 2
            ELSE 3
        END AS verif_tier
    FROM concept_labels
    WHERE concept_id = ?
      AND verification_status NOT IN ('disputed', 'rejected')
    ORDER BY 
        lang_tier ASC,
        verif_tier ASC,
        is_preferred DESC,
        concept_label_id ASC
    LIMIT 1;
    """
    
    cur = conn.execute(
        query,
        (
            t0[0], t0[1],
            t1[0], t1[1],
            t2[0], t2[1],
            t3[0], t3[1],
            concept_id,
        ),
    )
    result = cur.fetchone()
    
    if result is not None:
        return {
            "concept_label_id": result[0],
            "concept_id": result[1],
            "language_code": result[2],
            "script_code": result[3],
            "label_text": result[4],
            "display_label": result[4],
            "normalized_label": result[5],
            "label_type": result[6],
            "translation_origin": result[7],
            "verification_status": result[8],
            "display_label_status": result[8],
            "is_preferred": result[9],
            "is_fallback": False,
        }
    
    # Fallback to concept_code with unreviewed status
    return {
        "concept_label_id": None,
        "concept_id": concept_id,
        "language_code": None,
        "script_code": None,
        "label_text": concept_code,
        "display_label": concept_code,
        "normalized_label": normalize_label(concept_code),
        "label_type": "fallback_concept_code",
        "translation_origin": None,
        "verification_status": "unreviewed",
        "display_label_status": "unreviewed",
        "is_preferred": 0,
        "is_fallback": True,
    }


def resolve_concept_sanskrit_references(
    conn: sqlite3.Connection,
    concept_id: int,
    allow_provisional: bool = False,
) -> dict[str, str | None]:
    """Resolves canonical Sanskrit references (Devanagari and IAST) for a concept.
    
    Rules per ADR Decision 3.C & 3.D:
    1. Concept status check: If concept is not found, or is 'deprecated',
       or is 'provisional' when allow_provisional=False, returns both None.
    2. Queries concept_labels for language_code = 'sa' and verification_status NOT IN ('disputed', 'rejected').
    3. Ranks candidate labels by:
       - verif_tier: verified (0) > reviewed (1) > unreviewed (2)
       - is_preferred DESC (1 before 0)
       - concept_label_id ASC
    4. Returns best Devanagari label as 'canonical_sanskrit_deva' and best Latin (IAST) label
       as 'canonical_sanskrit_iast'.
    """
    require_stage_c_schema_v3(conn)
    cur = conn.execute(
        "SELECT status FROM dravyaguna_concepts WHERE concept_id = ?",
        (concept_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {"canonical_sanskrit_deva": None, "canonical_sanskrit_iast": None}
    
    status = row[0]
    if status == "deprecated":
        return {"canonical_sanskrit_deva": None, "canonical_sanskrit_iast": None}
    if status == "provisional" and not allow_provisional:
        return {"canonical_sanskrit_deva": None, "canonical_sanskrit_iast": None}
    
    query = """
    SELECT 
        script_code,
        label_text,
        CASE verification_status
            WHEN 'verified' THEN 0
            WHEN 'reviewed' THEN 1
            WHEN 'unreviewed' THEN 2
            ELSE 3
        END AS verif_tier,
        is_preferred,
        concept_label_id
    FROM concept_labels
    WHERE concept_id = ?
      AND language_code = 'sa'
      AND verification_status NOT IN ('disputed', 'rejected')
    ORDER BY 
        verif_tier ASC,
        is_preferred DESC,
        concept_label_id ASC;
    """
    
    deva: str | None = None
    iast: str | None = None
    
    cur = conn.execute(query, (concept_id,))
    for row in cur.fetchall():
        script, text = row[0], row[1]
        if script == "Deva" and deva is None:
            deva = text
        elif script == "Latn" and iast is None:
            iast = text
        if deva is not None and iast is not None:
            break
            
    return {
        "canonical_sanskrit_deva": deva,
        "canonical_sanskrit_iast": iast,
    }
