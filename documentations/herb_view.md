# Herb Detail View-Model Layer (`herb_view.py`)

## 1. Purpose

`src/herbal_almanac/herb_view.py` is a presentation-layer utility module. It transforms herb data returned by the repository/database layer into structures that are easier for the web templates to display.

Its responsibilities include:

- Removing duplicate property rows for presentation without deleting source claims.
- Grouping Dravyaguna properties into classical domains.
- Summarizing agreement or disagreement among Virya claims.
- Producing a three-Dosha display model.
- Converting legacy `herb_attributes` rows into structured sections.
- Formatting botanical family names and retrieval timestamps.

The module is deliberately independent of SQLite. It receives Python values and returns new presentation structures; it does not query or modify the database.

## 2. Where It Fits in the Architecture

The main caller is `web_app.py`, particularly the `/herbs/{herb_id}` detail route.

The flow is:

1. `database_operator.py` retrieves the herb, legacy attributes, and Dosha data.
2. `repository_api.py` supplies normalized Stage C semantic data when schema version 3 is available.
3. `herb_view.py` prepares that data for presentation.
4. `web_app.py` passes the prepared structures to `herb_detail_semantic.html`.

This separation keeps SQL and repository logic out of the presentation transformation layer.

## 3. Imports and Dependencies

### Standard-library imports

| Import | Use |
|---|---|
| `re` | Devanagari detection and timestamp fallback parsing |
| `datetime` | Parsing ISO-8601 retrieval timestamps |
| `typing.Any` | Flexible dictionary/list type annotations |

There are no imports from other Herbal Almanac modules. The module is self-contained apart from its input data contracts.

## 4. Constants

### `DEVANAGARI_REGEX`

A compiled regular expression matching characters in the Devanagari Unicode range (`U+0900`–`U+097F`). It is used to classify attribute subfields as Hindi/Devanagari variants.

### `FIXED_DOMAIN_ORDER`

Defines the preferred Dravyaguna display order:

1. `rasa`
2. `guna`
3. `virya`
4. `vipaka`
5. `prabhava`
6. `karma`

### `VERNACULAR_LANG_CODES`

Maps language names found in legacy vernacular attributes to ISO 639-1 codes. Both `odia` and `oriya` map to `or`.

## 5. Functions

### 5.1 `clean_family(value: str | None) -> str`

Removes repeated entries from a comma-separated botanical family string.

**Logic:**

1. Returns `"Not recorded"` for an empty or missing value.
2. Splits the string on commas.
3. Trims whitespace and removes empty entries.
4. Uses insertion-order deduplication.
5. Joins the remaining family names.

Example:

```python
clean_family("Acanthaceae, Acanthaceae")
# "Acanthaceae"
```

It does not validate botanical taxonomy; it only removes repeated display text.

### 5.2 `format_retrieved(iso_ts: str | None) -> str`

Converts an ISO-8601 timestamp into a readable date such as `19 Nov 2026`.

**Logic:**

1. Returns `"Not recorded"` if the input is empty.
2. Trims whitespace.
3. Replaces a trailing `Z` representation with `+00:00` for parsing.
4. Uses `datetime.fromisoformat()`.
5. If parsing fails, attempts to extract a `YYYY-MM-DD` prefix with a regular expression.
6. If that fallback also fails, returns the original cleaned string.

The function formats the date; it does not convert the timestamp into a different timezone.

### 5.3 `dedupe_properties(properties: list[dict[str, Any]] | None) -> list[dict[str, Any]]`

Combines equivalent normalized property records for display.

The grouping key is:

```python
(domain, concept_code, part_concept_code, is_disputed)
```

This means records are not merged when they differ by concept, plant-part concept, domain, or disputed status.

For each group, the function:

- Copies the first record as the base display record.
- Adds `claim_count`, representing the number of records in the group.
- Adds `source_expressions`, containing distinct non-empty source expressions in encounter order.

It does not delete or update source claims in the database. It also does not merge records with different `is_disputed` values.

### 5.4 `group_properties_by_domain(properties) -> dict[str, list[dict[str, Any]]]`

Creates a dictionary of property records grouped by domain.

**Logic:**

1. Initializes the six standard domains in `FIXED_DOMAIN_ORDER`.
2. Calls `dedupe_properties()`.
3. Places each deduplicated property under its lowercased domain.
4. Preserves additional, unexpected domain names as additional dictionary keys.

A standard domain with no records remains present with an empty list.

### 5.5 `virya_consensus(properties) -> dict[str, Any] | None`

Creates a compact summary of the Virya records.

It first filters the input to records whose domain is `virya`.

Possible results:

- **No Virya records:** returns `None`.
- **One unique concept code:** returns a `consensus` result with `agrees=True`.
- **More than one unique concept code:** returns a `divergent` result with `agrees=False` and the list of concept codes.

The consensus text includes the total claim count and a display label. When available, the canonical Sanskrit IAST form is included alongside the label.

This is a presentation summary of mapped concept agreement. It does not adjudicate source disagreements or determine which source is authoritative.

### 5.6 `dedupe_dosha_effects(effects) -> dict[str, Any]`

Builds two related presentation structures:

- `unique_effects`: deduplicated Dosha/effect pairs.
- `three_doshas`: a fixed Vata, Pitta, and Kapha view.

Dosha names are inferred from concept codes or display labels. Effect labels are normalized into:

- `Pacifies / Decreases`
- `Aggravates / Increases`
- The original label, or `Unspecified effect` when no recognized effect is available.

The deduplication key is `(dosha, effect_text)`. Each pair tracks a claim count and distinct source expressions.

