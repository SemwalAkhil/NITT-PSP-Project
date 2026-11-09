# Database Operator

## Purpose

`database_operator.py` owns SQLite persistence for cleaned DRAVYA records. It
does not download pages or interpret HTML. Its responsibilities are connection
management, schema creation, lightweight migration, transactional persistence,
and idempotent updates.

## `AyurvedicAlmanac`

### Constructor

`AyurvedicAlmanac(database_path=None)` uses a per-user writable data directory
when no path is supplied. On Linux and other Unix-like systems this is
`$XDG_DATA_HOME/herbal-almanac/AyurvedicDB.db`, or
`~/.local/share/herbal-almanac/AyurvedicDB.db` when `XDG_DATA_HOME` is unset.
macOS uses `~/Library/Application Support/herbal-almanac/AyurvedicDB.db`, and
Windows uses `%APPDATA%/herbal-almanac/AyurvedicDB.db`.

The parent directory is created when the first connection is opened, so an
installed package never writes beside its own modules. Pass an explicit path,
such as `/tmp/ayurvedic.db`, for tests, isolated runs, or a shared database.
Existing databases at either the default or explicit path continue through the
existing schema migration process.

### `connect()`

Every connection enables:

```sql
PRAGMA foreign_keys = ON;
```

SQLite does not enforce foreign keys by default on every new connection.
Connections return `sqlite3.Row` objects so columns can be accessed by name.

## Schema

### `herbs`

Stores the main plant identity, source name, source record ID, source URL,
retrieval timestamp, botanical name, and family. `original_name` stores the normalized Unicode
source name. The original `english_name` field is retained as the
transliterated compatibility/search name.

The pair `(source, source_record_id)` identifies one source record across
repeated scrapes.
`retrieved_at` records when the source page was extracted.

### `illness`

Stores illness names for the planned herb-to-illness model. The current DRAVYA scraper populates this table only from values in the
the `Therapeutic Usage.Name` condition field in `cleaning.py`. These source
conditions are marked unverified; controlled-vocabulary mapping is deferred.
Other therapeutic fields remain source attributes. `canonical_key` is unique
so case, diacritic, and terminal transliteration variants of the same illness
can be shared by many herbs. The original display name is retained in
`english_name`.

### `treatment`

This many-to-many join table connects herbs and illnesses through `herb_id`
and `illness_id`. Its composite primary key prevents duplicate relationships,
and foreign keys use cascading deletes. The `source` column distinguishes
`scraped` relationships from `manual` relationships added through the CLI.
Values from the source condition field create `scraped` relationships, while
their `machine_generated` and
`verification_status` metadata records that they are unverified.

### `herb_attributes`

Stores flexible fields that do not yet have dedicated normalized columns:

- `herb_id`
- `field_name`
- `value`
- `source_text`
- `source_language`
- `machine_generated`
- `verification_status`

The composite primary key prevents duplicate values for one herb and field.
`source_text` preserves the original extracted wording for review.
Translation metadata identifies automatically generated values and whether
they have been reviewed.

Vernacular names use the same flexible attribute store with field names such
as `Vernacular Names.English` and `Vernacular Names.Hindi`. English is included
in the supported language list because it is the source's primary display-name
language. The source title's Ayurvedic/Sanskrit name is stored in the normalized
`herbs.original_name` column. Its transliteration is stored in the
compatibility `herbs.english_name` column, while searches check both columns.
Other language values remain available through `herb_attributes` without
adding a fixed column for every language.

Translated values use the same store with `Translated Names.<Language>` field
names. They are persisted by `insert_record()` exactly like source
attributes, so JSON and CSV exports include them automatically.

### `herb_doshas`

Stores one normalized effect for each Dosha documented by a source expression:

- `herb_id`
- `dosha` (`Vata`, `Pitta`, or `Kapha`)
- `effect` (`decrease`, `increase`, or `unspecified`)
- `source_expression`
- `source`

Every documented expression creates all three Dosha rows, including
`unspecified` rows for Doshas that are not mentioned. This makes the absence of
an effect explicit without inferring one. Scraped rows are replaced during a
record refresh, while the source expression is retained for auditability.

## Schema migration

`create_database()` is safe to call repeatedly. It creates missing tables and
adds the newer columns to the original prototype `herbs` table when needed.
It also creates a unique source-record index and migrates legacy illness
tables. The illness migration consolidates canonical duplicate names,
redirects or removes duplicate treatment links, and creates a unique index on
`illness(canonical_key)` so illness upserts have a valid conflict target.
Existing SQLite files are migrated in place; use a new database path for a
clean rebuild.

