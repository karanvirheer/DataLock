"""
Runtime inference engine for Deadlock builds.

This module is intended to run inside AWS Lambda (or locally)
using the exported inference bundle.

Key concepts:

- InferenceBundle: wraps
    - inference.duckdb (with heroes/items/synergy/counter/etc.)
    - XGBoost models for each phase
    - training_metadata.json + bundle_metadata.json

- recommend_build_from_bundle: given a bundle and a draft payload,
  returns recommended items per phase.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb



PHANTOM_TIER = 9 

DEFAULT_SLOTS_PER_PHASE = {
    "early": 4,
    "mid": 4,
    "late": 4,
    "very_late": 3,
}

DEFAULT_LAMBDA_PER_PHASE = {
    "early": 0.01,
    "mid":   0.03,
    "late":  0.05,
    "very_late": 0.02,
}


def _safe_get(val, default):
    if val is None:
        return default
    if isinstance(val, float) and np.isnan(val):
        return default
    return val


@dataclass
class InferenceBundle:
    """
    Loaded inference bundle from a directory:

      bundle_root/
        inference.duckdb
        early.json
        mid.json
        late.json
        very_late.json
        training_metadata.json
        bundle_metadata.json
    """

    root: Path
    db_path: Path
    training_meta: Dict[str, Any]
    bundle_meta: Dict[str, Any]
    phases: List[str]
    features: List[str]
    numeric_features: List[str]
    categorical_features: List[str]

    con: duckdb.DuckDBPyConnection
    models: Dict[str, xgb.Booster]

    item_global_stats: pd.DataFrame
    hero_item_stats: pd.DataFrame
    transition_hero: Dict[int, Dict[int, Dict[int, float]]]
    transition_global: Dict[int, Dict[int, float]]

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_dir(cls, models_dir: Path) -> "InferenceBundle":
        models_dir = models_dir.resolve()
        db_path = models_dir / "inference.duckdb"

        if not db_path.exists():
            raise FileNotFoundError(f"inference.duckdb not found at {db_path}")

        training_meta_path = models_dir / "training_metadata.json"
        bundle_meta_path = models_dir / "bundle_metadata.json"

        if not training_meta_path.exists():
            raise FileNotFoundError(
                f"training_metadata.json not found at {training_meta_path}"
            )
        if not bundle_meta_path.exists():
            raise FileNotFoundError(
                f"bundle_metadata.json not found at {bundle_meta_path}"
            )

        training_meta = json.loads(training_meta_path.read_text())
        bundle_meta = json.loads(bundle_meta_path.read_text())

        phases = bundle_meta.get("phases") or training_meta.get("phases")
        features = bundle_meta.get("features") or training_meta.get("features")
        numeric_features = (
            bundle_meta.get("numeric_features")
            or training_meta.get("numeric_features")
        )
        categorical_features = (
            bundle_meta.get("categorical_features")
            or training_meta.get("categorical_features")
        )

        con = duckdb.connect(str(db_path), read_only=True)

        models = cls._load_phase_models(models_dir, phases)
        ig, hi = cls._load_item_stats(con)
        t_hero, t_global = cls._load_transition_stats(con)

        return cls(
            root=models_dir,
            db_path=db_path,
            training_meta=training_meta,
            bundle_meta=bundle_meta,
            phases=phases,
            features=features,
            numeric_features=numeric_features,
            categorical_features=categorical_features,
            con=con,
            models=models,
            item_global_stats=ig,
            hero_item_stats=hi,
            transition_hero=t_hero,
            transition_global=t_global,
        )

    @staticmethod
    def _load_phase_models(
        models_dir: Path, phases: List[str]
    ) -> Dict[str, xgb.Booster]:
        models: Dict[str, xgb.Booster] = {}
        for phase in phases:
            model_path = models_dir / f"{phase}.json"
            if not model_path.exists():
                raise FileNotFoundError(f"Model file missing: {model_path}")
            clf = xgb.Booster()
            clf.load_model(model_path.as_posix())
            models[phase] = clf
        return models

    @staticmethod
    def _load_item_stats(con: duckdb.DuckDBPyConnection):
        """
        Load hero_item_winrate into:
          - item_global_stats: item_id -> item_global_wr
          - hero_item_stats:   (hero_id,item_id) -> hero_item_wr
        """
        item_global_df = con.execute(
            """
            SELECT
                item_id,
                AVG(smoothed_wr) AS item_global_wr
            FROM hero_item_winrate
            GROUP BY item_id
            """
        ).df()

        hero_item_df = con.execute(
            """
            SELECT
                hero_id,
                item_id,
                smoothed_wr AS hero_item_wr
            FROM hero_item_winrate
            """
        ).df()

        return item_global_df, hero_item_df

    @staticmethod
    def _load_transition_stats(con: duckdb.DuckDBPyConnection):
        """
        Build transition dictionaries from item_transition_stats table.
        """
        df = con.execute(
            """
            SELECT hero_id, item_current, item_next, trans_prob
            FROM item_transition_stats
            """
        ).df()

        hero_map: dict[int, dict[int, dict[int, float]]] = {}
        for _, row in df.iterrows():
            h = int(row["hero_id"])
            cur = int(row["item_current"])
            nxt = int(row["item_next"])
            p = float(row["trans_prob"])
            hero_map.setdefault(h, {}).setdefault(cur, {})[nxt] = p

        # Also build a global fallback using aggregated counts
        gdf = con.execute(
            """
            SELECT item_current, item_next, SUM(trans_prob) AS sum_prob
            FROM item_transition_stats
            GROUP BY item_current, item_next
            """
        ).df()

        global_map: dict[int, dict[int, float]] = {}
        for cur, grp in gdf.groupby("item_current"):
            total = grp["sum_prob"].sum()
            cur_map: dict[int, float] = {}
            for _, row in grp.iterrows():
                nxt = int(row["item_next"])
                p = float(row["sum_prob"]) / float(total)
                cur_map[nxt] = p
            global_map[int(cur)] = cur_map

        return hero_map, global_map

    # ------------------------------------------------------------------
    # Item stats merging & preprocessing
    # ------------------------------------------------------------------
    def merge_item_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        ig = self.item_global_stats
        hi = self.hero_item_stats

        df = df.merge(ig, on="item_id", how="left")
        df = df.merge(hi, on=["hero_id", "item_id"], how="left")

        df["item_global_wr"] = df["item_global_wr"].fillna(50.0)
        df["hero_item_wr"] = df["hero_item_wr"].fillna(df["item_global_wr"])
        return df

    def preprocess_for_inference(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Encode categorical columns & cast numerics according to training metadata.
        """
        df = df.copy()

        # Team encoding
        if "team" in df.columns:
            df["team"] = df["team"].map({"Team0": 0, "Team1": 1}).astype("int8")

        # Assigned lane
        if "assigned_lane" in df.columns:
            df["assigned_lane"] = df["assigned_lane"].astype("int8")

        # Hero / item / lane_opponent
        if "hero_id" in df.columns:
            df["hero_id"] = df["hero_id"].astype("int16")
        if "item_id" in df.columns:
            df["item_id"] = df["item_id"].astype("int32")
        if "lane_opponent" in df.columns:
            df["lane_opponent"] = df["lane_opponent"].fillna(-1).astype("int16")

        # Numeric features -> float32
        for col in self.numeric_features:
            if col in df.columns:
                df[col] = df[col].astype("float32")

        # Keep only feature columns; fill missing with 0
        cols = [c for c in self.features if c in df.columns]
        df = df[cols].fillna(0.0)

        return df

    # ------------------------------------------------------------------
    # Draft context + recommendation
    # ------------------------------------------------------------------
    def _global_match_stats(self) -> dict:
        row = self.con.execute(
            """
            SELECT
                AVG(duration_s)  AS avg_duration_s,
                AVG(team0_tier)  AS avg_team0_tier,
                AVG(team1_tier)  AS avg_team1_tier
            FROM match_info
            """
        ).df().iloc[0]
        return row.to_dict()

    def _build_inference_context_row(
        self,
        hero_id: int,
        lane_ally_id: int,
        team_other_ids: list[int],
        lane_enemy_ids: list[int],
        enemy_other_ids: list[int],
    ) -> pd.DataFrame:
        """
        Build a single hero-context row from the current draft.
        """

        assert len(team_other_ids) == 4, "Expected 4 non-lane allies."
        assert len(lane_enemy_ids) == 2, "Expected 2 lane enemies."
        assert len(enemy_other_ids) == 4, "Expected 4 non-lane enemies."

        ally_ids = [lane_ally_id] + team_other_ids
        enemy_ids = lane_enemy_ids + enemy_other_ids

        # 1) Lane performance snapshot for this hero
        snap_row = self.con.execute(
            """
            SELECT
                AVG(souls_9m) AS souls_9m,
                AVG(cs_9m)    AS cs_9m,
                AVG(kills_9m) AS kills_9m
            FROM hero_lane_snap_9
            WHERE hero_id = ?
            """,
            [hero_id],
        ).df().iloc[0]

        souls_9m = _safe_get(snap_row["souls_9m"], 0.0)
        cs_9m = _safe_get(snap_row["cs_9m"], 0.0)
        kills_9m = _safe_get(snap_row["kills_9m"], 0.0)

        # 2) Synergy vs allies
        placeholders = ",".join(["?"] * len(ally_ids))
        sy_df = self.con.execute(
            f"""
            SELECT hero1, hero2, winrate
            FROM hero_synergy
            WHERE (hero1 = ? AND hero2 IN ({placeholders}))
               OR (hero2 = ? AND hero1 IN ({placeholders}))
            """,
            [hero_id, *ally_ids, hero_id, *ally_ids],
        ).df()

        sy_map: dict[int, float] = {}
        for _, row in sy_df.iterrows():
            h1, h2, wr = int(row["hero1"]), int(row["hero2"]), float(row["winrate"])
            other = h2 if h1 == hero_id else h1
            sy_map[other] = wr

        sy_vals = [sy_map.get(aid, 50.0) for aid in ally_ids] or [50.0]
        synergy_avg = float(np.mean(sy_vals))
        synergy_max = float(np.max(sy_vals))
        synergy_sum = float(np.sum(sy_vals))
        synergy_strong_count = float(np.sum(np.array(sy_vals) >= 55.0))

        # 3) Counter vs enemies
        placeholders = ",".join(["?"] * len(enemy_ids))
        ct_df = self.con.execute(
            f"""
            SELECT enemy, winrate
            FROM hero_counter
            WHERE hero = ? AND enemy IN ({placeholders})
            """,
            [hero_id, *enemy_ids],
        ).df()

        ct_map = {int(r["enemy"]): float(r["winrate"]) for _, r in ct_df.iterrows()}
        ct_vals = [ct_map.get(eid, 50.0) for eid in enemy_ids] or [50.0]

        counter_avg = float(np.mean(ct_vals))
        counter_max = float(np.max(ct_vals))
        counter_sum = float(np.sum(ct_vals))
        counter_hard_count = float(np.sum(np.array(ct_vals) <= 45.0))

        # 4) Lane matchup vs the two lane enemies
        placeholders_lane = ",".join(["?"] * len(lane_enemy_ids))
        lane_df = self.con.execute(
            f"""
            SELECT opponent, avg_soul_diff, avg_souls_raw, tower_rate
            FROM hero_soul_matchup
            WHERE hero = ? AND opponent IN ({placeholders_lane})
            """,
            [hero_id, *lane_enemy_ids],
        ).df()

        if len(lane_df) == 0:
            lane_opponent = -1
            avg_soul_diff = 0.0
            avg_souls_raw = 0.0
            lane_tower_rate = 0.5
        else:
            worst_idx = lane_df["avg_soul_diff"].idxmin()
            lane_opponent = int(lane_df.loc[worst_idx, "opponent"])
            avg_soul_diff = float(lane_df["avg_soul_diff"].mean())
            avg_souls_raw = float(lane_df["avg_souls_raw"].mean())
            lane_tower_rate = float(lane_df["tower_rate"].mean())

        # 5) Global match stats
        gstats = self._global_match_stats()
        duration_s = _safe_get(gstats["avg_duration_s"], 1800.0)
        team0_tier = _safe_get(gstats["avg_team0_tier"], PHANTOM_TIER)
        team1_tier = _safe_get(gstats["avg_team1_tier"], PHANTOM_TIER)

        ctx = {
            "match_id": 0,
            "phase": "unknown",
            "hero_id": int(hero_id),
            "item_id": -1,
            "team": "Team0",
            "assigned_lane": 1,
            "duration_s": float(duration_s),
            "souls_9m": float(souls_9m),
            "cs_9m": float(cs_9m),
            "kills_9m": float(kills_9m),
            "lane_adv_signed": 0.0,
            "team0_tier": float(team0_tier),
            "team1_tier": float(team1_tier),
            "synergy_avg": synergy_avg,
            "synergy_max": synergy_max,
            "synergy_sum": synergy_sum,
            "synergy_strong_count": synergy_strong_count,
            "counter_avg": counter_avg,
            "counter_max": counter_max,
            "counter_sum": counter_sum,
            "counter_hard_count": counter_hard_count,
            "lane_opponent": lane_opponent,
            "avg_soul_diff": avg_soul_diff,
            "avg_souls_raw": avg_souls_raw,
            "lane_tower_rate": lane_tower_rate,
        }

        return pd.DataFrame([ctx])

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    def _get_transition_prob(self, hero_id: int, item_current: int, item_next: int):
        hmap = self.transition_hero.get(int(hero_id), {})
        if item_current in hmap and item_next in hmap[item_current]:
            return hmap[item_current][item_next]
        gmap = self.transition_global.get(int(item_current), {})
        if item_next in gmap:
            return gmap[item_next]
        return 0.01

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def recommend_build(
        self,
        hero_id: int,
        lane_ally_id: int,
        team_other_ids: list[int],
        lane_enemy_ids: list[int],
        enemy_other_ids: list[int],
        top_k_per_phase: int = 10,
        lambda_by_phase: dict[str, float] | None = None,
        slots_per_phase: dict[str, int] | None = None,
        candidate_top_n: int = 30,
    ) -> dict[str, list[dict]]:
        """
        Main entrypoint: recommend items per phase for a given draft.
        """
        if lambda_by_phase is None:
            lambda_by_phase = {
                ph: DEFAULT_LAMBDA_PER_PHASE.get(ph, 0.3)
                for ph in self.phases
            }

        if slots_per_phase is None:
            slots_per_phase = DEFAULT_SLOTS_PER_PHASE

        # 1) Context row
        ctx_df = self._build_inference_context_row(
            hero_id=hero_id,
            lane_ally_id=lane_ally_id,
            team_other_ids=team_other_ids,
            lane_enemy_ids=lane_enemy_ids,
            enemy_other_ids=enemy_other_ids,
        )

        # 2) Item metadata
        items_df = self.con.execute(
            """
            SELECT
                si.id   AS item_id,
                si.name AS item_name,
                si.tier,
                si.cost,
                ia.shop_image,
                ia.shop_image_webp,
                ia.item_slot_type
            FROM shop_items si
            LEFT JOIN item_assets ia
                   ON ia.item_id = si.id
            """
        ).df()

        # 3) Repeat context rows per item
        base = ctx_df.loc[ctx_df.index.repeat(len(items_df))].reset_index(drop=True)
        base["item_id"] = items_df["item_id"].values

        base = self.merge_item_stats(base)
        X_base = self.preprocess_for_inference(base)

        # 4) Score per phase using core XGBoost Booster API
        dmat = xgb.DMatrix(X_base)  # X_base is a pandas DataFrame

        for phase in self.phases:
            booster = self.models[phase]
            scores = booster.predict(dmat)
            items_df[f"score_{phase}"] = scores

        items_df["hero_id"] = hero_id
        items_df = self.merge_item_stats(items_df)

        # 5) Build coherent sequence with transitions
        sequence_by_phase = self._build_sequence_with_transitions(
            hero_id=hero_id,
            items_df=items_df,
            slots_per_phase=slots_per_phase,
            lambda_by_phase=lambda_by_phase,
            candidate_top_n=candidate_top_n,
        )

        # 6) Truncate to top_k_per_phase
        out: dict[str, list[dict]] = {}
        for phase in self.phases:
            phase_items = sequence_by_phase.get(phase, [])[:top_k_per_phase]
            out[phase] = phase_items

        return out

    def _build_sequence_with_transitions(
        self,
        hero_id: int,
        items_df: pd.DataFrame,
        slots_per_phase: dict[str, int],
        lambda_by_phase: dict[str, float],
        candidate_top_n: int,
    ) -> dict[str, list[dict]]:
        """
        Greedy sequence builder using per-phase scores + transition stats.

        Also attaches explanation fields such as:
          - phase_rank / phase_percentile
          - hero_item_wr / item_global_wr / synergy_delta_wr
          - transition_prob_from_prev
          - order_in_phase / order_global / total_score
        """
        rank_maps: dict[str, pd.DataFrame] = {}
        for ph in self.phases:
            score_col = f"score_{ph}"
            if score_col not in items_df.columns:
                continue

            df_scores = items_df[["item_id", score_col]].copy()
            df_scores = df_scores.sort_values(score_col, ascending=False)
            df_scores["phase_rank"] = np.arange(len(df_scores)) + 1
            df_scores["phase_percentile"] = (
                1.0 - (df_scores["phase_rank"] - 1) / len(df_scores)
            )

            rank_maps[ph] = df_scores.set_index("item_id")[
                ["phase_rank", "phase_percentile"]
            ]

        phase_order: list[str] = []
        for ph in self.phases:
            phase_order.extend([ph] * slots_per_phase.get(ph, 0))

        chosen_ids: set[int] = set()
        sequence: list[int] = []

        for phase in phase_order:
            score_col = f"score_{phase}"
            lam = lambda_by_phase.get(phase, 0.3)

            cand = items_df[~items_df["item_id"].isin(chosen_ids)].copy()
            if score_col not in cand.columns:
                continue

            cand = cand.sort_values(score_col, ascending=False).head(candidate_top_n)
            if cand.empty:
                break

            best_item = None
            best_score = -1e9

            for _, row in cand.iterrows():
                item_id = int(row["item_id"])
                base_score = float(row[score_col])
                if base_score <= 0:
                    continue

                log_base = float(np.log(base_score + 1e-8))

                if not sequence:
                    log_trans = 0.0
                else:
                    prev_item = sequence[-1]
                    p_trans = self._get_transition_prob(hero_id, prev_item, item_id)
                    log_trans = float(np.log(p_trans + 1e-6))

                total = log_base + lam * log_trans
                if total > best_score:
                    best_score = total
                    best_item = item_id

            if best_item is None:
                break

            sequence.append(best_item)
            chosen_ids.add(best_item)

        # ------------------------------------------------------------------
        # Split into phases and pack metadata
        # ------------------------------------------------------------------
        results: dict[str, list[dict]] = {ph: [] for ph in self.phases}
        idx = 0
        prev_item_id: int | None = None

        for ph in self.phases:
            slots = slots_per_phase.get(ph, 0)
            score_col = f"score_{ph}"
            lam = lambda_by_phase.get(ph, 0.3)

            for slot_idx in range(slots):
                if idx >= len(sequence):
                    break

                iid = sequence[idx]
                row = items_df[items_df["item_id"] == iid].iloc[0]

                base_score = float(_safe_get(row.get(score_col), 0.0))

                if prev_item_id is None:
                    trans_prob = None
                    # no previous item; treat total_score as just log(base_score)
                    if base_score > 0:
                        total_score = float(np.log(base_score + 1e-8))
                    else:
                        total_score = float("-inf")
                else:
                    trans_prob = float(
                        self._get_transition_prob(hero_id, prev_item_id, iid)
                    )
                    if base_score > 0:
                        log_base = float(np.log(base_score + 1e-8))
                    else:
                        log_base = float(-1e8)
                    log_trans = float(np.log(trans_prob + 1e-6))
                    total_score = log_base + lam * log_trans

                phase_rank = None
                phase_percentile = None
                rank_df = rank_maps.get(ph)
                if rank_df is not None and iid in rank_df.index:
                    rank_row = rank_df.loc[iid]
                    phase_rank = int(rank_row["phase_rank"])
                    phase_percentile = float(rank_row["phase_percentile"])

                hero_wr = float(
                    _safe_get(row.get("hero_item_wr"), row.get("item_global_wr"))
                )
                global_wr = float(
                    _safe_get(row.get("item_global_wr"), hero_wr)
                )
                synergy_delta = hero_wr - global_wr

                results[ph].append(
                    {
                        "item_id": int(row["item_id"]),
                        "name": row["item_name"],
                        "tier": int(_safe_get(row.get("tier"), 0)),
                        "cost": int(_safe_get(row.get("cost"), 0)),
                        # keep "score" as the raw phase score for backwards-compat
                        "score": base_score,
                        "shop_image": row.get("shop_image"),
                        "shop_image_webp": row.get("shop_image_webp"),
                        "item_slot_type": row.get("item_slot_type"),

                        "phase_rank": phase_rank,
                        "phase_percentile": phase_percentile,
                        "hero_item_wr": hero_wr,
                        "item_global_wr": global_wr,
                        "synergy_delta_wr": synergy_delta,
                        "transition_prob_from_prev": trans_prob,
                        "order_in_phase": slot_idx,
                        "order_global": idx,
                        "total_score": total_score,
                    }
                )

                prev_item_id = iid
                idx += 1

        return results


