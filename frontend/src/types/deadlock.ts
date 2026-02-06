
// Hero asset coming from /api/heroes (Lambda → S3 hero_assets.json)
export interface HeroAsset {
  hero_id: number;
  hero_name: string;
  hero_image: string | null;
  hero_image_webp: string | null;
}

// Phases in the recommendation response
export type PhaseKey = "early" | "mid" | "late" | "very_late";

// Single item in a given phase
export interface RecommendedItem {
  item_id: number;
  name: string;
  tier: number;
  cost: number;
  score: number;
  shop_image: string | null;
  shop_image_webp: string | null;
  item_slot_type: string | null;

  // NEW fields from backend attribution
  phase_rank: number | null;
  phase_percentile: number | null;   // 0–1
  hero_item_wr: number;
  item_global_wr: number;
  synergy_delta_wr: number;
  transition_prob_from_prev: number | null;
  order_in_phase: number;
  order_global: number;
  total_score: number | null;
}


// Map of phase → list of items
export type RecommendationsByPhase = {
  [P in PhaseKey]?: RecommendedItem[];
};

// Payload we send to /api/recommend
export interface RecommendPayload {
  hero_id: number;
  lane_ally_id: number;
  team_other_ids: number[];
  lane_enemy_ids: number[];
  enemy_other_ids: number[];
  // optional: how many items per phase to return
  top_k_per_phase?: number;
}

export interface MetadataPayload {
  model_version: string;
  matches_analyzed: number;
  players_sampled: number;
  date_from: string;
  date_to: string;
  hero_count: number;
  item_count: number;
}
