"""
Pytest configuration and session-scoped hermetic test fixtures.
Provides an offline, deterministic Schema Version 2 SQLite database
seeded from sample.html without any live network access.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import pytest

# Force plain CLI output in tests; prevent Typer and Rich from emitting ANSI
# color codes or wrapping lines when GITHUB_ACTIONS or color flags are set in CI.
os.environ.pop("FORCE_COLOR", None)
os.environ.pop("CLICOLOR_FORCE", None)
os.environ.pop("PY_COLORS", None)
os.environ.pop("GITHUB_ACTIONS", None)
os.environ["NO_COLOR"] = "1"
os.environ["TERM"] = "dumb"
os.environ["COLUMNS"] = "200"
os.environ["TERMINAL_WIDTH"] = "200"

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.scrapper import parse_plant


@pytest.fixture(scope="session")
def hermetic_v2_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Builds a hermetic Schema Version 2 database from sample.html.

    Session-scoped, strictly offline, no live network calls.
    Generates a database at schema version 2 ([1, 2]) containing realistic
    CCRAS DRAVYA plant records and claims parsed from sample.html.
    """
    tmp_dir = tmp_path_factory.mktemp("hermetic_db_session")
    db_path = tmp_dir / "hermetic_v2.db"

    almanac = AyurvedicAlmanac(db_path)
    almanac.create_database()

    project_root = Path(__file__).resolve().parent.parent
    sample_html_path = project_root / "sample.html"
    if sample_html_path.is_file():
        html_content = sample_html_path.read_text(encoding="utf-8")
        record = parse_plant(plant_id=1, url="https://example.com/plant/1", html=html_content)
        almanac.insert_record(record)

    return db_path
