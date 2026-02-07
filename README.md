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


---

## Demo
- **Live:** https://datalock.dev
- **Demo Video:** https://www.datalock.dev/video/demo.webm
- **Walkthrough GIF:** `./docs/images/datalock-demo.gif` *(optional but recommended)*

---

## How It Works
1. **User selects match context (Frontend)**
   - Hero + allies + enemies + phase are selected in the Next.js UI.

2. **Server-side API routes call AWS (key stays private)**
   - The browser never sees the API key.
   - Next.js server routes attach `x-api-key` from environment variables.

3. **AWS Lambda builds features and runs inference**
   - Lambda converts the request into a fixed-order feature vector using model metadata.
   - XGBoost models score items and rank them by predicted win-impact for the context.

4. **Private model assets are loaded from S3 and cached**
   - Models + metadata live in a **private S3 bucket**.
   - Lambda downloads the inference bundle on cold start, then caches it in `/tmp` and warm globals.

5. **Optional caching for repeated contexts**
   - DynamoDB can store results for identical contexts to reduce repeated inference work.

---
