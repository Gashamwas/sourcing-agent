# Designer Readiness Gate

Status: open
Owner: Sam
Last updated: 2026-05-03

## Purpose

Slice 0 of [/Users/sam.vangelos/.cursor/plans/designer-module-spec_5f3d48c1.plan.md](file:///Users/sam.vangelos/.cursor/plans/designer-module-spec_5f3d48c1.plan.md). Three GO/NO-GO gates that must clear before Designer slices that depend on them ship. Slice 1 (schema + registry + placeholder evaluator) is gate-independent and can land before any of these resolve.

## Gates

### Gate A — Behance API key access (blocks Slice 2; allows v0 downgrade)

**What's verified.** Cloris has a working Behance Developer API key with read access to `/v2/users/{username}/projects`, `/v2/projects/{id}`, and `/v2/users/{username}` (used for facial triage and image acquisition).

**Verification steps.**

1. Check Adobe Developer Console for an existing Behance API client registered to a Cloris-controlled email. If present, validate it returns 200 against `GET https://api.behance.net/v2/users/jurgenmaier?api_key=<KEY>` (Jurgen Maier is a long-active public Behance profile suitable for a smoke probe).
2. If no key exists, attempt registration at [adobe.io / Behance API](https://www.adobe.io/apis/creativecloud/behance.html). Adobe stopped accepting new clients in 2020, so this will likely fail; document the response.
3. If registration is denied, escalate to Adobe Developer Relations via partner channel (not blocked on this; the Slice 2 plan downgrade is the parallel path).

**GO criteria.**

- API key returns 200 against the smoke probe.
- Rate limit headers (`x-ratelimit-remaining`) confirm the standard 150 req/hr free tier or higher.

**NO-GO downgrade.** Drop Behance from Slice 2 scope. Slice 2 ships with Google CSE-only as v0; Slice 10 (Dribbble enrichment) becomes a maybe-promotion if it ends up being the differentiating data source. Document the downgrade in the Slice 2 PR description and update the spec's §3.1 source-by-source posture.

**Status:** _to be filled by human_.

### Gate B — Gemini 2.5 Pro API access (blocks Slice 5)

**What's verified.** Cloris has authenticated access to Gemini 2.5 Pro via either Google AI Studio API or Vertex AI, with image-input support and structured-output (`response_schema`) support at the per-evaluation token volume documented in spec §4.1 (~62K image tokens × 30 candidates per run).

**Verification steps.**

1. Check `~/.cursor/.env` and the `shared/llm_clients.py` config for an existing `GEMINI_API_KEY` or `GOOGLE_AI_STUDIO_API_KEY`.
2. If present, run `python -c "from google import genai; client = genai.Client(); resp = client.models.generate_content(model='gemini-2.5-pro', contents=['hello']); print(resp.text)"` — expect a successful response.
3. If absent, create a Google AI Studio account and provision a key. Free tier is sufficient for the fixture-portfolio characterization in Slice 5 (~50 evaluations).
4. Verify image-input support with a single 1024×1024 fixture image.
5. Verify structured-output support: pass a `response_schema={...}` and confirm the response parses cleanly.

**GO criteria.**

- Both text and image inputs return parseable structured output at the projected per-call token budget.
- Token-counting endpoints (`models.count_tokens`) return ~258 tokens per 1024×1024 image, matching the cost-projection assumption in spec §4.1.

**NO-GO downgrade.** None — Designer's vision-evaluation pipeline is the load-bearing differentiation. Without Gemini 2.5 Pro access, Slice 5 cannot ship and Slices 6-11 are downstream-blocked. If Gemini access is denied, surface as a hard stop and revisit module scope (drop the visual-evaluation differentiation; ship Designer as a text-only sourcing module). Per spec §13, fine-tuning and switching primary model to Sonnet 4.6 are explicitly rejected (cost differential is ~10x).

**Status:** _to be filled by human_.

### Gate C — Asset-rights legal posture review (blocks Slices 5-7)

**What's verified.** A 1-day legal review of [designer/SOURCE_RIGHTS.md](../designer/SOURCE_RIGHTS.md) (created in Slice 1 as a skeleton; populated as a deliverable of this gate) confirming Cloris's posture is defensible:

- **Bounded cache.** Run lifetime + 30 days, then deletion via cron job.
- **No redistribution / training.** Images are read by Gemini 2.5 Pro for evaluation only; not sold, republished, or used as training data.
- **Per-source ToS posture.** Behance: cache-for-API-purpose under the developer agreement. Google CSE thumbnails: display permitted under custom-search ToS. Direct portfolio fetch: only for whitelisted hosts with permissive ToS or no `robots.txt`/meta-robots exclusion.
- **Provenance metadata retention.** URL + retrieved_at + ToS_source retained 90 days for audit; longer than the cache itself, shorter than indefinite.
- **Designer-side opt-out v1.5 commitment.** A `.well-known/cloris-policy.json` discovery is planned for v1.5; v1 ships without it. Surface as a known limitation.

**Verification steps.**

1. Slice 1 commits `designer/SOURCE_RIGHTS.md` with the policy text (this is the artifact under review).
2. Sam (or counsel) reviews the document against current Behance ToS, Google CSE ToS, and Dribbble ToS.
3. Reviewer either signs off or surfaces specific edits before the cache infrastructure (Slice 5) ships.

**GO criteria.**

- `designer/SOURCE_RIGHTS.md` reviewed and signed off (commit message or PR comment recording the review).
- Any reviewer-mandated edits land before Slice 5 begins image caching.

**NO-GO downgrade.** Defer image acquisition entirely. Slice 5 ships without image acquisition (vision-evaluation prompt receives URLs only and degrades to URL-mention prompts; effectively neuters the visual-evaluation differentiation). This is functionally equivalent to a hard stop on the module's core value proposition. If counsel raises specific concerns, address them in `designer/SOURCE_RIGHTS.md` and re-submit; don't ship the cache without sign-off.

**Status:** _to be filled by human_.

## Decision rubric

| Gate | GO | NO-GO action |
|------|----|--------------|
| A. Behance API key | ship Slice 2 with Behance + Google CSE | downgrade Slice 2 to Google CSE-only v0; defer Behance integration to a follow-up |
| B. Gemini 2.5 Pro API | ship Slice 5 vision pipeline | hard stop — revisit module scope (text-only Designer module is a different product) |
| C. Asset-rights legal review | ship Slice 5 with image caching | defer image caching; Slice 5 effectively neutered until counsel signs off |

## Sign-off

When each gate clears, append below with date + verifier name + brief evidence (e.g., "Behance API key returns 200 against smoke probe; rate limit 150 req/hr confirmed").

- [ ] Gate A — Behance API key:
- [ ] Gate B — Gemini 2.5 Pro API:
- [ ] Gate C — Asset-rights legal review:
