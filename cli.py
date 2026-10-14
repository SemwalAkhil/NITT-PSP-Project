from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, NoReturn

import typer
import requests
from rich.console import Console
from rich.table import Table

from database_operator import AyurvedicAlmanac
from scrapper import ScraperError, scrape


app = typer.Typer(
    name="herbal-almanac",
    help="Manage the Herbal Almanac database and data sources.",
    no_args_is_help=True,
)
console = Console()


def database(path: str) -> AyurvedicAlmanac:
    return AyurvedicAlmanac(path)


def show_rows(rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        typer.echo("No matching records.")
        return
    table = Table(title=title)
    for column in rows[0]:
        table.add_column(column)
    for row in rows:
        table.add_row(*(str(row[column] or "") for column in rows[0]))
    console.print(table)


def fail(error: Exception) -> NoReturn:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(code=1)


def write_records(
    records: dict[str, list[dict[str, Any]]],
    output: Path,
    file_format: str,
) -> None:
    if file_format == "json":
        output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    rows = [
        {"record_type": record_type, **row}
        for record_type, record_rows in records.items()
        for row in record_rows
    ]
    fieldnames = ["record_type"]
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def show_record_groups(records: dict[str, list[dict[str, Any]]]) -> None:
    for record_type, rows in records.items():
        show_rows(rows, record_type.title())


@app.command()
def setup(
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
) -> None:
    """Create the database schema and apply migrations."""
    database(database_path).create_database()
    typer.echo(f"Database ready: {database_path}")


@app.command("scrape")
def scrape_site(
    site: str = typer.Argument("dravya", help="Supported site: dravya."),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
    max_pages: int | None = typer.Option(None, min=1),
    max_plants: int | None = typer.Option(None, min=1),
    timeout: float = typer.Option(15.0, min=0.1),
    retries: int = typer.Option(2, min=0),
    record_retries: int = typer.Option(1, "--record-retries", min=0),
    failure_report: str | None = typer.Option(None, "--failure-report"),
) -> None:
    """Scrape a supported site and insert records directly into the database."""
    if site.lower() != "dravya":
        raise typer.BadParameter("Only the DRAVYA site is currently supported.", param_hint="site")
    try:
        report = scrape(
            database_path,
            max_pages,
            max_plants,
            timeout,
            retries,
            record_retries,
            failure_report,
        )
    except (OSError, ValueError, sqlite3.Error, requests.RequestException, ScraperError) as error:
        fail(error)
    typer.echo(f"Processed {report.processed} DRAVYA records.")
    if report.failures:
        typer.echo(f"Failed {len(report.failures)} records.", err=True)
        if failure_report:
            typer.echo(f"Failure report: {failure_report}", err=True)


@app.command("herb")
def add_herb(
    english_name: str = typer.Argument(..., help="Herb name."),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
    botanical_name: str | None = typer.Option(None),
    family: str | None = typer.Option(None),
    source: str | None = typer.Option(None),
    source_record_id: int | None = typer.Option(None, min=1),
    source_url: str | None = typer.Option(None),
) -> None:
    """Insert one herb while enforcing herb field validation."""
    try:
        herb_id = database(database_path).add_herb(
            english_name, source, source_record_id, source_url, botanical_name, family
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        fail(error)
    typer.echo(f"Inserted herb {herb_id}: {english_name}")


@app.command("illness")
def add_illness(
    english_name: str = typer.Argument(..., help="Illness name."),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
) -> None:
    """Insert one illness; duplicate names are rejected by the schema."""
    try:
        illness_id = database(database_path).add_illness(english_name)
    except (ValueError, OSError, sqlite3.Error) as error:
        fail(error)
    typer.echo(f"Inserted illness {illness_id}: {english_name}")


@app.command("treatment")
def add_treatment(
    herb_id: int = typer.Argument(..., min=1),
    illness_id: int = typer.Argument(..., min=1),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
) -> None:
    """Link an existing herb to an existing illness."""
    try:
        database(database_path).add_treatment(herb_id, illness_id)
    except (ValueError, OSError, sqlite3.Error) as error:
        fail(error)
    typer.echo(f"Linked herb {herb_id} to illness {illness_id}.")


@app.command("herbs")
def list_herbs(
    query: str = typer.Argument(""),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
) -> None:
    """Search herbs by common or botanical name."""
    show_rows(database(database_path).search_herbs(query), "Herbs")


@app.command("illnesses")
def list_illnesses(
    query: str = typer.Argument(""),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
) -> None:
    """Search illnesses by name."""
    show_rows(database(database_path).search_illnesses(query), "Illnesses")


@app.command("treatments")
def list_treatments(
    herb_id: int = typer.Argument(..., min=1),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
) -> None:
    """Show illnesses associated with a herb ID."""
    show_rows(database(database_path).treatment_details(herb_id), "Treatments")


@app.command("attributes")
def list_attributes(
    herb_id: int = typer.Argument(..., min=1),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional JSON or CSV destination.",
    ),
    file_format: str | None = typer.Option(
        None,
        "--format",
        help="Output format: json or csv. Inferred from --output when omitted.",
    ),
) -> None:
    """Show or export all source attributes stored for a herb."""
    if file_format is None and output is not None:
        file_format = output.suffix.lower().lstrip(".")
    if file_format is not None:
        file_format = file_format.lower()
    if file_format not in (None, "json", "csv"):
        raise typer.BadParameter("format must be json or csv", param_hint="format")
    if file_format is not None and output is None:
        raise typer.BadParameter("--output is required when --format is provided.", param_hint="output")

    try:
        rows = database(database_path).herb_attributes(herb_id)
        if output is not None and file_format is not None:
            write_records({"attributes": rows}, output, file_format)
            typer.echo(f"Saved attributes records to {output}.")
        else:
            show_rows(rows, "Herb Attributes")
    except (OSError, sqlite3.Error) as error:
        fail(error)


@app.command("records")
def list_records(
    record_type: str = typer.Argument(
        "all",
        help="Records to show: all, herbs, illnesses, treatments, or attributes.",
    ),
    database_path: str = typer.Option("AyurvedicDB.db", "--database", "-d"),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional JSON or CSV destination.",
    ),
    file_format: str | None = typer.Option(
        None,
        "--format",
        help="Output format: json or csv. Inferred from --output when omitted.",
    ),
) -> None:
    """Show all records, or save them as JSON/CSV."""
    record_type = record_type.lower()
    valid_types = {"all", "herbs", "illnesses", "treatments", "attributes"}
    if record_type not in valid_types:
        raise typer.BadParameter(", ".join(sorted(valid_types)), param_hint="record_type")

    if file_format is None and output is not None:
        file_format = output.suffix.lower().lstrip(".")
    if file_format is not None:
        file_format = file_format.lower()
    if file_format not in (None, "json", "csv"):
        raise typer.BadParameter("format must be json or csv", param_hint="format")
    if file_format is not None and output is None:
        raise typer.BadParameter("--output is required when --format is provided.", param_hint="output")

    try:
        records = database(database_path).all_records()
        selected = records if record_type == "all" else {record_type: records[record_type]}
        if output is not None and file_format is not None:
            write_records(selected, output, file_format)
            typer.echo(f"Saved {record_type} records to {output}.")
        else:
            show_record_groups(selected)
    except (OSError, sqlite3.Error) as error:
        fail(error)


if __name__ == "__main__":
    app()
