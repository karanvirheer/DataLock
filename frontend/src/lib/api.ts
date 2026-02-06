// src/lib/api.ts
"use client";

import type {
  HeroAsset,
  RecommendPayload,
  RecommendationsByPhase,
} from "@/types/deadlock";

interface RecommendResponse {
  model_version: string;
  recommendations: RecommendationsByPhase;
}

export async function fetchHeroes(): Promise<HeroAsset[]> {
  const res = await fetch("/api/heroes", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    throw new Error(`Failed to load heroes (${res.status})`);
  }

  const data = await res.json();
  return data.heroes as HeroAsset[];
}

export async function recommendBuild(
  payload: RecommendPayload
): Promise<RecommendResponse> {
  const res = await fetch("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Recommend failed (${res.status}) ${text ? `- ${text}` : ""}`.trim()
    );
  }

  return (await res.json()) as RecommendResponse;
}