The three-Dosha structure always contains Vata, Pitta, and Kapha. If no effect is recorded for one of them, the output says `"Not recorded"` and sets `recorded=False`.

**Important:** `"Not recorded"` is not equivalent to `"no effect"`. The function intentionally avoids interpreting missing data as evidence of no effect.

### 5.7 `classify_subfield_variant(subfield: str) -> str`

Classifies a legacy attribute subfield into a display variant.

Rules:

| Condition | Result |
|---|---|
| Exactly `Name` or ending in `.Name` | `english` |
| Contains `Diacritical` | `iast` |
| Contains Devanagari characters | `hindi` |
| Anything else | Original trimmed subfield string |

The final fallback is not converted into a standardized language code; it preserves the unrecognized subfield identifier.

### 5.8 `group_attributes(attributes) -> dict[str, Any]`

Transforms raw `herb_attributes` rows into named display sections.

Each input row is expected to contain fields such as:

- `field_name`
- `value`
- `source_text`
- `source_language`

The function splits `field_name` into a primary group and subfield using the first period. It then classifies the subfield and organizes values by group.

The returned dictionary contains:

| Output key | Purpose |
|---|---|
| `vernacular_names` | Language names, language codes, and joined vernacular values |
| `vernacular_sources` | Distinct sources for vernacular names |
| `parts_used` | English, IAST, and Devanagari rows for plant parts |
| `dosage_formulations` | Name, form, and reference records |
| `dosage_references` | Distinct dosage references |
| `dosage_sources` | Sources for dosage formulations |
| `dose_items` | Dose statements |
| `dose_sources` | Sources for dose statements |
| `doshakarma_merged` | Merged Doshakarma language variants |
| `karma_merged` | Merged Karma language variants |
| `therapeutic_usages` | Therapeutic usage strings |
| `therapeutic_sources` | Sources for therapeutic usage |
| `etymology_merged` | Merged etymology variants |
| `varga_merged` | Merged Varga variants |
| `pharmacopoeial_records` | Pharmacopoeial field/value pairs |
| `pharmacopoeial_sources` | Sources for pharmacopoeial records |
| `raw_dravyaguna_groups` | Available Rasa, Guna, Virya, Vipaka, Prabhava, Mahakashaya, and Skandha groups |
| `other_groups` | Unrecognized groups retained as generic field/value rows |

The internal `_merge_triple_group()` helper aligns English, IAST, and Hindi values by list position. It does not perform linguistic matching or guarantee that values at the same position are semantically equivalent.

Unknown attribute groups are preserved in `other_groups` rather than discarded.

### `herb_image_url(herb)`

Resolves the CCRAS DRAVYA CDN image URL for a herb dictionary based on its resolved plant ID:
`https://dravya.ccras.org.in/resources/views/admin/required/upload/{plant_id}.jpg`. Returns `None` if no plant ID is resolved.

### `herb_vernacular_table(herb)`

Extracts vernacular names across Indian languages from the curated `herb_names.csv` glossary via `HerbGlossaryStore`. Returns a list of dictionaries with `language`, `name`, and ISO `lang_code`.

### `herb_name(herb, lang="en")`

Jinja presentation helper and filter resolving the localized herb name for a herb dictionary in the requested ISO language code (`'hi'`, `'ta'`, `'ur'`, etc.) using `HerbGlossaryStore`:
- When `lang == 'en'`: returns the curated English column name if available, falling back to `herb['english_name']` or `herb['original_name']`.
- When `lang != 'en'`: returns the native script name from the glossary if available and not `"N/A"`, or `None` if no translation exists in that language (allowing templates to render the graceful fallback notice).

## 6. How `web_app.py` Uses This Module

The herb detail route uses the module in two paths.

### When Stage C schema version 3 is available

- `dedupe_properties()` prepares normalized property records.
- `group_properties_by_domain()` builds domain sections.
- `virya_consensus()` prepares the Virya summary.
- `dedupe_dosha_effects()` prepares the normalized Dosha view.
- `group_attributes()` still processes legacy attributes.

### When Stage C is unavailable

- The normalized property collections are empty.
- The domain grouping is initialized with empty lists.
- The Virya summary is `None`.
- `dedupe_dosha_effects()` receives the legacy Dosha records instead.
- `group_attributes()` continues to prepare the legacy attribute sections.

This allows the herb page to retain legacy information while presenting normalized semantic data only when the schema capability is available.

## 7. Example

```python
from herbal_almanac.herb_view import (
    clean_family,
    dedupe_properties,
    virya_consensus,
)

family = clean_family("Lamiaceae, Lamiaceae")

properties = [
    {
        "domain": "rasa",
        "concept_code": "RASA_TIKTA",
        "part_concept_code": None,
        "is_disputed": False,
        "display_label": "Bitter",
        "source_expression": "Tikta",
    },
    {
        "domain": "rasa",
        "concept_code": "RASA_TIKTA",
        "part_concept_code": None,
        "is_disputed": False,
        "display_label": "Bitter",
        "source_expression": "तिक्त",
    },
]

deduped = dedupe_properties(properties)

print(family)
# Lamiaceae

print(deduped[0]["claim_count"])
# 2

print(deduped[0]["source_expressions"])
# ['Tikta', 'तिक्त']
```

## 8. Design Boundaries

- This module does not access SQLite.
- It does not create, update, or delete source claims.
- It does not decide whether a disputed claim is correct.
- It does not treat missing Dosha information as absence of an effect.
- It does not translate arbitrary attribute values.
- It prepares data for presentation; repository and database modules remain responsible for retrieval and persistence.
