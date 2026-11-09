# Database Operator

## Purpose and boundaries

`src/herbal_almanac/database_operator.py` owns SQLite persistence for
validated `PlantRecord` objects. It does not download pages or parse source
HTML. Its responsibilities include connection lifecycle, legacy schema
compatibility, versioned migrations, transactional persistence, search, and
export-oriented reads.

## `AyurvedicAlmanac` and connection management

### Database path

`AyurvedicAlmanac(database_path=None)` uses a per-user writable location:

- Linux/Unix: `$XDG_DATA_HOME/herbal-almanac/AyurvedicDB.db`, falling back to
  `~/.local/share/herbal-almanac/AyurvedicDB.db`.
- macOS: `~/Library/Application Support/herbal-almanac/AyurvedicDB.db`.
- Windows: `%APPDATA%/herbal-almanac/AyurvedicDB.db`.

The parent directory is created when a connection is opened. Pass an explicit
path for tests, isolated runs, or a shared local database.

### `connect()`

Each new SQLite connection enables `PRAGMA foreign_keys = ON` and uses
`sqlite3.Row` as its row factory. Foreign-key enforcement is configured per
connection.

### Private `_connection()`

Ordinary read and CRUD methods use the private `_connection()` context
manager. It opens one operation-scoped connection, enters SQLite's
transaction context, and closes the connection in `finally`. Normal exit
commits; exceptions roll back; both paths close the connection. Using
`contextlib.closing()` alone would close the resource but would not supply the
transaction behavior.

`create_database()` intentionally has a separate lifecycle because it
manages schema creation and versioned migrations. It closes its connection in
`finally` and marks the instance initialized only after successful completion.

## Active legacy application tables

The application currently continues to read and write these tables:

| Table | Responsibility |
|---|---|
| `herbs` | Herb identity, source/source-record identity, original and compatibility names, botanical name/family text, source URL, retrieval timestamp, and search key |
| `illness` | Condition names, normalized/canonical search keys, and verification metadata |
| `treatment` | Herb–illness relationships; `source` distinguishes manual and scraped rows |
| `herb_attributes` | Flexible section-qualified source values, source wording/language, and translation metadata |
| `herb_doshas` | Normalized Vata/Pitta/Kapha effect rows retaining the source expression |

### Transactional record upsert

`insert_record()` writes one cleaned record in one transaction. It upserts
the herb by `(source, source_record_id)`, resolves the actual local herb ID,
refreshes flexible attributes, refreshes scraped treatment links while
preserving manual links, and refreshes normalized Dosha rows. It commits only
after all steps succeed. Failure rolls back the complete record update.

The source condition field currently creates unverified illness entries and
scraped treatment links. Other Therapeutic Usage sections remain available as
source attributes. Translation-generated attributes retain their
machine-generated/unverified metadata.

## Legacy compatibility and initialization

`create_database()` first acquires the instance's re-entrant
initialization lock. It opens its own connection, sets
`PRAGMA busy_timeout = 10000`, and uses `BEGIN IMMEDIATE` to reserve the
SQLite writer before schema changes. Static DDL statements execute individually
inside the transaction; `executescript()` is avoided because it implicitly
commits a pending transaction.

Legacy table/column adjustments and data consolidation remain supported for
existing local database files. Versioned normalized migrations then use the
`schema_migrations` ledger. Each migration body and its version row are
committed together under the writer reservation. Failed work is rolled back
and is not marked as applied. An instance becomes initialized only after the
whole initialization flow succeeds.

## Versioned migrations

### Migration 1 — core identity and provenance

Version `1`, `core_identity_and_provenance`, adds:

- `schema_migrations` — applied migration versions.
- `sources` — source/provider identifiers, including a manual source.
- `source_records` — source-level record identifiers and retrieval metadata.
- `source_claims` — assertions tied to source records, including review
  workflow and correction lineage.
- `legacy_herb_map` — a stable one-to-one mapping from legacy herb IDs.
- `herb_names` — typed, multilingual, claim-backed herb name associations.

Before backfill, duplicate normalized legacy identities
`(cleaned source, string source_record_id)` are rejected with
`MigrationError` and conflicting herb IDs. Missing external IDs remain
explicitly represented by `legacy_herb_id:<id>` artifact references rather
than invented keys. The backfill preserves legacy IDs and source URLs and uses
the inserted source-record ID directly to avoid ambiguous lookup.

Migration 1 does not rewrite the active legacy application tables or redirect
application reads/writes to the new tables. Its new structures provide an
additive provenance foundation.

### Migration 2 — normalized botanical taxonomy

Version `2`, `normalized_botanical_taxonomy`, adds:

- `taxa` — taxonomic concepts with controlled rank and normalized-name fields.
- `taxon_relationships` — provenance-backed parent-child or synonym links.
- `herb_taxa` — provenance-backed associations between herbs and taxa.

Legacy botanical names are backfilled as separate `unknown`-rank taxa;
legacy family values are backfilled as `family`-rank taxa. The migration
preserves original herb columns and does not infer accepted status, author
citations, parent-child hierarchy, or synonym merges. Each association is
linked to a source claim. Constraints enforce allowed ranks and relationship
types, foreign keys, no self-parent relationships, duplicate prevention, and
the preferred accepted-taxon rule.

Migration 2 remains additive: the legacy tables continue to be the active
application read/write contract.

### Claim-to-herb validation

SQLite foreign keys confirm that referenced claims and herbs exist, but they
cannot prove that a claim's source record belongs to the herb receiving a name
association. The application helper `_validate_herb_claim()` verifies the
source-record relationship before `_insert_herb_name()` writes a row.
Missing, cross-herb, or ambiguous associations raise
`ClaimAssociationError`.

The supported manual-claim path requires the `manual` source and an explicit
`raw_artifact_ref = legacy_herb_id:<herb_id>` binding. This is an
application-level rule; direct SQL can bypass it and should not be treated as
validated application curation.

## Search and read behavior

Herb and illness searches use normalized search keys and ranked exact,
substring, and fuzzy matching. Non-empty queries omit results below the
`0.65` minimum score; empty queries retain the full sorted listing behavior.
This reduces unrelated whole-string matches while retaining small spelling
variants.

`herb_doshas(herb_id)` returns normalized effects with their source
expressions. `all_records()` includes Dosha data for JSON/CSV export.
Compatibility helpers `insert_herb()` and `insert_illness()` remain for the
original prototype; new ingestion should use `insert_record()`.

## Connection and migration verification

The offline database tests cover:

- Success and failure connection closure.
- Transaction rollback and foreign-key enforcement.
- Independent operation connections.
- Concurrent initialization on one instance and across instances.
- Idempotent migration application.
- Migration rollback and retry without a partial version-ledger entry.

Run both the mandatory regression and full suite:

```bash
python -m pytest tests/test_scrapper.py -q
python -m pytest -q
```

## Design boundary

The normalized schema is deliberately staged. Migrations 1 and 2 add source
identity/provenance and botanical taxonomy, but the legacy application model
remains active. The remaining target domain structures in
`documentations/database_schema.md` must be treated as proposals until their
own migrations and tests are implemented.
