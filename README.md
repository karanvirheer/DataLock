<p align="center">
  <img src="/assets/logo.svg" alt="DataLock Logo" width="130"/>
</p>
<p align="center">
  <img src="/assets/logo_name.png" alt="DataLock" width="400"/>
</p>

<p align="center">
  <strong>ML-powered item build recommendations for Valve’s Deadlock.</strong>
</p>

<p align="center">
  <a href="https://datalock.dev">Live Site</a> ·
  <a href="https://deadlock-api.com/">Deadlock API</a>
</p>

---
## About
DataLock is a context-aware item recommender for Valve’s Deadlock. Select your hero, allies, enemies, and game phase to receive ranked item suggestions predicted to improve your chances of winning. Instead of static build guides, DataLock adapts recommendations to the lobby you are actually in, using an ML model trained on large-scale community match data.

Recommendations are enriched with item metadata and shop images, then presented in a clean, fast UI that makes it easy to compare options and lock in a build.

<p align="center">
  <img src="/assets/demo.gif" alt="Datalock Demo"/>
</p>

---

## How It Works

DataLock is split into three layers: a fast UI for selecting match context, a serverless inference API for ranking items, and a private model bundle that keeps the ML artifacts and metadata secure.

**1) UI collects match context (Vercel, Next.js)**  
You select your hero, allies, enemies, and a game phase (early, mid, late). The UI is intentionally lightweight so the interaction feels instant and the recommendation flow is easy to understand.

**2) Requests are routed server-side to protect secrets (Next.js API routes)**  
The browser never talks to AWS directly. Instead, the Next.js server routes forward requests to the inference API and attach an `x-api-key` from environment variables. This keeps the API key out of client-side code and prevents it from being scraped from network requests.

**3) Serverless inference runs on AWS Lambda (Python)**  
The AWS HTTP API triggers a Python Lambda handler which:
- validates the request payload (hero IDs, phase, team sizes)
- transforms the match context into a fixed-order feature vector (using versioned metadata)
- scores candidate items using an XGBoost model trained on large-scale match outcomes
- returns a ranked list of items with scores and item metadata for display

**4) Model assets are loaded from private S3 and cached for speed**  
The inference bundle (models + feature ordering + item/hero metadata) lives in a private S3 bucket. On cold start, Lambda downloads the bundle once, then caches it in `/tmp` and process-level globals so subsequent invocations reuse the assets without repeated S3 fetches. This reduces latency and cost while keeping the artifacts private.

**5) Optional caching for repeated matchups (DynamoDB)**  
For identical contexts (same hero, allies, enemies, phase), DynamoDB can cache the response. This avoids recomputing rankings for common matchups and makes repeated requests consistently fast.

**6) Results are rendered as a build shortlist (Next.js UI)**  
The frontend renders the ranked recommendations as item cards using the returned metadata (names and shop images). The goal is to make the output feel like a usable build shortlist rather than a raw model score dump.

---
