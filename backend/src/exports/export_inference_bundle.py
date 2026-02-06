"""
Build a compact inference bundle from the training DuckDB + model files.

Resulting structure:

  exports/<model_version>/
    models/
      inference.duckdb
      early.json
      mid.json
      late.json
      very_late.json
      training_metadata.json
      bundle_metadata.json
    <model_version>.zip      # zip of the `models/` subdir

Only the tables required for inference are copied into inference.duckdb.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb

from ..config import (
    TRAINING_DB_PATH,
    MODELS_ROOT,
    EXPORTS_ROOT,
    INFERENCE_SUBDIR,
    INFERENCE_DB_NAME,
    PHASES,
)

# These must exist in the training DB.
INFERENCE_TABLES: list[str] = [
    "heroes",
    "shop_items",
    "item_assets",
    "match_info",
    "hero_synergy",
    "hero_counter",
    "hero_soul_matchup",
    "hero_lane_snap_9",
    "hero_item_winrate",
    "item_transition_stats",
]


@dataclass
class BundlePaths:
    model_version: str
    bundle_dir: Path
    models_dir: Path
    inference_db_path: Path
    zip_path: Path
    training_meta_path: Path


def _resolve_paths(model_version: str) -> BundlePaths:
    bundle_dir = EXPORTS_ROOT / model_version
    models_dir = bundle_dir / INFERENCE_SUBDIR
    inference_db_path = models_dir / INFERENCE_DB_NAME
    zip_path = bundle_dir / f"{model_version}.zip"
    training_meta_path = MODELS_ROOT / model_version / "training_metadata.json"

    return BundlePaths(
        model_version=model_version,
        bundle_dir=bundle_dir,
        models_dir=models_dir,
        inference_db_path=inference_db_path,
        zip_path=zip_path,
        training_meta_path=training_meta_path,
    )


def _copy_tables_with_attach(
    tables: Iterable[str],
    source_db: Path,
    dest_db: Path,
) -> None:
    """
    Use ATTACH on both the source and destination DBs, then
    copy tables via:

      CREATE TABLE dest_db.table AS
      SELECT * FROM source_db.table;
    """
    dest_db.parent.mkdir(parents=True, exist_ok=True)

    # Connect to a throwaway in-memory DB and attach both files
    con = duckdb.connect(database=":memory:")

    src_str = source_db.as_posix()
    dst_str = dest_db.as_posix()

    print(f"ATTACH source_db: {src_str}")
    con.execute(f"ATTACH '{src_str}' AS source_db (READ_ONLY TRUE);")

    print(f"ATTACH dest_db:   {dst_str}")
    con.execute(f"ATTACH '{dst_str}' AS dest_db (READ_ONLY FALSE);")

    try:
        for table in tables:
            print(f"  Copying table {table!r} -> dest_db.{table}")
            con.execute(
                f"CREATE OR REPLACE TABLE dest_db.{table} AS "
                f"SELECT * FROM source_db.{table};"
            )
    finally:
        con.execute("DETACH source_db;")
        con.execute("DETACH dest_db;")
        con.close()


def _create_inference_db(paths: BundlePaths) -> None:
    """
    Creates a tiny DuckDB file (inference.duckdb) containing only
    the tables needed for inference.
    """
    if not TRAINING_DB_PATH.exists():
        raise FileNotFoundError(
            f"Training DB not found at {TRAINING_DB_PATH}. "
            "Run the training notebook first."
        )

    _copy_tables_with_attach(
        tables=INFERENCE_TABLES,
        source_db=TRAINING_DB_PATH,
        dest_db=paths.inference_db_path,
    )


def _copy_model_files(paths: BundlePaths) -> None:
    """
    Copy XGBoost model JSONs and training_metadata.json into models_dir.
    """
    src_model_dir = MODELS_ROOT / paths.model_version
    if not src_model_dir.exists():
        raise FileNotFoundError(
            f"Model directory not found: {src_model_dir}. "
            "Did you run the training notebook?"
        )

    paths.models_dir.mkdir(parents=True, exist_ok=True)

    # Phase models
    for phase in PHASES:
        src = src_model_dir / f"{phase}.json"
        dst = paths.models_dir / f"{phase}.json"
        if not src.exists():
            raise FileNotFoundError(f"Expected model file missing: {src}")
        shutil.copy2(src, dst)

    # training_metadata.json
    if not paths.training_meta_path.exists():
        raise FileNotFoundError(
            f"training_metadata.json missing at {paths.training_meta_path}"
        )
    shutil.copy2(paths.training_meta_path, paths.models_dir / "training_metadata.json")


def _write_bundle_metadata(paths: BundlePaths) -> None:
    """
    Write a small metadata file with bundle information.
    """
    training_meta = json.loads(paths.training_meta_path.read_text())

    bundle_meta = {
        "model_version": paths.model_version,
        "tables": INFERENCE_TABLES,
        "phases": training_meta.get("phases"),
        "features": training_meta.get("features"),
        "numeric_features": training_meta.get("numeric_features"),
        "categorical_features": training_meta.get("categorical_features"),
    }

    out_path = paths.models_dir / "bundle_metadata.json"
    out_path.write_text(json.dumps(bundle_meta, indent=2))
    print(f"Wrote bundle_metadata.json to {out_path}")


def _zip_models_dir(paths: BundlePaths) -> None:
    """
    Zip the models_dir into <model_version>.zip in bundle_dir.
    """
    paths.bundle_dir.mkdir(parents=True, exist_ok=True)

    if paths.zip_path.exists():
        paths.zip_path.unlink()

    print(f"Creating zip archive at {paths.zip_path}...")

    with zipfile.ZipFile(paths.zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths.models_dir.rglob("*"):
            arcname = path.relative_to(paths.bundle_dir)
            zf.write(path, arcname)

    size_mb = paths.zip_path.stat().st_size / (1024 * 1024)
    print(f"Zip size: {size_mb:.2f} MB")


def build_inference_bundle(model_version: str) -> tuple[Path, Path]:
    """
    Create a compact inference bundle for the given model_version.

    Returns:
        (bundle_dir, zip_path)
    """
    paths = _resolve_paths(model_version)

    print(f"Building inference bundle for model_version={model_version!r}")
    print(f"Training DB: {TRAINING_DB_PATH}")
    print(f"Bundle dir:  {paths.bundle_dir}")

    # 1) Build tiny inference DB from the training DB
    _create_inference_db(paths)

    # 2) Copy models + training metadata
    _copy_model_files(paths)

    # 3) Write bundle metadata
    _write_bundle_metadata(paths)

    # 4) Zip everything in bundle_dir/models
    _zip_models_dir(paths)

    return paths.bundle_dir, paths.zip_path
