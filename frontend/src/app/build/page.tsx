/* eslint-disable @next/next/no-img-element */
"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState, useRef } from "react";;
import type {
  HeroAsset,
  PhaseKey,
  RecommendedItem,
  RecommendationsByPhase,
  RecommendPayload,
} from "@/types/deadlock";
import { trackEvent } from "@/lib/analytics";

type BuildPhase = PhaseKey;

type ContextRole = "you" | "laneAlly" | "ally" | "laneEnemy" | "enemy";

interface RecommendResponse {
  model_version: string;
  recommendations: RecommendationsByPhase;
}

type SelectionStage =
  | "hero"
  | "laneAlly"
  | "teamOthers"
  | "laneEnemies"
  | "enemyOthers";

const PHASE_LABELS: Record<BuildPhase, string> = {
  early: "Early Game",
  mid: "Mid Game",
  late: "Late Game",
  very_late: "Very Late Game",
};

// 6v6: hero + laneAlly + 4 other allies, 2 lane enemies + 4 other enemies
const MAX_TEAM_OTHERS = 4;
const MAX_LANE_ENEMIES = 2;
const MAX_ENEMY_OTHERS = 4;

const STAGE_META: Record<SelectionStage, { label: string; roleClass: string }> =
  {
    hero: { label: "You", roleClass: "selection-step--you" },
    laneAlly: { label: "Lane Ally", roleClass: "selection-step--laneAlly" },
    teamOthers: { label: "Allies", roleClass: "selection-step--allies" },
    laneEnemies: {
      label: "Lane Enemies",
      roleClass: "selection-step--laneEnemies",
    },
    enemyOthers: { label: "Enemy Team", roleClass: "selection-step--enemies" },
  };

function stageHeading(stage: SelectionStage): string {
  switch (stage) {
    case "hero":
      return "Select Hero";
    case "laneAlly":
      return "Select Lane Ally";
    case "teamOthers":
      return "Select Allies";
    case "laneEnemies":
      return "Select Lane Enemies";
    case "enemyOthers":
      return "Select Enemy Team";
    default:
      return "Select Hero";
  }
}

function getStageCounts(
  stage: SelectionStage,
  heroId: number | null,
  laneAllyId: number | null,
  teamOtherIds: number[],
  laneEnemyIds: number[],
  enemyOtherIds: number[]
): { current: number; required: number } {
  switch (stage) {
    case "hero":
      return { current: heroId ? 1 : 0, required: 1 };
    case "laneAlly":
      return { current: laneAllyId ? 1 : 0, required: 1 };
    case "teamOthers":
      return { current: teamOtherIds.length, required: MAX_TEAM_OTHERS };
    case "laneEnemies":
      return { current: laneEnemyIds.length, required: MAX_LANE_ENEMIES };
    case "enemyOthers":
      return { current: enemyOtherIds.length, required: MAX_ENEMY_OTHERS };
  }
}

/* Deadlock-style Roman numerals for tiers */
const TIER_ROMAN: Record<number, string> = {
  1: "I",
  2: "II",
  3: "III",
  4: "IV",
  5: "V",
};

function tierToRoman(tier: number | null | undefined): string {
  if (!tier || tier <= 0) return "";
  return TIER_ROMAN[tier] ?? String(tier);
}

/** Format a value that might be 0–1 or 0–100 as a percentage string */
function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const v = value <= 1 ? value * 100 : value;
  return `${v.toFixed(1)}%`;
}

/** Format a 0–1 or 0–100 percentile as e.g. "97th" */
function formatPercentile(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const v = value <= 1 ? value * 100 : value;
  return `${Math.round(v)}th`;
}

/** Inline style for the name bar based on item_slot_type */
function getSlotNameBarStyle(
  slotType: string | null | undefined
): CSSProperties | undefined {

  if (!slotType) return undefined;

  switch (slotType) {
    case "spirit": {
      const base = "138,85,179";
      return {
        background: `rgba(${base},0.35)`,
        borderTopColor: `rgba(${base},1)`,
        borderBottomColor: `rgba(${base},1)`,
      };
    }
    case "weapon": {
      const base = "229,138,0";
      return {
        background: `rgba(${base},0.35)`,
        borderTopColor: `rgba(${base},1)`,
        borderBottomColor: `rgba(${base},1)`,
      };
    }
    case "vitality": {
      const base = "0,255,153";
      return {
        background: `rgba(${base},0.35)`,
        borderTopColor: `rgba(${base},1)`,
        borderBottomColor: `rgba(${base},1)`,
      };
    }
    default:
      return undefined;
  }
}

