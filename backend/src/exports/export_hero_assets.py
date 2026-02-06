from pathlib import Path
import duckdb
import json

from deadlock_backend.config import EXPORTS_ROOT, TRAINING_DB_PATH, DEFAULT_ASSET_PREFIX

def build_hero_assets(model_version: str) -> Path:
    con = duckdb.connect(TRAINING_DB_PATH)

    df = con.execute("""
        SELECT
            hero_id,
            name AS hero_name,
            icon_hero_card AS hero_image,
            icon_hero_card_webp AS hero_image_webp
        FROM hero_assets
        ORDER BY hero_id
    """).df()

    out_dir = EXPORTS_ROOT / model_version / DEFAULT_ASSET_PREFIX
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "hero_assets.json"
    data = df.to_dict(orient="records")

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote hero assets → {out_path}")
    con.close()
    return out_path
