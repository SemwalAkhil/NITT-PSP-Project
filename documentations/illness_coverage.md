# Illness Glossary Coverage Auditor (`illness_coverage.py`)

## 1. Purpose
The `illness_coverage.py` script audits an existing SQLite database against the packaged multilingual illness glossary. It calculates glossary resolution percentages, lists unresolved condition terms, and flags catalog-versus-CSV translation discrepancies.

## 2. Where it fits
- **Upstream callers:** Run directly from the command line as an administrative audit and quality-assurance utility.
- **Downstream dependencies:** Calls `database_operator.py` to inspect illness records and `illness_glossary.py` to test resolution and fetch catalog conflicts.

## 3. Key functions and classes
- `audit_illness_coverage(database_path, print_conflicts=False)`: Accepts a database path and conflict flag, returns an audit report dictionary containing resolution statistics, kind breakdowns, and unresolved names.
- `main()`: CLI argument parsing entry point that executes the audit and formats terminal report output.

## 4. Worked example
```bash
# Run coverage audit on local database
python scripts/illness_coverage.py --database data/demo.db

# Include catalog-vs-CSV translation conflict audit
python scripts/illness_coverage.py --database data/demo.db --conflicts
```
