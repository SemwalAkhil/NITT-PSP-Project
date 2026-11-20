# Illness Glossary Coverage Auditor (`scripts/illness_coverage.py`)

## 1. Purpose

`scripts/illness_coverage.py` is a standalone audit utility that checks how well the illness records in a SQLite database match the packaged multilingual illness glossary.

It reports:

- The number of illness rows inspected.
- How many illness names resolve through the glossary.
- How many remain unresolved.
- The glossary resolution percentage.
- A breakdown of resolved records by concept kind.
- Optionally, disagreements between selected Stage C catalog labels and CSV glossary labels.

It is a diagnostic script. It does not insert, update, or delete illness records.

## 2. Where It Fits in the Architecture

The script connects the database layer with the glossary resolution layer:

```text
scripts/illness_coverage.py
          |
          +---- SQLite database (read-only)
          |          |
          |          v
          |      illness table
          |
          +---- illness_glossary.py
                     |
                     +---- resolve_illness()
                     |
                     +---- get_catalog_csv_conflicts()
          |
          v
   Coverage report
```

The database supplies the illness names to audit. The glossary module determines whether each name can be resolved and provides the catalog-versus-CSV conflict information.

## 3. Imports and Dependencies

### Standard-library imports

| Import | Responsibility |
|---|---|
| `argparse` | Parses command-line arguments |
| `Path` | Resolves script, source, and database paths |
| `sqlite3` | Opens the target database in read-only mode |
| `sys` | Adds the project's `src` directory to the import path |

The source uses `Any` in type annotations but does not explicitly import it from `typing`. Because the module uses `from __future__ import annotations`, these annotations are postponed rather than evaluated immediately. However, resolving them later with tools such as `typing.get_type_hints()` may fail unless `Any` is made available.

### Internal imports

| Imported symbol | Origin | Responsibility |
|---|---|---|
| `default_database_path` | `herbal_almanac.database_operator` | Supplies the platform default database path |
| `get_catalog_csv_conflicts` | `herbal_almanac.illness_glossary` | Retrieves catalog-versus-CSV disagreements |
| `resolve_illness` | `herbal_almanac.illness_glossary` | Checks whether a database illness name resolves |

## 4. Project Import Setup

The script can be executed directly from the repository without requiring the package to have been installed first.

It determines the repository root:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
```

Then it adds the `src` directory to `sys.path` if it is not already present:

```python
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
```

This makes imports such as `herbal_almanac.illness_glossary` available when the script is run from the repository.

## 5. Main Audit Function

### `audit_illness_coverage(database_path, print_conflicts=False) -> dict[str, Any]`

This is the core function.

It accepts a database path and returns a dictionary containing the audit results.

The `print_conflicts` parameter is present in the function signature, but the current implementation does not use it to control conflict retrieval or report construction. Conflict data is retrieved regardless of its value. The parameter only has an effect at the caller level when `main()` decides whether to print those conflicts.

### Step 1: Validate the database path

```python
db_file = Path(database_path)

if not db_file.is_file():
    raise FileNotFoundError(...)
