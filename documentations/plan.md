# Dravyaguna Data Mapping Project — SDLC Plan

## Current implementation snapshot

The repository currently implements the DRAVYA MVP path through
`scrapper.py`, `cleaning.py`, `database_operator.py`, and `cli.py`:

```text
DRAVYA directory
    -> HTTP discovery and fetch with retries
    -> semantic table and vernacular-card parsing
    -> PlantRecord cleaning and validation
    -> optional translation enrichment
    -> SQLite transaction (herbs, attributes, illness/treatment, Dosha)
    -> CLI inspection and JSON/CSV export
```

Implemented today:

- DRAVYA pagination, plant-ID discovery, timeouts, retries, and progress output.
- Section-qualified table attributes and language-qualified vernacular names.
- Unicode/source-text preservation and English-facing transliteration.
- Optional machine translation, disabled by default.
- Conservative Dosha-expression normalization retaining each source expression.
- SQLite record upserts and legacy schema compatibility migrations.
- Connection-scoped transactions with guaranteed connection closure.
- Concurrent schema initialization protection using an instance lock and
  SQLite writer reservation.
- Versioned Migration 1 for source identity and claim-level provenance tables.
- Migration 1 duplicate-identity preflight and application-level herb/claim
  subject validation.
- Versioned Migration 2 for botanical taxonomy tables, with conservative
  legacy backfill and no inferred taxonomic hierarchy.
- Typer commands for setup, scraping, manual records, searching, inspection,
  and JSON/CSV export.
- Offline regression, database lifecycle, initialization, and installed
  package smoke tests; CI covers Python 3.10–3.14.
- A broader normalized Dravyaguna data model in
  `documentations/database_schema.md`; domain tables beyond Migrations 1–2
  remain a staged design proposal.

Still planned:

- More normalized domain tables for properties, parts, Karma, Dosha,
  conditions, and controlled vocabularies.
- External terminology mapping and source adapters beyond CCRAS DRAVYA.
- API/PDF/Excel importers and richer data-quality reporting.
- A dedicated public Python query API and a public package release.

The detailed phase checklist below remains a design roadmap, not a claim that
every target subsystem exists. The status snapshot above distinguishes active
features from additive migration foundations and future proposal work.

## Goal

Build an open-source Python library and relational database that maps
Ayurvedic pharmacology (Dravyaguna) to Ayurvedic/Sanskrit drug names, botanical
identities, vernacular names, properties, Karma, Dosha effects, therapeutic
indications, source provenance, and supporting evidence.

## Core principle

Preserve original source wording next to normalized interpretations. Missing
or ambiguous values should remain unknown or unspecified rather than being
inferred.

---

## Long-term design roadmap

The phase-based sections below are retained as planning material. They describe
potential future capabilities and should not be read as implemented status.
