# Reachability probe results — self-published by CI

Each dated section below is written directly by the `stage0-reachability`
workflow from an Actions runner and pushed by the runner itself (the
repository is private, so runner output cannot be read any other way from the
dev sandbox). Sections append chronologically; every heading names its vantage
point. Local-sandbox comparisons live in `docs/stage0-report.md`.

Reference points reported earlier by the maintainer (run 32795730414,
Actions vantage): `mcdonline.nic.in` 200 · `sahaaya2.bbmp.gov.in` 200 ·
`data.opencity.in` 200 · `bbmp.gov.in` 000 — the asymmetry that motivates
recording both vantage points for every future claim.

## Run 32848776574 — 2026-08-25T12:39:49Z UTC (Actions runner)

Method: unauthenticated GETs, project User-Agent, `-m 30`, 3 s spacing.

| Host | HTTP | Time (s) |
|---|---|---|
| `https://mcdonline.nic.in/` | 200 | 4.947469 |
| `https://bbmp.gov.in/` | 000 | 0 |
| `https://sahaaya2.bbmp.gov.in/` | 200 | 1.451784 |
| `https://data.opencity.in/api/3/action/package_search?q=grievance&rows=1` | 200 | 0.710819 |
| `https://sahaaya2.bbmpgov.in/` | 200 | 1.089192 |
| `https://nammabengaluru.s3.ap-south-1.amazonaws.com/` | 403 | 0.716664 |
| `https://web.archive.org/` | 200 | 0.490076 |
