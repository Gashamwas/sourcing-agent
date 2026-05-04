# Cloris packaging pipeline

End-to-end build of `dist/Cloris.dmg` — the signed, notarized,
recipient-installable artifact handed to A24's Head of Recruiting.

This directory owns:

```
cloris/packaging/
├── README.md                      <- you are here
├── APPLE_DEV_SETUP.md             <- pre-flight: Apple Developer account
├── CLORIS_DOES_AND_DOES_NOT.md    <- ships with the DMG (IT-readable)
├── Info.plist                     <- reference (real plist is in the spec)
├── entitlements.plist             <- hardened-runtime entitlements
├── cloris.spec                    <- PyInstaller spec, main UI binary
├── cloris-worker.spec             <- PyInstaller spec, sibling worker binary
├── entry/
│   ├── cloris_main.py             <- main app entrypoint script
│   └── cloris_worker.py           <- worker entrypoint script
├── icon/
│   ├── icon-full.svg              <- full graphic (>= 64 px renders)
│   ├── icon-small.svg             <- simplified (<= 32 px renders)
│   ├── render-svg.py              <- cairosvg fallback renderer
│   ├── build-icon.sh              <- icon pipeline (svg -> .icns)
│   └── cloris.icns                <- generated; embedded by cloris.spec
└── scripts/
    ├── build-app.sh               <- pyinstaller both specs -> Cloris.app
    ├── check-universal2-deps.sh   <- lipo -info every C-extension
    ├── sign-app.sh                <- codesign inside-out + hardened runtime
    ├── notarize-app.sh            <- xcrun notarytool + stapler staple
    └── build-dmg.sh               <- create-dmg + sign DMG
```

## Pre-flight (do these once, days before you need to ship)

1. Apple Developer account: see `APPLE_DEV_SETUP.md`. **Start this
   first** — Apple's verification can take up to a week.
2. Tools:
   - `pip install pyinstaller cairosvg pillow` (in the project venv)
   - `brew install create-dmg`
   - `brew install librsvg` (optional — `cairosvg` is a fallback)
3. Universal 2 deps: run `./scripts/check-universal2-deps.sh` and
   resolve any single-arch wheels before building.
4. Frontend: `cd cloris/frontend && pnpm build` (the spec embeds the
   built dist/ into the .app's Resources).

## Standard build pipeline

Run from the repo root, in this order:

```bash
# Each script chains into the next; if any fails, fix the cause
# before continuing.

./cloris/packaging/icon/build-icon.sh           # cloris.icns
./cloris/packaging/scripts/build-app.sh         # dist/Cloris.app
./cloris/packaging/scripts/sign-app.sh          # codesign + hardened runtime
./cloris/packaging/scripts/notarize-app.sh      # Apple notary + staple
./cloris/packaging/scripts/build-dmg.sh         # dist/Cloris.dmg
```

Final hand-off package (upload to a private S3 bucket with a
presigned URL; do not use a public link):

- `dist/Cloris.dmg`
- `dist/Cloris.dmg.sha256`
- `cloris/packaging/CLORIS_DOES_AND_DOES_NOT.md`

## What lives where (architecture)

The build produces TWO binaries inside the .app bundle:

```
Cloris.app/
└── Contents/
    ├── Info.plist                         <- generated from the spec
    ├── MacOS/
    │   ├── Cloris                          <- main UI binary (FastAPI + pywebview)
    │   └── cloris-worker                   <- sibling binary spawned per-launch
    └── Resources/
        ├── cloris.icns                     <- icon
        ├── cloris/frontend/dist/           <- bundled SPA assets
        ├── _internal/                      <- Cloris's _MEIPASS
        └── cloris-worker-internal/         <- cloris-worker's _MEIPASS
```

The two-binary split (see plan §2 "Phase 0 worker-binary slice") is
non-negotiable in the frozen .app: `sys.executable` is the main UI
binary, not a python interpreter, so the legacy
`[python, -m, cloris.worker]` spawn pattern doesn't work. The API
layer detects frozen context via
`cloris/api.py:_frozen_worker_binary_path` and spawns the sibling
binary directly.

## Verification before shipping

Before uploading the DMG to the recipient:

```bash
# 1. Notarization staple is valid (offline Gatekeeper accept).
xcrun stapler validate dist/Cloris.app

# 2. Gatekeeper accepts the .app from a fresh-quarantine state.
spctl -a -v dist/Cloris.app
# Expected: "accepted" + "source=Notarized Developer ID"

# 3. Both architectures are present.
lipo -info dist/Cloris.app/Contents/MacOS/Cloris
lipo -info dist/Cloris.app/Contents/MacOS/cloris-worker
# Expected: "Architectures in the fat file: ... are: x86_64 arm64"

# 4. The DMG itself is signed.
codesign --verify --verbose=2 dist/Cloris.dmg

# 5. Smoke-test on a clean Mac (different from the build machine):
#    - Mount the DMG, drag Cloris.app to /Applications, eject.
#    - Double-click Cloris.app. Expect the welcome surface.
#    - Paste a real Anthropic key + check the box, click Continue.
#    - Verify Chrome opens on the Cloris profile.
#    - Sign into LinkedIn Recruiter in the Cloris Chrome.
#    - Verify the home renders.
```

A clean-Mac smoke is mandatory. The build machine has every dev
dep already installed (cached fonts, cached LinkedIn cookies,
~/.chrome-cdp from previous launch-chrome.sh runs); the recipient's
Mac has none of that. Plan §6 budgets ~1.5 days for this — don't
skip it.

## Common failure modes

| Symptom                               | Cause                                              | Fix                                                                                   |
| ------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------- |
| MemoryError on first launch           | Hardened runtime without `allow-unsigned-executable-memory` | Verify entitlements.plist applied (`codesign -d --entitlements - Cloris.app`)         |
| dylib load failure                    | Library validation enabled                         | Verify `disable-library-validation` entitlement                                       |
| Notary "binary not signed"            | A nested .so/.dylib was missed by sign-app.sh      | Re-run sign-app.sh; check the inside-out loop output for skips                        |
| Notary "main binary uses incompatible signing" | `--deep` was used (Apple deprecated this)    | sign-app.sh signs without --deep; if you ran codesign manually with --deep, re-do it  |
| .app crashes on Intel Mac             | arm64-only dep slipped in                          | Re-run `check-universal2-deps.sh` and rebuild from a python.org-installed interpreter |
| Recipient sees Gatekeeper warning     | DMG not signed OR notarization not stapled         | Run sign-app.sh + notarize-app.sh + build-dmg.sh in that order                        |

## When this whole pipeline runs (cadence)

Per release. There is no continuous build / nightly DMG; each
release is a deliberate ship. The plan §6 estimate is ~2.5-3 weeks
end-to-end; once Phase 0-2 are done, subsequent releases are ~1 day
(rebuild + re-sign + re-notarize + re-DMG, no Apple Developer
re-onboarding).