This is a lightweight migration approach suitable for the current prototype.
A formal migration tool can be introduced when schema changes become frequent.

### Migration 1: core identity and provenance

Migration 1 is tracked in `schema_migrations` at version `1` with the name
`core_identity_and_provenance`. It runs transactionally after the legacy
prototype initialization and creates `sources`, `source_records`,
`source_claims`, `legacy_herb_map`, and `herb_names`. A partial unique index
enforces non-null `(source_id, external_record_key)` pairs while allowing
multiple legacy records whose external key is unavailable.

Before Migration 1 creates any of its tables, it validates normalized legacy
identities `(cleaned source, string source_record_id)`. Duplicate non-null
identities raise `MigrationError` with the conflicting legacy herb IDs. Null
source-record IDs remain valid because each receives its explicit
`legacy_herb_id:<id>` artifact reference. The backfill uses each inserted
`source_records` row ID directly; it never selects a possibly ambiguous match
with `ORDER BY` and `LIMIT`.

The backfill creates source rows from existing source identifiers and a
`manual` source row for future curation. It preserves source URLs, retrieval
timestamps, and non-null external record IDs. Records without an external key
retain a `legacy_herb_id:<id>` artifact reference instead of receiving an
invented key. Existing herb IDs map one-to-one through `legacy_herb_map`.

One claim-backed `source_alias` name is created from each herb's existing
`original_name` (or `english_name` when the original is absent). Existing
attributes, treatments, Dosha rows, and herb columns are not rewritten. The
application continues to read and write the legacy tables; the new tables are
available for migration validation and future dual-write work.

If table creation or backfill fails, the Migration 1 transaction rolls back its
new tables and does not insert a migration-version row. Reinitialization is
idempotent after a successful versioned run.

### Application-level claim subject validation

SQLite foreign keys prove that a `herb_names.herb_id` and
`source_claims.source_claim_id` exist, but they cannot prove that the claim's
source record describes that herb. The private `_validate_herb_claim()` helper
resolves the herb through `legacy_herb_map`, resolves its unique source record,
and rejects missing, cross-herb, or ambiguous claims with
`ClaimAssociationError`. `_insert_herb_name()` invokes this helper before
creating an association.

Manual claims are accepted only when their source is `manual` and their source
record has the explicit `raw_artifact_ref = legacy_herb_id:<herb_id>` binding.
This is a deliberate application policy for future manual curation, not a
database-enforced foreign key. Direct SQL inserts can bypass it and must not be
treated as validated application operations.

## `insert_record()`

One record is written in a single transaction:

1. Ensure the schema exists.
2. Insert or update the herb using `(source, source_record_id)`.
3. Resolve the actual local herb ID using that natural key.
4. Delete the herb's previous attributes.
5. Delete the herb's previous scraped treatment links; manual links are
   preserved.
6. Insert the current cleaned attributes.
7. Create or reuse unverified conditions from the source condition field and
   insert the current herb-to-illness links.
8. Normalize and insert the current Doshakarma expressions into `herb_doshas`.
9. Commit only after all steps succeed.

If an attribute insert fails, the context manager rolls back the whole update.
This prevents partially updated records.

The local ID is queried after the upsert instead of relying on `lastrowid`.
When SQLite takes the conflict-update path, `lastrowid` is not a reliable way
to identify the existing row.

## Other methods

`insert_records()` persists an iterable of `PlantRecord` objects by delegating
to `insert_record()`.

`_insert_treatments_from_attributes()` selects section-qualified fields whose
names contain `Therapeutic` and `Usage`. It cleans and deduplicates their
values, inserts missing illness names, and creates the corresponding treatment
links. Since `insert_record()` deletes links first, a later scrape reflects
the source's current therapeutic usage rather than accumulating stale links.

Searches rank exact, substring, and fuzzy matches and omit non-empty-query
results below the minimum relevance score (`0.65`). Empty queries retain the
full sorted listing behavior. This keeps weak whole-string matches such as
`Turmeric` out of a `tulsi` search while preserving small misspellings such as
`Tulsii`.

`insert_herb()` and `insert_illness()` remain as compatibility helpers for the
original prototype. New ingestion should use `insert_record()` to retain
provenance and attributes.

`herb_doshas(herb_id)` returns normalized effects together with their source
expressions. `all_records()` includes a `doshas` group for JSON and CSV export.

## Design principle

The database stores searchable cleaned values together with source context.
This supports future normalization while keeping the dataset auditable and
rebuildable from source pages.