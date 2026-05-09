import json
from pathlib import Path

from groundline.core.app_recipe import (
    app_status,
    default_app_recipe,
    export_latest_artifact,
    load_app_recipe,
    run_app_recipe,
    write_app_recipe,
)
from groundline.core.engine import Groundline


def test_app_recipe_run_writes_artifacts_and_status(tmp_path: Path) -> None:
    recipe = default_app_recipe().model_copy(
        update={
            "collection": "app_demo",
            "artifacts_dir": str(tmp_path / "artifacts"),
        }
    )
    recipe_path = tmp_path / "groundline.app.toml"
    data_dir = tmp_path / "data"
    engine = Groundline.from_local(data_dir)

    write_app_recipe(recipe_path, recipe)
    loaded = load_app_recipe(recipe_path)
    report = run_app_recipe(engine=engine, recipe=loaded, data_dir=data_dir)
    status = app_status(engine, loaded)
    exported = export_latest_artifact(loaded, tmp_path / "exported.json")

    assert loaded == recipe
    assert report.demo.ingest.documents
    assert report.artifacts[0].kind == "latest"
    assert Path(report.artifacts[0].path).exists()
    artifact_payload = json.loads(Path(report.artifacts[0].path).read_text())
    assert artifact_payload["recipe"]["collection"] == "app_demo"
    assert artifact_payload["demo"]["collection"] == "app_demo"
    assert status.latest_artifact is not None
    assert status.latest_run is not None
    assert exported.path.endswith("exported.json")
    assert (tmp_path / "exported.json").exists()