function hardScrollToTop() {
  if (typeof window === "undefined") return;

  // main scroll
  window.scrollTo({ top: 0, behavior: "auto" });

  if (typeof document !== "undefined") {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }
}

export default function BuildPage() {
  const recommendationTopRef = useRef<HTMLDivElement | null>(null);

  // ---------- HERO DATA ----------
  const [heroes, setHeroes] = useState<HeroAsset[]>([]);
  const [isLoadingHeroes, setIsLoadingHeroes] = useState(false);
  const [heroesError, setHeroesError] = useState<string | null>(null);

  // ---------- SELECTION STATE ----------
  const [stage, setStage] = useState<SelectionStage>("hero");

  const [heroId, setHeroId] = useState<number | null>(null);
  const [laneAllyId, setLaneAllyId] = useState<number | null>(null);
  const [teamOtherIds, setTeamOtherIds] = useState<number[]>([]);
  const [laneEnemyIds, setLaneEnemyIds] = useState<number[]>([]);
  const [enemyOtherIds, setEnemyOtherIds] = useState<number[]>([]);

  // ---------- RECOMMENDATION STATE ----------
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [recommendation, setRecommendation] =
    useState<RecommendResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showBuildView, setShowBuildView] = useState(false);

  const [showItemStats, setShowItemStats] = useState(false);

  // ---------- BUILD CONTEXT SUMMARY ----------

  function getHeroById(id: number | null): HeroAsset | null {
    if (id == null) return null;
    return heroes.find((h) => h.hero_id === id) ?? null;
  }

  function renderContextCell(
    hero: HeroAsset | null,
    key: string,
    tag: string | null,
    role: ContextRole | null
  ) {
    const baseClass = "build-context-cell";
    const roleClass = role ? ` build-context-cell--${role}` : "";

    if (!hero) {
      return (
        <div key={key} className={baseClass + " build-context-cell--empty"} />
      );
    }

    const imgSrc = hero.hero_image_webp || hero.hero_image || "";

    return (
      <div key={key} className={baseClass + roleClass}>
        <div className="build-context-cell-image">
          {imgSrc && <img src={imgSrc} alt={hero.hero_name} loading="lazy" />}
          <div className="build-context-cell-overlay">
            {tag && <div className="build-context-cell-tag">{tag}</div>}
            <div className="build-context-cell-name">{hero.hero_name}</div>
          </div>
        </div>
      </div>
    );
  }

  function renderSelectionSummary() {
    if (!heroes.length) return null;

    const youHero = getHeroById(heroId);
    const laneAllyHero = getHeroById(laneAllyId);
    const teamOtherHeroes = teamOtherIds
      .map((id) => getHeroById(id))
      .filter((h): h is HeroAsset => Boolean(h));
    const laneEnemyHeroes = laneEnemyIds
      .map((id) => getHeroById(id))
      .filter((h): h is HeroAsset => Boolean(h));
    const enemyOtherHeroes = enemyOtherIds
      .map((id) => getHeroById(id))
      .filter((h): h is HeroAsset => Boolean(h));

    const anythingSelected =
      youHero ||
      laneAllyHero ||
      teamOtherHeroes.length ||
      laneEnemyHeroes.length ||
      enemyOtherHeroes.length;

    if (!anythingSelected) return null;

    // YOUR TEAM: YOU | LANE | ALLY | ALLY | ALLY | ALLY
    const yourTeamSlots: React.ReactNode[] = [];
    yourTeamSlots.push(
      renderContextCell(youHero, "your-you", youHero ? "YOU" : null, "you")
    );
    yourTeamSlots.push(
      renderContextCell(
        laneAllyHero,
        "your-lane",
        laneAllyHero ? "LANE" : null,
        "laneAlly"
      )
    );
    for (let i = 0; i < MAX_TEAM_OTHERS; i++) {
      const hero = teamOtherHeroes[i] ?? null;
      yourTeamSlots.push(
        renderContextCell(
          hero,
          `your-ally-${i}`,
          hero ? "ALLY" : null,
          hero ? "ally" : null
        )
      );
    }

    // ENEMY TEAM: LANE | LANE | ENEMY | ENEMY | ENEMY | ENEMY
    const enemyTeamSlots: React.ReactNode[] = [];
    for (let i = 0; i < MAX_LANE_ENEMIES; i++) {
      const hero = laneEnemyHeroes[i] ?? null;
      enemyTeamSlots.push(
        renderContextCell(
          hero,
          `enemy-lane-${i}`,
          hero ? "LANE" : null,
          hero ? "laneEnemy" : null
        )
      );
    }
    for (let i = 0; i < MAX_ENEMY_OTHERS; i++) {
      const hero = enemyOtherHeroes[i] ?? null;
      enemyTeamSlots.push(
        renderContextCell(
          hero,
          `enemy-${i}`,
          hero ? "ENEMY" : null,
          hero ? "enemy" : null
        )
      );
    }

    return (
      <div className="build-context-strip">
        <div className="build-context-group">
          <div className="build-context-grid">{yourTeamSlots}</div>
          <div className="build-context-row-label">Your Team</div>
        </div>

        <div className="build-context-group">
          <div className="build-context-grid">{enemyTeamSlots}</div>
          <div className="build-context-row-label">Enemy Team</div>
        </div>
      </div>
    );
  }

  // ---------- FETCH HEROES VIA /api/heroes ----------
  useEffect(() => {
    let cancelled = false;

    async function loadHeroes() {
      try {
        setIsLoadingHeroes(true);
        setHeroesError(null);

        const res = await fetch("/api/heroes");
        if (!res.ok) {
          throw new Error(`GET /api/heroes failed: ${res.status}`);
        }

        const data = await res.json();
        const heroesData: HeroAsset[] = data.heroes ?? data;

        if (!cancelled) {
          const sorted = [...heroesData].sort((a, b) =>
            a.hero_name.localeCompare(b.hero_name)
          );
          setHeroes(sorted);
        }
      } catch (err) {
        console.error("Error loading heroes:", err);
        if (!cancelled) {
          setHeroesError("Failed to load heroes. Please refresh.");
        }
      } finally {
        if (!cancelled) setIsLoadingHeroes(false);
      }
    }

    loadHeroes();
    return () => {
      cancelled = true;
    };
  }, []);

  // ---------- SELECTION HELPERS ----------

  const usedHeroIds = useMemo(() => {
    const set = new Set<number>();
    if (heroId != null) set.add(heroId);
    if (laneAllyId != null) set.add(laneAllyId);
    for (const id of teamOtherIds) set.add(id);
    for (const id of laneEnemyIds) set.add(id);
    for (const id of enemyOtherIds) set.add(id);
    return set;
  }, [heroId, laneAllyId, teamOtherIds, laneEnemyIds, enemyOtherIds]);

  function resetAll() {
    setHeroId(null);
    setLaneAllyId(null);
    setTeamOtherIds([]);
    setLaneEnemyIds([]);
    setEnemyOtherIds([]);
    setStage("hero");
    setRecommendation(null);
    setSubmitError(null);
    setShowBuildView(false);
  }

  function handleStageClick(next: SelectionStage) {
    setStage(next);
    setShowBuildView(false);
  }

  function handleHeroClick(id: number) {
    // 1. If this hero is already selected for the current stage, unselect it.
    if (stage === "hero" && heroId === id) {
      setHeroId(null);
      return;
    }

    if (stage === "laneAlly" && laneAllyId === id) {
      setLaneAllyId(null);
      return;
    }

    if (stage === "teamOthers" && teamOtherIds.includes(id)) {
      setTeamOtherIds((prev) => prev.filter((x) => x !== id));
      return;
    }

    if (stage === "laneEnemies" && laneEnemyIds.includes(id)) {
      setLaneEnemyIds((prev) => prev.filter((x) => x !== id));
      return;
    }

    if (stage === "enemyOthers" && enemyOtherIds.includes(id)) {
      setEnemyOtherIds((prev) => prev.filter((x) => x !== id));
      return;
    }

    // 2. Don't allow reusing a hero assigned to another role.
    if (usedHeroIds.has(id)) {
      return;
    }

    // 3. Normal assignment + auto-advance behaviour.
    if (stage === "hero") {
      setHeroId(id);
      setStage("laneAlly");
      return;
    }

    if (stage === "laneAlly") {
      setLaneAllyId(id);
      setStage("teamOthers");
      return;
    }

    if (stage === "teamOthers") {
      setTeamOtherIds((prev) => {
        if (prev.length >= MAX_TEAM_OTHERS) return prev;
        const next = [...prev, id];
        if (next.length === MAX_TEAM_OTHERS) setStage("laneEnemies");
        return next;
      });
      return;
    }

    if (stage === "laneEnemies") {
      setLaneEnemyIds((prev) => {
        if (prev.length >= MAX_LANE_ENEMIES) return prev;
        const next = [...prev, id];
        if (next.length === MAX_LANE_ENEMIES) setStage("enemyOthers");
        return next;
      });
      return;
    }

    if (stage === "enemyOthers") {
      setEnemyOtherIds((prev) => {
        if (prev.length >= MAX_ENEMY_OTHERS) return prev;
        const next = [...prev, id];
        return next;
      });
      return;
    }
  }

  function badgeForHero(heroIdValue: number): string | null {
    if (heroId === heroIdValue) return "You";
    if (laneAllyId === heroIdValue) return "Lane Ally";
    if (teamOtherIds.includes(heroIdValue)) return "Ally";
    if (laneEnemyIds.includes(heroIdValue)) return "Lane Enemy";
    if (enemyOtherIds.includes(heroIdValue)) return "Enemy";
    return null;
  }

  function roleClassForHero(heroIdValue: number): string | null {
    if (heroId === heroIdValue) return "role-you";
    if (laneAllyId === heroIdValue) return "role-laneAlly";
    if (teamOtherIds.includes(heroIdValue)) return "role-ally";
    if (laneEnemyIds.includes(heroIdValue)) return "role-laneEnemy";
    if (enemyOtherIds.includes(heroIdValue)) return "role-enemy";
    return null;
  }

  const canSubmit =
    heroId != null &&
    laneAllyId != null &&
    teamOtherIds.length === MAX_TEAM_OTHERS &&
    laneEnemyIds.length === MAX_LANE_ENEMIES &&
    enemyOtherIds.length === MAX_ENEMY_OTHERS;

  // ---------- CALL /api/recommend ----------

  async function handleRecommendClick() {
    if (!canSubmit) return;

    try {
      setIsSubmitting(true);
      setSubmitError(null);
      setRecommendation(null);
      setShowBuildView(false);

      const payload: RecommendPayload = {
        hero_id: heroId!, 
        lane_ally_id: laneAllyId!,
        team_other_ids: teamOtherIds,
        lane_enemy_ids: laneEnemyIds,
        enemy_other_ids: enemyOtherIds,
        top_k_per_phase: 8,
      };

      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errBody = (await res.json().catch(() => null)) as unknown;

        let apiErrorMessage: string | undefined;
        if (
          errBody &&
          typeof errBody === "object" &&
          "error" in errBody &&
          typeof (errBody as { error?: unknown }).error === "string"
        ) {
          apiErrorMessage = (errBody as { error?: string }).error;
        }

        const msg =
          apiErrorMessage ?? `Recommendation failed with status ${res.status}`;
        throw new Error(msg);
      }

      const data: RecommendResponse = await res.json();
      setRecommendation(data);
      setShowBuildView(true);
    } catch (err: unknown) {
      console.error("Error requesting recommendation:", err);
      const message =
        err instanceof Error ? err.message : "Failed to get recommendation.";
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleBackFromBuild() {
    setShowBuildView(false);
    hardScrollToTop();
  }

  const handleRecommendClickWithTracking = () => {
    hardScrollToTop();
    trackEvent("recommend_build_click", {
      category: "recommendation",
      location: "build_page",
    });
    handleRecommendClick(); 
  };

  // ---------- RENDER HELPERS ----------

  function renderHeroGrid() {
    if (isLoadingHeroes) {
      const skeletonCount = 35;
      return (
        <div className="hero-grid hero-grid--skeleton">
          {Array.from({ length: skeletonCount }).map((_, idx) => (
            <div key={idx} className="hero-skeleton-tile">
              <div className="hero-skeleton-image" />
              <div className="hero-skeleton-name" />
            </div>
          ))}
        </div>
      );
    }
    if (heroesError) return <p style={{ color: "#f97373" }}>{heroesError}</p>;
    if (!heroes.length) return <p>No heroes available.</p>;

    return (
      <div className="hero-grid">
        {/* Fullscreen video background */}
        <video
          className="bg-video"
          src="/video/roster_bg_loop.webm"
          autoPlay
          muted
          loop
          playsInline
        />

        {heroes.map((hero) => {
          const imgSrc = hero.hero_image_webp || hero.hero_image || "";
          const roleClass = roleClassForHero(hero.hero_id);
          const assigned = usedHeroIds.has(hero.hero_id);
          const badge = badgeForHero(hero.hero_id);

          const isActiveRole =
            (stage === "hero" && heroId === hero.hero_id) ||
            (stage === "laneAlly" && laneAllyId === hero.hero_id) ||
            (stage === "teamOthers" && teamOtherIds.includes(hero.hero_id)) ||
            (stage === "laneEnemies" && laneEnemyIds.includes(hero.hero_id)) ||
            (stage === "enemyOthers" && enemyOtherIds.includes(hero.hero_id));

          const className =
            "hero-card" +
            (assigned ? " assigned" : "") +
            (roleClass ? ` ${roleClass}` : "") +
            (isActiveRole ? " hero-card--active-role" : "");

          return (
            <button
              key={hero.hero_id}
              type="button"
              className={className}
              onClick={() => handleHeroClick(hero.hero_id)}
            >
              {/* Flame background layer */}
              <div className="hero-card-bg">
                <video
                  className="hero-card-bg-video"
                  src="/video/card_flame.webm"
                  autoPlay
                  muted
                  loop
                  playsInline
                />
              </div>

              {/* Hero portrait */}
              {imgSrc ? (
                <img src={imgSrc} alt={hero.hero_name} loading="lazy" />
              ) : (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.7rem",
                    color: "var(--text-muted)",
                    padding: "4px",
                    textAlign: "center",
                  }}
                >
                  {hero.hero_name}
                </div>
              )}

              {badge && <span className="hero-card-badge">{badge}</span>}

              <span className="hero-card-name">
                {hero.hero_name.toUpperCase()}
              </span>
            </button>
          );
        })}
      </div>
    );
  }

  function renderRecommendations() {
    if (!recommendation) {
      return (
        <p style={{ color: "var(--text-muted)" }}>
          No recommendation loaded. Go back and run{" "}
          <strong>Recommend Build</strong>.
        </p>
      );
    }

    const recs = recommendation.recommendations;

    return (
      <>
        <div className="recommendation-phases">
          {(Object.keys(PHASE_LABELS) as BuildPhase[]).map((phase) => {
            const items: RecommendedItem[] = recs[phase] ?? [];
            return (
              <div key={phase} className="recommendation-phase-row">
                <div className="recommendation-phase-header-strip">
                  <div className="recommendation-phase-header">
                    {PHASE_LABELS[phase]}
                  </div>
                </div>

                <div className="recommendation-items-row">
                  {items.length === 0 ? (
                    <div className="recommendation-empty">
                      No items for this phase.
                    </div>
                  ) : (
                    items.map((item) => {
                      const img = item.shop_image_webp || item.shop_image || "";

                      let tier: number | undefined;
                      if (
                        "tier" in item &&
                        typeof (item as { tier?: unknown }).tier === "number"
                      ) {
                        tier = (item as { tier?: number }).tier;
                      }

                      const romanTier = tierToRoman(tier ?? null);

                      const cardClass =
                        "item-card" + (tier ? ` item-card--tier-${tier}` : "");

                      const nameBarStyle = getSlotNameBarStyle(
                        item.item_slot_type ?? null
                      );

                      // ─────────────────────────────
                      // SIMPLE VIEW
                      // ─────────────────────────────
                      if (!showItemStats) {
                        return (
                          <div key={item.item_id} className={cardClass}>
                            <div className="item-card-visual">
                              <div className="item-card-art">
                                {img && (
                                  <img
                                    src={img}
                                    alt={item.name}
                                    loading="lazy"
                                  />
                                )}
                              </div>

                              {romanTier && (
                                <div className="item-card-tier">
                                  <span>{romanTier}</span>
                                </div>
                              )}

                              <div
                                className="item-card-name-bar"
                                style={nameBarStyle}
                              >
                                {item.name}
                              </div>
                            </div>
                          </div>
                        );
                      }

                      // ─────────────────────────────
                      // STATS VIEW
                      // ─────────────────────────────
                      const hasSynergy =
                        item.synergy_delta_wr != null &&
                        Math.abs(item.synergy_delta_wr) > 0.0005;

                      const synergyPositive = (item.synergy_delta_wr ?? 0) >= 0;

                      const synergyDisplay = hasSynergy
                        ? `${synergyPositive ? "+" : "−"}${formatPercent(
                            Math.abs(item.synergy_delta_wr as number)
                          )}`
                        : null;

                      const flowDisplay =
                        item.transition_prob_from_prev != null
                          ? formatPercent(item.transition_prob_from_prev)
                          : null;

                      return (
                        <div key={item.item_id} className="item-row">
                          <div className={cardClass}>
                            <div className="item-card-visual">
                              <div className="item-card-art">
                                {img && (
                                  <img
                                    src={img}
                                    alt={item.name}
                                    loading="lazy"
                                  />
                                )}
                              </div>

                              {romanTier && (
                                <div className="item-card-tier">
                                  <span>{romanTier}</span>
                                </div>
                              )}

                              <div
                                className="item-card-name-bar"
                                style={nameBarStyle}
                              >
                                {item.name}
                              </div>
                            </div>
                          </div>

                          <div className="item-stats-panel">
                            <div className="item-stat-block-column">
                              {/* Block 1 – Rank */}
                              <div className="item-stat-block">
                                <div className="item-stat-block-header">
                                  <span className="item-stat-block-label">
                                    Rank
                                  </span>
                                </div>
                                <div className="item-stat-block-body">
                                  <div className="item-stat-block-main">
                                    {item.phase_rank != null
                                      ? `#${item.phase_rank}`
                                      : "—"}
                                  </div>
                                  {item.phase_percentile != null && (
                                    <div className="item-stat-block-sub">
                                      {formatPercentile(item.phase_percentile)}
                                    </div>
                                  )}
                                </div>

                                <div className="item-stat-tooltip">
                                  <div className="item-stat-tooltip-title">
                                    Model Rank
                                  </div>
                                  <div className="item-stat-tooltip-body">
                                    How high this item is rated for{" "}
                                    <span className="item-stat-tooltip-em">
                                      your hero
                                    </span>{" "}
                                    at this moment in the game.{" "}
                                    <span className="item-stat-tooltip-em">
                                      #1
                                    </span>{" "}
                                    means it’s the strongest pick here.
                                  </div>
                                </div>
                              </div>

                              {/* Block 2 – Win Rate */}
                              <div className="item-stat-block item-stat-block--winrate">
                                <div className="item-stat-block-header">
                                  <span className="item-stat-block-label">
                                    Win Rate
                                  </span>
                                </div>
                                <div className="item-stat-block-body">
                                  <div className="item-stat-block-main">
                                    {formatPercent(item.hero_item_wr)}
                                  </div>
                                  <div className="item-stat-block-sub">
                                    {formatPercent(item.item_global_wr)} global
                                  </div>
                                </div>

                                <div className="item-stat-tooltip">
                                  <div className="item-stat-tooltip-title">
                                    Win Rate
                                  </div>
                                  <div className="item-stat-tooltip-body">
                                    Out of{" "}
                                    <span className="item-stat-tooltip-em">
                                      100 games
                                    </span>{" "}
                                    where this hero buys this item at this
                                    moment, this is how many end in a win.{" "}
                                    <span className="item-stat-tooltip-em">
                                      Global
                                    </span>{" "}
                                    is the same idea, but averaged across{" "}
                                    <span className="item-stat-tooltip-em">
                                      all heroes
                                    </span>
                                    .
                                  </div>
                                </div>
                              </div>

                              {/* Block 3 – Synergy / Flow highlight */}
                              {(hasSynergy || flowDisplay) && (
                                <div
                                  className={
                                    "item-stat-block item-stat-block--highlight " +
                                    (hasSynergy
                                      ? synergyPositive
                                        ? "item-stat-block--positive"
                                        : "item-stat-block--negative"
                                      : "")
                                  }
                                >
                                  <div className="item-stat-block-header">
                                    <span className="item-stat-block-label">
                                      {hasSynergy ? "Synergy" : "Flow"}
                                    </span>
                                  </div>
                                  <div className="item-stat-block-body">
                                    <div className="item-stat-block-main">
                                      {hasSynergy
                                        ? synergyDisplay
                                        : flowDisplay}
                                    </div>
                                    <div className="item-stat-block-sub">
                                      {hasSynergy
                                        ? "vs global"
                                        : "after previous"}
                                    </div>
                                  </div>

                                  <div className="item-stat-tooltip">
                                    <div className="item-stat-tooltip-title">
                                      {hasSynergy ? "Synergy" : "Build Flow"}
                                    </div>
                                    <div className="item-stat-tooltip-body">
                                      {hasSynergy ? (
                                        <>
                                          Shows how well this item{" "}
                                          <span className="item-stat-tooltip-em">
                                            fits this hero
                                          </span>{" "}
                                          compared to everyone else.{" "}
                                          <span className="item-stat-tooltip-em">
                                            +3%
                                          </span>{" "}
                                          means about{" "}
                                          <span className="item-stat-tooltip-em">
                                            3 extra wins
                                          </span>{" "}
                                          out of 100 games when this hero buys
                                          it.
                                        </>
                                      ) : (
                                        <>
                                          Shows how often players buy this item{" "}
                                          <span className="item-stat-tooltip-em">
                                            right after
                                          </span>{" "}
                                          the previous item in real matches.
                                          Higher means it’s a very{" "}
                                          <span className="item-stat-tooltip-em">
                                            common next step
                                          </span>
                                          .
                                        </>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </>
    );
  }

  // ---------- CONDITIONAL RENDER (selection vs build view) ----------

  if (showBuildView) {
    return (
      <main className="build-page">
        <div className="datalock-page build-view">
          <section className="section build-section">
            <div className="build-top-bar">
              <button
                type="button"
                className="back-button"
                onClick={handleBackFromBuild}
              >
                Back
              </button>

              <div className="build-view-toggle">
                <div className="view-toggle-pill">
                  <button
                    type="button"
                    className={
                      "view-toggle-option" +
                      (!showItemStats ? " view-toggle-option--active" : "")
                    }
                    onClick={() => setShowItemStats(false)}
                  >
                    ITEMS
                  </button>
                  <button
                    type="button"
                    className={
                      "view-toggle-option" +
                      (showItemStats ? " view-toggle-option--active" : "")
                    }
                    onClick={() => setShowItemStats(true)}
                  >
                    ANALYTICS
                  </button>
                </div>
              </div>

              <div />
            </div>

            {renderSelectionSummary()}

            <div
              ref={recommendationTopRef}
              className={
                "recommendation-area" +
                (showItemStats ? " recommendation-area--stats" : "")
              }
            >
              {isSubmitting ? (
                <p>Calculating recommendation…</p>
              ) : submitError ? (
                <p style={{ color: "#f97373" }}>{submitError}</p>
              ) : (
                renderRecommendations()
              )}
            </div>
          </section>
        </div>
      </main>
    );
  }

  // ---------- MAIN (HERO SELECTION) RENDER ----------

  return (
    <main>
      <div className="datalock-page">
        {/* HERO SELECTION */}
        <section className="section">
          <h2 className="section-title section-title--large">
            {stageHeading(stage)}
          </h2>

          <div className="selection-steps">
            {(Object.keys(STAGE_META) as SelectionStage[]).map((key) => {
              const meta = STAGE_META[key];
              const { current, required } = getStageCounts(
                key,
                heroId,
                laneAllyId,
                teamOtherIds,
                laneEnemyIds,
                enemyOtherIds
              );

              return (
                <button
                  key={key}
                  type="button"
                  className={[
                    "selection-step",
                    meta.roleClass,
                    key === stage ? "active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => handleStageClick(key)}
                >
                  <span className="selection-step-label">{meta.label}</span>
                  <div className="selection-step-counts">
                    {Array.from({ length: required }).map((_, idx) => {
                      const filled = idx < current;
                      const cls = filled
                        ? "selection-step-dot selection-step-dot--filled"
                        : "selection-step-dot";
                      return <span key={idx} className={cls} />;
                    })}
                    <span className="selection-step-counter">
                      {current}/{required}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {renderHeroGrid()}

          <div className="actions-row">
            {/* RECOMMEND BUILD */}
            <button
              type="button"
              className="action-button-primary"
              onClick={handleRecommendClickWithTracking}
              disabled={!canSubmit || isSubmitting}
            >
              <span className="action-button-primary-inner">
                <span className="action-button-flame">
                  <video
                    src="/video/play_btn_flame.webm"
                    autoPlay
                    muted
                    loop
                    playsInline
                  />
                </span>
                <span className="action-button-label">
                  {isSubmitting ? "Recommending…" : "Recommend Build"}
                </span>
              </span>
            </button>

            {/* RESET */}
            <button
              type="button"
              className="action-button-reset"
              onClick={resetAll}
              disabled={isSubmitting}
            >
              <span className="action-button-reset-inner">
                <span className="action-button-reset-label">Reset</span>
              </span>
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