```

The audit requires an existing database file.

### Step 2: Open SQLite in read-only mode

```python
conn = sqlite3.connect(
    f"file:{db_file.resolve()}?mode=ro",
    uri=True,
)
```

The `mode=ro` URI parameter opens the database read-only.

The script then executes:

```sql
SELECT id, english_name
FROM illness
ORDER BY english_name
```

It retrieves the illness table rows in alphabetical order and closes the connection in a `finally` block.

The script does not modify the database.

**Counting detail:** The query does not contain `DISTINCT`; it counts every returned illness row. Whether those rows represent unique names depends on the database's own constraints.

### Step 3: Initialize audit collections

The function creates:

- `resolved`: records whose names matched the glossary.
- `unresolved`: names that did not match.
- `kind_counts`: counters for three concept kinds.

The initial kind categories are:

```python
{
    "standard": 0,
    "procedure": 0,
    "non-disease concept": 0,
}
```

### Step 4: Resolve each illness

For every database row:

```python
res = resolve_illness(name)
```

If `res.matched` is true:

- The illness ID and original database name are added to `resolved`.
- The resolved glossary object is retained in the result.
- The record's `kind` is counted when it matches a known category.
- An absent or unrecognized kind is counted as `standard`.

If `res.matched` is false, the original database name is added to `unresolved`.

The audit uses the glossary's matching logic. It does not independently verify the clinical meaning or translation of a matched term.

### Step 5: Retrieve catalog conflicts

```python
conflicts = get_catalog_csv_conflicts()
```

This retrieves the conflicts collected by the glossary store.

These conflicts are about disagreements between selected Stage C catalog labels and CSV glossary values. They are not necessarily disagreements involving the specific illness rows in the database being audited.

### Step 6: Calculate coverage

The function calculates:

```python
resolved_percentage = (
    len(resolved) / total * 100.0
) if total > 0 else 100.0
```

An empty illness table is reported as 100% resolved because there are no unresolved rows.

This percentage measures glossary matching coverage, not translation quality or medical correctness.

### Step 7: Return the audit dictionary

The returned structure contains:

| Key | Meaning |
|---|---|
| `database_path` | Absolute path to the inspected database |
| `total_illnesses` | Number of illness rows returned by the query |
| `resolved_count` | Number of matched rows |
| `unresolved_count` | Number of unmatched rows |
| `resolved_percentage` | Percentage of matched rows |
| `resolved` | Detailed matched records, including resolved glossary objects |
| `unresolved` | Original names that did not resolve |
| `kind_counts` | Counts by concept kind |
| `conflicts` | Catalog-versus-CSV conflict records |

## 6. Report Formatting Function

### `print_coverage_report(audit_result, show_conflicts=False) -> None`

Prints a human-readable terminal report.

It displays:

1. Report title.
2. Database path.
3. Total illness rows.
4. Resolved count and percentage.
5. Unresolved count.
6. Concept-kind breakdown.
7. Unresolved illness names, if any.

When `show_conflicts=True`, it also prints:

- Number of catalog conflict records.
- The affected catalog concept code.
- The original glossary term.
- The language in which a disagreement was found.
- The catalog label and CSV label.

When `--conflicts` is passed, the report explicitly prints: `Note: Curated Stage C catalog labels WIN as primary; CSV labels preserved.` and labels the conflicting sides `Curated Catalog (Primary)` and `Machine CSV (Gemini)`. This reflects the glossary's precedence behavior for catalog-backed indication terms.

## 7. Command-Line Entry Point

### `main() -> None`

The script uses `argparse` to provide two options.

| Option | Purpose |
|---|---|
| `--database` / `-d` | Explicit SQLite database path |
| `--conflicts` / `-c` | Print catalog-versus-CSV disagreements |

### Database path selection

If `--database` is supplied, that path is used.

Otherwise:

1. The script checks for `data/demo.db` inside the repository.
2. If the local demo database exists, it is selected.
3. Otherwise, `default_database_path()` is used.

The chosen path is passed to `audit_illness_coverage()`.

The returned dictionary is passed to `print_coverage_report()`. The `--conflicts` flag controls whether the conflict section is displayed.

## 8. Running the Auditor

From the repository root:

```bash
python scripts/illness_coverage.py
```

Audit a specific database:

```bash
python scripts/illness_coverage.py \
  --database data/almanac.db
```

Include catalog-versus-CSV conflict details:

```bash
python scripts/illness_coverage.py \
  --database data/almanac.db \
  --conflicts
```

Short form:

```bash
python scripts/illness_coverage.py -d data/almanac.db -c
```

## 9. Example Report Interpretation

Suppose an audit reports:

```text
Total illness rows: 100
Resolved: 85 / 100 (85.0%)
Unresolved: 15
```

This means:

- 85 database illness rows matched the glossary.
- 15 rows did not match.
- The glossary matching coverage for this database is 85%.

It does not establish that the 85 matched entries have accurate translations, nor that the 15 unmatched entries are invalid illness terms.

An unresolved name may simply be absent from the packaged glossary or use a spelling not covered by its matching rules.

## 10. Design Boundaries and Limitations

- The database is opened in read-only mode.
- The script reads the `illness` table directly rather than calling a database operator search method.
- The glossary matching behavior is delegated to `resolve_illness()`.
- The conflict report is sourced from the glossary store, not calculated by comparing only the current database's illness rows.
- The coverage percentage measures successful term resolution, not translation accuracy or clinical validity.
- The query counts all illness rows without `DISTINCT` (`SELECT id, english_name FROM illness ORDER BY english_name`), even though the script's docstring and terminal report text state "distinct illnesses".
- The `print_conflicts` parameter of `audit_illness_coverage()` is currently unused.
- The script does not catch and reformat all database, parsing, or glossary errors; unexpected failures can terminate execution.
- The script is an audit utility and does not repair unresolved terms or modify catalog labels.