# ----------------------------------------------------------------------
# Convenience functions for loading bundle from dir/zip
# ----------------------------------------------------------------------
def load_bundle_from_dir(bundle_dir: Path) -> InferenceBundle:
    """
    Given exports/<model_version>/models directory, load an InferenceBundle.
    """
    models_dir = bundle_dir
    if (models_dir / "models").is_dir():
        models_dir = models_dir / "models"
    return InferenceBundle.from_dir(models_dir)


def load_bundle_from_zip(zip_path: Path, extract_dir: Path) -> InferenceBundle:
    """
    Given a zip file path, extract it to extract_dir and load bundle.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    models_dir = extract_dir / "models"
    return InferenceBundle.from_dir(models_dir)


def recommend_build_from_bundle(bundle: InferenceBundle, payload: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """
    Small wrapper suitable for a Lambda handler.

    Expected payload structure:

    {
      "hero_id": int,
      "lane_ally_id": int,
      "team_other_ids": [int, int, int, int],
      "lane_enemy_ids": [int, int],
      "enemy_other_ids": [int, int, int, int],
      "top_k_per_phase": 8
    }
    """
    return bundle.recommend_build(
        hero_id=int(payload["hero_id"]),
        lane_ally_id=int(payload["lane_ally_id"]),
        team_other_ids=[int(x) for x in payload["team_other_ids"]],
        lane_enemy_ids=[int(x) for x in payload["lane_enemy_ids"]],
        enemy_other_ids=[int(x) for x in payload["enemy_other_ids"]],
        top_k_per_phase=int(payload.get("top_k_per_phase", 8)),
    )
