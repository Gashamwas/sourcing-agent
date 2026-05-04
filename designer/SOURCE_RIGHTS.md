# Designer Module — Source Rights & Asset Policy

Status: skeleton (awaiting Gate C legal review per `plans/designer-readiness-gate.md`)
Owner: Sam
Last updated: 2026-05-03

This document is the artifact reviewed in Gate C of the Designer Readiness Gate. Slice 5 (image acquisition + vision evaluation) does NOT ship until counsel signs off on the posture below. Edits requested during review land here before Slice 5 begins.

## Posture summary

Cloris's Designer module evaluates designer portfolios against a brief-encoded `BriefDesignRubric`. To do that evaluation, vision LLMs (Gemini 2.5 Pro primary; Claude Sonnet 4.6 cross-check on top-decile candidates) read images of the designer's published work product. The images are sourced from public APIs and (where licensing permits) public webpages. Cloris does not redistribute, train on, or display these images outside the recruiter's authenticated workspace.

## Acquisition channels (per-source posture)

### Behance v2 API

- **License path.** Adobe Behance Developer API standard agreement permits "cache for the purpose of fulfilling the API client's stated functionality." Cloris's stated functionality is recruiter-facing portfolio evaluation; caching for evaluation falls within scope.
- **Endpoints used.** `/v2/users/{username}`, `/v2/users/{username}/projects`, `/v2/projects/{id}` — all public, no scraped surfaces.
- **Image URLs.** Extracted from the `modules` array of `/v2/projects/{id}` responses (`image.size.original` or `image.size.disp`, ~1024px res).
- **Cache lifetime.** Run lifetime + 30 days, then deleted via cron job. Provenance metadata (URL + retrieved_at + ToS_source) retained 90 days for audit.
- **Rate limit.** 150 req/hr free tier. Cloris respects it.

### Google Custom Search Engine (CSE)

- **License path.** Google CSE ToS permits display of result thumbnails (`pagemap.cse_thumbnail`) within custom search results. Cloris uses the thumbnails as evaluation inputs — same display surface, same recruiter-authenticated workspace.
- **Endpoints used.** Standard CSE programmable search endpoint, filtered to portfolio-host domains (`site:cargo.site`, `site:squarespace.com`, `site:format.com`, `site:semplice.com`, `site:awwwards.com`, `site:siteinspire.com`).
- **Image URLs.** `pagemap.cse_thumbnail[*].src` — Google-provided low-res thumbnails. Cloris does NOT bypass this to fetch full-res originals from the host site (would require host-by-host ToS analysis; out of scope for v1).
- **Cache lifetime.** Same as Behance — run + 30 days; provenance 90 days.
- **Rate limit.** 100 queries/day free; $5/1K paid up to 10K/day.

### Direct portfolio fetch (whitelisted hosts only)

- **License path.** Per-host opt-in. Default behavior: skip direct fetch — Cloris uses Google CSE thumbnails only. Direct fetch is a v1.5 feature gated on per-host ToS permitting it OR no `robots.txt` / meta-robots exclusion.
- **Hosts under consideration.** Cargo.site, Squarespace, Format, Semplice. Slice 5 ships with direct fetch DISABLED for all hosts; v1.5 enables on a per-host basis after host-by-host ToS confirmation.
- **Cache lifetime.** Same as Behance.

### Dribbble v2 API (Slice 10, optional)

- **License path.** Standard Dribbble Developer API agreement permits read access to user shots / tags / projects for OAuth2-authenticated clients. Same cache-for-API-purpose posture as Behance.
- **Endpoints used.** `/v2/users/{user_id}/shots`, `/v2/shots/{shot_id}`, tag-filtered shot search. Popular feed is NOT used (explicitly unavailable to API users per Dribbble's published API restrictions).
- **Image URLs.** Extracted from shot responses (`images.normal` or `images.hidpi`).
- **Cache lifetime.** Same as Behance.

## Bounded cache

- **TTL: run lifetime + 30 days.** A cron job (Slice 5) deletes asset blobs from `output/state/designer/<state_key>/assets.sqlite3` once the run is finalized + 30 days have passed.
- **Provenance retention: 90 days.** URL + `retrieved_at` + `ToS_source` survive the asset-blob deletion by 60 days so any audit query can answer "where did Cloris get this image, when, and under what license posture?" — even after the blob itself is gone.
- **No backup outside the bounded cache.** Designer asset blobs are NOT included in any platform-wide backup that would extend the TTL beyond the documented window.

## No redistribution / no training

- **Display surface.** Recruiter's authenticated workspace only. Asset URLs surface inline in the HITL visual review card so the recruiter can verify provenance; the cached blobs themselves are read by Gemini 2.5 Pro / Sonnet 4.6 for evaluation, then served only to the workspace (never to a public surface, never embedded in a marketing page, never shared cross-customer).
- **No training.** Cloris does not fine-tune any model on cached portfolio assets. The brief-encoded rubric carries per-customer taste; off-the-shelf vision models apply it. Spec §13 explicitly rejects fine-tuning.
- **No cross-customer leakage.** Each customer's runs are isolated by `state_key`. A designer evaluated for Customer A is not surfaced to Customer B's recruiter.

## Designer-side opt-out (v1.5 commitment)

v1 ships without a designer-side opt-out mechanism. v1.5 will introduce a `.well-known/cloris-policy.json` discovery (a designer publishes this on their portfolio domain to register a `cloris-no-cache` policy; Cloris reads it before any cache write and skips that designer). Documented as a known v1 limitation; not a defect.

## Open items for Gate C reviewer

- Confirm Behance Developer API agreement still permits cache-for-API-purpose at the cache lifetime documented above (run + 30 days; provenance 90 days). If counsel reads the agreement to require shorter retention, update both windows here.
- Confirm Google CSE ToS interpretation: thumbnails-as-evaluation-input is consistent with "display in custom search results."
- Confirm cross-customer isolation language is sufficient.
- Sign off in the table below; Slice 5 begins on sign-off.

## Sign-off

| Reviewer | Date | Notes |
|----------|------|-------|
| _to be filled_ | _to be filled_ | _to be filled_ |
