# Cloris Frontend (Slice 5)

Vite + Svelte 5 SPA. Python serves the built artifact in `dist/` directly,
so CI does not need Node.

## Develop

```
pnpm install
pnpm dev      # Vite dev server on :5173, proxies /api and /healthz to
              # the local Cloris API at 127.0.0.1:8765 (start it with
              # `python -m cloris start`).
```

## Build

```
pnpm build    # Emits cloris/frontend/dist/{index.html, assets/*}.
```

## Why `dist/` is committed

Python serves `cloris/frontend/dist/index.html` and mounts
`cloris/frontend/dist/assets/` as static files (see `cloris/api.py`). CI
runs `make validate`, which never invokes pnpm or Node — committing the
built bundle keeps the runtime self-contained.

## Bundled fonts

Vendored locally as `.woff2`. No Google Fonts CDN. See
`src/fonts/LICENSES.md` for the consolidated SIL Open Font License v1.1
attribution covering all three families:

- Fraunces — OFL-1.1 (https://github.com/undercasetype/Fraunces)
- Instrument Serif — OFL-1.1 (https://github.com/Instrument/instrument-serif)
- JetBrains Mono — OFL-1.1 (https://github.com/JetBrains/JetBrainsMono)

## Slice 5 non-goals

- No Authoring Loop, no candidate review, no Run Review, no Next Run Learning.
- No GitHub launch UI (read-only rows for GitHub state dirs).
- No pause UI; `away` mode is intentionally absent.
- No fake readiness or status states the backend cannot truthfully report.
