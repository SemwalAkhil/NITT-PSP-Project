"""Smoke test for a wheel installed outside the source repository."""

from pathlib import Path
import tempfile

from herbal_almanac import PlantRecord
from herbal_almanac.cleaning import clean_text
from herbal_almanac.database_operator import AyurvedicAlmanac


def main() -> None:
    assert clean_text("  Tulsi  ") == "Tulsi"
    assert PlantRecord.__module__ == "herbal_almanac.cleaning"
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "selected.db"
        database = AyurvedicAlmanac(database_path)
        database.create_database()
        assert database_path.exists()
    print("installed package smoke test passed")


if __name__ == "__main__":
    main()