"""Smoke test for a wheel installed outside the source repository."""

from pathlib import Path
import tempfile

from herbal_almanac import PlantRecord
from herbal_almanac.cleaning import clean_text
from herbal_almanac.database_operator import AyurvedicAlmanac
import herbal_almanac.migrations.migration_0003_semantic_dravyaguna as migration_3
import herbal_almanac.repository_api as repo_api
import herbal_almanac.schema_capability_gate as gate
import herbal_almanac.concept_catalog as catalog
import herbal_almanac.claim_lifecycle as lifecycle
import herbal_almanac.backfill_engine as backfill
import herbal_almanac.cli as cli
import herbal_almanac.web_app as web_app


def main() -> None:
    assert clean_text("  Tulsi  ") == "Tulsi"
    assert PlantRecord.__module__ == "herbal_almanac.cleaning"
    assert migration_3.MIGRATION_VERSION == 3
    assert hasattr(repo_api, "herb_dravyaguna_profile")
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "selected.db"
        database = AyurvedicAlmanac(database_path)
        database.create_database()
        assert database_path.exists()

        # Verify Stage C upgrade from wheel works (SQL assets packaged)
        upgrade_res = database.upgrade_to_stage_c()
        assert upgrade_res["version"] == 3

    print("installed package smoke test passed")


if __name__ == "__main__":
    main()