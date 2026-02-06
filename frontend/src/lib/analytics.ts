// lib/analytics.ts

type EventParams = {
  category?: string;
  label?: string;
  value?: number;
  // Allow common GA param types without using `any`
  [key: string]: string | number | boolean | undefined;
};

// Augment the Window type so TS knows about `gtag`
declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

export function trackEvent(name: string, params: EventParams = {}): void {
  if (typeof window === "undefined") return; // SSR guard
  window.gtag?.("event", name, params);
}
