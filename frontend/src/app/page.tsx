"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";
import type { MetadataPayload } from "@/types/deadlock";
import Image from "next/image";
import { trackEvent } from "@/lib/analytics";
import AnnouncementBanner from "@/components/announcement-banner-static";

const MODEL_VERSION_FALLBACK = "Unknown";
const TRAINED_MATCHES = "200K+";
const UNIQUE_PLAYERS = "180k+";

// simple in-memory cache for this browser session
let metadataCache: MetadataPayload | null = null;
let metadataCacheTimestamp = 0;
const METADATA_CACHE_TTL_MS = 15 * 60 * 1000; // 15 minutes

const handleOpenRecommenderClick = () => {
  trackEvent("open_hero_build_recommender", {
    category: "navigation",
    location: "home_cta",
  });
};

function formatNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString();
}

export default function HomePage() {
  const [metadata, setMetadata] = useState<MetadataPayload | null>(null);
  const [isLoadingMetadata, setIsLoadingMetadata] = useState(false);
  const [metadataError, setMetadataError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAndCacheMetadata() {
      try {
        setIsLoadingMetadata(true);
        setMetadataError(null);

        const res = await fetch("/api/metadata", { method: "GET" });
        if (!res.ok) {
          throw new Error(`GET /api/metadata failed: ${res.status}`);
        }
        const temp = await res.json();
        const data: MetadataPayload = temp.model_metadata ?? temp;

        if (!cancelled) {
          metadataCache = data;
          metadataCacheTimestamp = Date.now();
          setMetadata(data);
        }
      } catch (err: unknown) {
        console.error("Failed to load /api/metadata", err);
        if (!cancelled) {
          setMetadataError("Unable to load latest model stats.");
        }
      } finally {
        if (!cancelled) setIsLoadingMetadata(false);
      }
    }

    const now = Date.now();
    const isCacheFresh =
      metadataCache && now - metadataCacheTimestamp < METADATA_CACHE_TTL_MS;

    if (isCacheFresh) {
      setMetadata(metadataCache);
    } else {
      fetchAndCacheMetadata();
    }

    return () => {
      cancelled = true;
    };
  }, []);

  const displayVersion = metadata?.model_version ?? MODEL_VERSION_FALLBACK;
  const patchWindow = metadata
    ? `${metadata.date_from} → ${metadata.date_to}`
    : "Latest patch window";

  return (
    <main>
      {/* Fullscreen video background */}
      <video
        className="bg-video"
        src="/video/menu_streets_loop2.webm"
        autoPlay
        muted
        loop
        playsInline
      />

      <div className="home-page">
        {/* Top banner */}
        <AnnouncementBanner />

        {/* TOP: brand area + tagline */}
        <header className="home-header">
          <div className="home-logo-stack">
            <Image
              src="/logo/logo_svg.svg"
              alt="DATALOCK logo icon"
              width={96}
              height={96}
              className="home-logo-icon"
              priority
            />
            <Image
              src="/logo/logo_name_png.png"
              alt="DATALOCK"
              width={420}
              height={90}
              className="home-logo-wordmark"
              priority
            />
          </div>

          <div className="home-tagline">Deadlock Build Recommender</div>
        </header>

        {/* BIG CTA BAR */}
        <div className="home-actions">
          <Link href="/build">
            <button
              type="button"
              className="home-cta-button"
              onClick={handleOpenRecommenderClick}
            >
              <span className="home-cta-inner">
                <span className="home-cta-flame">
                  <video
                    src="/video/play_btn_flame.webm"
                    autoPlay
                    muted
                    loop
                    playsInline
                  />
                </span>
                <span className="home-cta-label">
                  Open Hero Build Recommender
                </span>
              </span>
            </button>
          </Link>
        </div>

        {/* Actively maintained status directly under CTA */}
        <div className="home-active-indicator">
          <span className="home-active-dot" />
          <span>
            {metadata
              ? `Actively maintained — LAST UPDATE: ${metadata.date_to}.`
              : "Actively maintained — model retrained on the latest Deadlock patch."}
          </span>
        </div>

        {/* BOTTOM ROW: tile grid – stats on left, demo tile on right */}
        <div className="home-layout">
          <section className="home-stat-grid">
            <div className="home-stat-tile home-stat-tile--wide">
              <div className="home-stat-eyebrow">Current model</div>
              <div className="home-stat-main home-stat-main--accent">
                {displayVersion}
              </div>
              <div className="home-stat-sub">{patchWindow}</div>
            </div>

            <div className="home-stat-tile home-stat-tile--matches">
              <div className="home-stat-main">
                {metadata ? formatNumber(metadata.matches_analyzed) : "—"}
              </div>
              <div className="home-stat-caption">Matches analyzed</div>
            </div>

            <div className="home-stat-tile home-stat-tile--players">
              <div className="home-stat-main">
                {metadata ? formatNumber(metadata.players_sampled) : "—"}
              </div>
              <div className="home-stat-caption">Players sampled</div>
            </div>

            <div className="home-stat-tile home-stat-tile--heroes">
              <div className="home-stat-main">
                {metadata ? formatNumber(metadata.hero_count) : "—"}
              </div>
              <div className="home-stat-caption">Heroes</div>
            </div>

            <div className="home-stat-tile home-stat-tile--items">
              <div className="home-stat-main">
                {metadata ? formatNumber(metadata.item_count) : "—"}
              </div>
              <div className="home-stat-caption">Items</div>
            </div>

            <div className="home-stat-footnote">
              Trained on <span>{TRAINED_MATCHES}</span> matches and{" "}
              <span>{UNIQUE_PLAYERS}</span> players overall.
            </div>

            {isLoadingMetadata && (
              <div className="home-meta-status">Loading live stats…</div>
            )}
            {metadataError && (
              <div className="home-meta-status home-meta-status--error">
                {metadataError}
              </div>
            )}
          </section>

          {/* Right: demo video tile */}
          <section className="home-demo-tile">
            <div className="home-demo-header">
              <span className="home-demo-eyebrow">Preview</span>
              <span className="home-demo-title">
                Build recommender in action
              </span>
            </div>

            <div className="home-demo-frame">
              <video
                className="home-demo-video"
                autoPlay
                muted
                loop
                playsInline
                // poster="/video/demo_build_flow_poster.jpg"
                preload="metadata"
              >
                <source src="/video/demo.webm" type="video/webm" />
                Your browser does not support the video tag.
              </video>
            </div>

            <p className="home-demo-caption">
              A quick 5-10 second loop of the hero selection → build
              recommendation flow.
            </p>
          </section>
        </div>
        {/* FOOTER */}
        <footer className="home-footer">
          <div className="home-footer-links">
            <a
              href="https://github.com/karanvirheer"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
            <a
              href="https://www.linkedin.com/in/karanvirheer"
              target="_blank"
              rel="noopener noreferrer"
            >
              LinkedIn
            </a>
            <a
              href="https://karanvirheer.com/?utm_source=datalock.dev&utm_medium=referral&utm_campaign=datalock_home_footer"
              target="_blank"
              rel="noopener noreferrer"
              onClick={() =>
                trackEvent("external_click", {
                  category: "outbound",
                  destination: "karanvirheer.com",
                  location: "home_footer",
                })
              }
            >
              Website
            </a>
          </div>

          <div className="home-footer-text">
            <p className="home-footer-credit">
              Built by <span>Karanvir Heer</span>
            </p>

            <p className="home-footer-disclaimer">
              <span className="home-footer-label">Disclaimer:</span> DATALOCK is
              a fan-made project and is not affiliated with, sponsored by, or
              endorsed by Valve, Deadlock, or any related trademarks. All game
              content and assets belong to their respective owners.
            </p>
          </div>
        </footer>
      </div>
    </main>
  );
}
