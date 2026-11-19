# Multilingual Illness Glossary & Resolution Engine (`src/herbal_almanac/illness_glossary.py`)

## 1. Purpose and Overview

The `illness_glossary.py` module provides an in-memory, fault-tolerant translation and resolution service for Ayurvedic illness terms (clinical indications). It decouples multilingual presentation from the underlying SQLite database schema, enabling rich localized terminology in the Web GUI and REST APIs across 15 Indian languages without mutating stored records or requiring schema migrations.

The module operates over a packaged UTF-8 glossary (`src/herbal_almanac/data/illness_glossary.csv`, 227 conditions, 16 language columns) generated via AI assistance (Gemini Deep Research). To preserve clinical and epistemic safety, all CSV-derived translations are strictly marked `origin="machine_generated"` and `verification="unverified"`, while curated Stage C scholarly catalog concepts (`IND_*` indications in `concept_catalog.py`) take priority on conflict for English, Hindi, and Sanskrit.

## 2. Supported Languages

The glossary supports 15 official Indian languages, represented by ISO 639-1 / 639-2 codes:

| Code | English Name | Native Script | Direction |
| :--- | :--- | :--- | :--- |
| `en` | English | English | LTR |
| `hi` | Hindi | हिन्दी | LTR |
| `sa` | Sanskrit | संस्कृतम् | LTR |
| `as` | Assamese | অসমীয়া | LTR |
| `bn` | Bengali | বাংলা | LTR |
| `gu` | Gujarati | ગુજરાતી | LTR |
| `kn` | Kannada | ಕನ್ನಡ | LTR |
| `ml` | Malayalam | മലയാളം | LTR |
| `mr` | Marathi | मराठी | LTR |
| `ne` | Nepali | नेपाली | LTR |
| `or` | Odia | ଓଡ଼ିଆ | LTR |
| `pa` | Punjabi | ਪੰਜਾਬੀ | LTR |
| `ta` | Tamil | தமிழ் | LTR |
| `te` | Telugu | తెలుగు | LTR |
| `ur` | Urdu | اردو | RTL |

## 3. Inputs, Data Structures & API

### Core Data Structures
- `LanguageLabel`: A string subclass representing a localized label for a language. Exposes attributes `language`, `script_name`, `label_text`, `origin`, and `verification`.
- `ResolvedIllness`: A dictionary/object subclass representing a resolved illness entity. Contains:
  - `english` (`str`): Primary English condition name.
  - `original_term` (`str`): Scraped transliteration as recorded in the source/database.
  - `key` (`str`): Normalized lookup key.
  - `labels` (`dict[str, LanguageLabel]`): Localized labels keyed by language code.
  - `matched` (`bool`): `True` if matched against glossary or Stage C catalog; `False` if fallback.
  - `origin` (`str`): `"machine_generated"` (CSV), `"catalog"` (Stage C concept catalog), or `"fallback"`.
  - `verification` (`str`): `"unverified"` or `"curated"`.
  - `concept_id` (`str | None`): Stage C concept identifier (e.g., `IND_JVARA`) if mapped.
  - `kind` (`str`): Entity classification (`"disease"`, `"procedure"`, or `"non-disease concept"`).
  - `note` (`str | None`): Descriptive note (e.g. `"translation not available"`).

### Core Functions
- `load_glossary() -> dict[str, dict[str, str]]`: Loads and caches the packaged CSV from package data via `importlib.resources`.
- `tolerant_illness_key(term: str) -> str`: Normalizes raw transliterated terms with phonetic fault tolerance.
- `resolve_illness(term: str) -> ResolvedIllness`: Resolves a scraped or user-supplied term to its multilingual representation.
- `search_glossary(query: str, limit: int = 50) -> list[ResolvedIllness]`: Searches across English names, synonyms, and all 15 native scripts.
- `get_catalog_csv_conflicts() -> list[dict]`: Audits and returns discrepancies between Stage C catalog labels and CSV machine translations.

## 4. Normalization and Resolution Flow

```text
[Raw Scraped Term] (e.g. "AdhmAnam", "KAsa", "jvaraH", "ArtavadoSaH/ArtavaduSTiH/rajodoSaH")
        │
        ▼
tolerant_illness_key()
  ├── Strip Sanskrit visarga (-H, -h) & case / diacritics
  ├── Normalize phonetic variants (w -> v, sh/z -> s, ch/chh/cch -> c)
  └── Deduplicate double consonants (kk -> k, tt -> t)
        │
        ├───────────────────────────────────────────┐
        ▼                                           ▼
[Single Key Lookup]                         [Compound Slash Split]
  Matches exact or normalized row?            Splits on '/' and resolves
        │                                     individual parts
        ▼                                           │
[Stage C Concept Catalog Check] ◄───────────────────┘
  Matches curated indication (e.g. IND_KASA, IND_JVARA)?
        ├── YES: Override en, hi, sa with curated catalog labels
        │        Inherit regional Indic scripts (bn, ta, te, etc.) from CSV
        │        Set origin="catalog", verification="curated"
        └── NO:  Use CSV translations
                 Set origin="machine_generated", verification="unverified"
        │
        ▼
[Entity Kind Classification]
  Tag procedures (yonipuran) or non-disease concepts (garbhanirodha, medhya, rasayana)
        │
        ▼
[Return ResolvedIllness]
  (If completely unmatched: return fallback with readable English & note="translation not available")
```

## 5. Coverage Audit Tool (`scripts/illness_coverage.py`)

A standalone CLI script audits the coverage of any SQLite database against the glossary:

```bash
python scripts/illness_coverage.py --database data/inspection.db
```

### Features:
- Reports total illness rows, distinct normalized terms, resolved count, and coverage percentage.
- Lists unresolved illness terms with their linked herb counts.
- Flags sensitive procedures and non-disease concepts.
- `--conflicts` flag: Audits and prints discrepancies where curated Stage C catalog labels differ from CSV translations.

### Verified Coverage Baseline:
- `data/inspection.db`: 28 distinct illnesses &rarr; **28/28 resolved (100.0%)**, 0 unresolved.
- `data/demo.db`: 15 distinct illnesses &rarr; **13/15 resolved (86.7%)**, 2 unresolved (manual curations "Chronic Fatigue" and "Digestive Weakness").
- Catalog vs. CSV conflicts: 39 discrepancies documented transparently.

## 6. Verification and Test Suite

The module is verified offline by `tests/test_illness_glossary.py` and `tests/test_packaging_and_guards.py`:
- **CSV Data Integrity:** Verifies 227 rows, 16 non-empty columns, UTF-8 encoding, and valid language scripts.
- **Phonetic Tolerance:** Verifies resolution across capitalization variants, visargas, and orthographic substitutions.
- **Slash Compound Resolution:** Verifies compound terms resolve to both composite and individual condition parts.
- **Scholarly Precedence:** Verifies curated Stage C catalog labels supersede CSV translations for English, Hindi, and Sanskrit.
- **Graceful Fallback:** Verifies unknown terms return readable transliterations with `matched=False` without raising errors.
- **Multilingual Search:** Verifies cross-script querying in Devanagari, Bengali, Tamil, etc.
- **Wheel Bundling:** Verifies `src/herbal_almanac/data/illness_glossary.csv` is included in built `.whl` archives.
