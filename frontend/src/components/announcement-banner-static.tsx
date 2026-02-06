"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "datalock_announcement_dismissed_v3";

export default function AnnouncementBannerStatic() {
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    try {
      const dismissed = localStorage.getItem(STORAGE_KEY);
      setHidden(dismissed === "1");
    } catch {
      setHidden(false);
    }
  }, []);

  if (hidden) return null;

  return (
    <div className="dl-announce-wrap">
      <div className="dl-announce-box" role="status" aria-live="polite">
        <div className="dl-announce-text">
          <span className="dl-announce-pill">Update</span>
          <span>
            Major update just released. DataLock and the ML model will be
            refreshed once all new heroes and their assets are available.
          </span>
        </div>

        <button
          type="button"
          className="dl-announce-dismiss"
          onClick={() => {
            try {
              localStorage.setItem(STORAGE_KEY, "1");
            } catch {}
            setHidden(true);
          }}
          aria-label="Dismiss announcement"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
