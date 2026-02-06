from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import duckdb

from deadlock_backend.config import TRAINING_DB_PATH, EXPORTS_ROOT, DEFAULT_ASSET_PREFIX


def compute_model_metadata(con: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
    """
    Compute high-level stats for the model from the training DB.

    Adjust the table names (match_info, match_player, etc.) if yours differ.
    """

    # Matches + date range for this patch
    matches_row = con.execute(
        """
        SELECT
            COUNT(DISTINCT match_id) AS matches_analyzed,
            MIN(start_time)          AS date_from,
            MAX(start_time)          AS date_to
        FROM match_info
        """
    ).df().iloc[0]

    # Unique players in the training data
    players_row = con.execute(
        """
        SELECT COUNT(DISTINCT account_id) AS players_sampled
        FROM match_player
        """
    ).df().iloc[0]

    # Hero and item coverage
    heroes_row = con.execute(
        "SELECT COUNT(*) AS hero_count FROM heroes"
    ).df().iloc[0]

    items_row = con.execute(
        "SELECT COUNT(*) AS item_count FROM shop_items"
    ).df().iloc[0]

    meta = {
        "matches_analyzed": int(matches_row["matches_analyzed"]),
        "players_sampled": int(players_row["players_sampled"]),
        "date_from": str(matches_row["date_from"])[:10],
        "date_to": str(matches_row["date_to"])[:10],
        "hero_count": int(heroes_row["hero_count"]),
        "item_count": int(items_row["item_count"]),
    }

    return meta


def build_model_metadata(model_version: str) -> Path:
    """
    Compute metadata and write it to:

        exports/<model_version>/<DEFAULT_ASSET_PREFIX>/model_metadata.json
    """
    assets_dir = EXPORTS_ROOT / model_version / DEFAULT_ASSET_PREFIX
    assets_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(TRAINING_DB_PATH)
    try:
        meta_core = compute_model_metadata(con)
    finally:
        con.close()

    meta = {
        "model_version": model_version,
        **meta_core,
    }

    out_path = assets_dir / "model_metadata.json"
    out_path.write_text(json.dumps(meta, indent=2))
    print(f"Wrote model metadata -> {out_path}")
    return out_path
