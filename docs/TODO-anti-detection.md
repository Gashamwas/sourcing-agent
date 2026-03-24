# Anti-Detection TODO

## Implemented
- [x] rebrowser-playwright (CDP detection evasion — Runtime.Enable patched)
- [x] Log-normal timing distributions (human_timing.py, all orchestrator delays)
- [x] ghost-cursor Bézier mouse trajectories (profile clicks, save, pagination)
- [x] Jittered delays on all browser interactions
- [x] Cadence pause system (30min activity → 2min break)
- [x] 0-result string failsafe

## Next: Per-Card Sequential Flow
Restructure the page processing loop from batch-then-burst to per-card sequential.

Current: extract all snippets → batch facial triage → rapid-fire profile opens
Target: for each card top-to-bottom, scroll into view → pause → extract → facial → open/skip

- Eliminates "dead air then burst" behavioral signature
- FACIAL_NO candidates get a visible 2-5s scroll-past (LinkedIn sees a human skip)
- Extraction moves from 1 batch cheap-model call to ~25 per-card calls (~$0.02/page extra)
- Wall-clock ~30-40s slower per page — but that IS the human-like pacing

## Dwell Time Variance
- Add occasional long dwells (30-90s) on interesting-looking profiles
- Add sub-3s bounces on obviously-wrong profiles
- Current dwell is too tight around the mean — needs wider spread + rare outliers

## Cross-Session Variance
- Vary daily volume (don't always do 200-400 profiles)
- Vary session start time
- Vary total session duration
- Occasionally run short sessions (30min, 50 profiles)

## Warm-Up Protocol (for new seats)
- Start at 25% of target volume
- Ramp over 2-4 weeks
- Critical for any future multi-seat deployment

## Decoy Interactions (Lower Priority — User Doing Manually For Now)
- Feed scrolling (2-5 min per session)
- Check notifications mid-search
- Occasional messaging interactions
- Re-examine a previously skipped profile for 5-12s
- Visit a company page mid-flow

## Future / Higher Effort
- Diffusion-model mouse trajectories (replaces ghost-cursor Bézier with neuromotor-authentic paths)
- OS-level input simulation (PyAutoGUI/nut.js — bypasses CDP event injection entirely)
- Camoufox Firefox fork (eliminates CDP detection class entirely, but requires architecture change)
- Tab visibility simulation (Page.setVisibilityState — simulate tab-away/tab-back)
- Keyboard noise injection (occasional stray keypresses, search field edits)
