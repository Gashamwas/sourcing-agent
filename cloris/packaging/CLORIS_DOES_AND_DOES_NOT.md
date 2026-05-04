# What Cloris does and doesn't do on your Mac

This is the IT/security-readable summary of Cloris's footprint on the
recipient's machine. Ships alongside the DMG download.

## What Cloris is

Cloris is a recruiter-side sourcing tool. It reads candidate profiles
in your existing LinkedIn Recruiter session, judges them against a
brief you wrote, and saves the matches into the Recruiter project
you've configured. You drive the work; Cloris does the reading and
the bookkeeping.

The Cloris desktop app is a notarized macOS .app bundle, distributed
as a signed DMG. Apple's Gatekeeper verifies the developer identity
on first launch — there is no "unverified developer" warning.

## What Cloris does, exactly

- **Opens its own Chrome window** on a dedicated profile at
  `~/.cloris/chrome-profile`. This profile is separate from your
  everyday Chrome — your bookmarks, passwords, session tabs, and
  signed-in accounts are not visible to Cloris and not modified by
  it. You sign into LinkedIn Recruiter once in the Cloris Chrome
  window; that sign-in persists.
- **Attaches to that Chrome over Chrome DevTools Protocol (CDP)**
  on `127.0.0.1:9222`. CDP is the same protocol Chrome's own
  developer tools use; it's a local websocket between Cloris and
  Chrome on your machine, never exposed to the internet.
- **Reads candidate profiles** in your Recruiter session at
  human-paced cadence (see "Pace" below) only when you explicitly
  start a search.
- **Sends snippets and full profile text to Anthropic's API** for
  judgment. Your Anthropic API key is the only thing transmitted to
  Anthropic; the per-candidate prose Cloris sends is the same prose
  visible to you in Recruiter.
- **Saves matching candidates** into the Recruiter project you
  configured for the brief — same action you'd take by hand,
  performed through the same Recruiter UI surface.
- **Writes runtime state** (which candidates have been judged, what
  Cloris said about them, your Recruiter project ID) to
  `~/Library/Application Support/Cloris/`. Nothing written to your
  Documents, Downloads, Desktop, or anywhere outside that directory.

## What Cloris does NOT do

- **Does not type messages, send InMails, change project settings,
  or take any candidate-outreach action on your behalf.** Cloris
  only reads and saves.
- **Does not touch your everyday Chrome.** No reading from your
  personal profile, no killing your personal Chrome processes, no
  modification of your default Chrome settings.
- **Does not phone home.** Cloris does not send telemetry, usage
  analytics, error reports, or any other traffic to Cloris-operated
  servers. The only outbound network traffic is:
  - LinkedIn (via your existing Recruiter session in the Cloris
    Chrome window) — same traffic you'd generate using LinkedIn
    manually.
  - Anthropic's API at `api.anthropic.com` — using the Anthropic
    key you pasted into the welcome screen.
- **Does not auto-update.** The .app you receive is the .app that
  runs. New versions are distributed as new DMG downloads; no
  background updater service runs on your machine.
- **Does not run in the background after quit.** Closing the Cloris
  window quits the app. The Cloris Chrome window can be closed
  separately; closing it ends the LinkedIn session attachment.

## Where Cloris stores things

| What | Where | Why |
| --- | --- | --- |
| Anthropic API key | `~/Library/Application Support/Cloris/.env` (chmod 600) | Required by Anthropic API; chmod 600 = owner-readable only |
| First-launch acknowledgment | `~/Library/Application Support/Cloris/acknowledged.json` | Records that the recipient agreed to Cloris's operational surface; surfaces no other state |
| Per-brief runtime state | `~/Library/Application Support/Cloris/output/state/<source>/<brief-id>/runtime_state.sqlite3` | SQLite database holding which candidates Cloris has read, judged, and saved |
| Cloris's dedicated Chrome profile | `~/.cloris/chrome-profile/` | Standard Chrome profile directory; isolates Cloris's LinkedIn session from your personal Chrome |
| Logs | None on disk; surfaced in the Cloris UI's "Live Monitor" view only | Cloris doesn't write log files |

To reset Cloris to first-launch state: delete
`~/Library/Application Support/Cloris/` and restart the app.

## Pace and rate-limiting

Cloris's operational cadence is hard-coded by deliberate engineering
decision (visible in the Settings → "How fast Cloris runs" panel
inside the app):

- ≤200 profile opens per session.
- ≤400 profile opens per 24-hour rolling window.
- ≤3 sessions per day.
- ~3.5–4.5 hour wall-clock cap per session, randomized to avoid
  metronomic patterns.
- Session start is gated by your explicit "Start search" click;
  Cloris does not auto-resume across day boundaries.

These numbers are below the threshold at which LinkedIn typically
flags account activity. They are not configurable from the UI.

## LinkedIn Terms-of-Service posture

Cloris operates through your normal Chrome browser using your normal
Recruiter session, at human-paced cadence, only when you explicitly
start a search. The bytes-on-the-wire to LinkedIn are the same as
those generated by you using LinkedIn manually.

That said: any automation tool against LinkedIn is in a gray area
under LinkedIn's Terms of Service. Cloris's job is to keep your
account well under the threshold where automation-detection
heuristics activate. The risk to your account, if LinkedIn objects
to your account's activity, is your risk to manage. If your
employer's IT policy or LinkedIn's contractual terms prohibit
browser-automation tools against Recruiter, do not run Cloris.

## Network surface summary

| Direction | Endpoint | Traffic |
| --- | --- | --- |
| Outbound (via your Cloris Chrome) | `linkedin.com/talent` | Your existing Recruiter session — search queries, profile reads, candidate saves |
| Outbound | `api.anthropic.com` | Per-candidate snippet/profile text + your prompt; uses the API key you pasted |
| Local only | `127.0.0.1:9222` (CDP) | Cloris ↔ its own Chrome window |
| Local only | `127.0.0.1:<random>` (Cloris UI) | Browser ↔ Cloris's local FastAPI server |

No other outbound destinations. No telemetry. No auto-update channel.

## Code provenance

The Cloris .app is signed with an Apple Developer ID (visible in
Finder via Get Info → "Verified Developer") and notarized by Apple
(verifiable with `spctl -a -v Cloris.app` from Terminal, which prints
the developer ID and "accepted" / "source=Notarized Developer ID").

If you need source-code review or a signed Bill of Materials before
running Cloris on a corporate-owned machine, contact whoever sent
you the DMG — they can route the request to the Cloris team.

## Uninstalling

1. Quit Cloris (close the window, or `Cmd+Q`).
2. Drag `Cloris.app` from Applications to the Trash.
3. Optionally remove `~/Library/Application Support/Cloris/` and
   `~/.cloris/chrome-profile/` to delete cached state and the
   Cloris-specific Chrome profile.

No background services. No launchd plists. No system-wide
modifications.
