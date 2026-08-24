#!/usr/bin/env python3
"""GhostFixes — Stage 0 feasibility probe (throwaway, CLAUDE.md Stage 0).

Answers the seven Stage 0 questions against whatever is reachable from this
sandbox, printing a per-phase report and dropping raw evidence in probe/out/
(gitignored — raw pages may contain unfetched PII, invariant 1).

Invariants honoured here:
  * invariant 4: unauthenticated GETs, publicly browsable endpoints only.
    No ticket-ID guessing — we follow links found on pages we legitimately
    fetched, or IDs already published in open datasets.
  * invariant 5: 1 request / 3 s, global and hard; honest User-Agent with
    project name + contact email on every request.
  * invariant 1: console output shows structure (URLs, JSON keys, tags),
    never personal details. Raw bodies stay in probe/out/.

Usage: PYTHONPATH=$PWD/pylibs python3 probe/probe.py --phase p1   (etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

PROBE_DIR = Path(__file__).resolve().parent
OUT = PROBE_DIR / "out"

CONTACT_EMAIL = "apba00001@uni-saarland.de"  # approved for UA use 2026-08-24
USER_AGENT = (
    "GhostFixes/0.0-stage0 "
    "(+https://github.com/Apoorvabatham/ghostfixes; "
    f"contact: {CONTACT_EMAIL})"
)

MIN_REQUEST_GAP_S = 3.0  # invariant 5, hard floor


class Limiter:
    """Global wall-clock gate: >= MIN_REQUEST_GAP_S between request starts."""

    def __init__(self, gap_s: float) -> None:
        self.gap_s = gap_s
        self._last_start = float("-inf")

    def wait(self) -> None:
        delta = self.gap_s - (time.monotonic() - self._last_start)
        if delta > 0:
            time.sleep(delta)
        self._last_start = time.monotonic()


LIMITER = Limiter(MIN_REQUEST_GAP_S)

_client = None


def _client_get():
    global _client
    if _client is None:
        import httpx

        _client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _client


def _log(record: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    status = record.get("status")
    line = f"[{status if status is not None else record.get('error', '?')}] {record['url']}"
    if record.get("note"):
        line += f"  ({record['note']})"
    print(line)


def fetch(url: str, *, save_to: str | None = None, note: str = ""):
    """One rate-limited, logged GET. Returns httpx.Response or None."""
    LIMITER.wait()
    started = time.monotonic()
    try:
        resp = _client_get().get(url, timeout=30.0)
    except Exception as exc:  # noqa: BLE001 — probe reports everything
        msg = f"{type(exc).__name__}: {exc}"
        # A TLS failure may be the sandbox, not the portal — flag it so the
        # report never confuses "blocked here" with "portal denied us".
        retried_unverified = False
        if "ertificate" in msg or "SSL" in msg or "TLS" in msg.upper():
            try:
                LIMITER.wait()
                import httpx

                loose = httpx.Client(
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                    verify=False,
                )
                started = time.monotonic()
                resp = loose.get(url, timeout=30.0)
                retried_unverified = True
            except Exception as exc2:  # noqa: BLE001
                _log({"url": url, "status": None, "error": f"{type(exc).__name__}: {exc}"[:300],
                      "retry_unverified_error": str(exc2)[:200], "note": note})
                return None
        else:
            _log({"url": url, "status": None, "error": msg[:300], "note": note})
            return None
        record_extra = {"ssl_retry_unverified": True} if retried_unverified else {}
    else:
        record_extra = {}

    elapsed = round(time.monotonic() - started, 2)
    record = {
        "url": url,
        "status": resp.status_code,
        "final_url": str(resp.url),
        "elapsed_s": elapsed,
        "content_type": resp.headers.get("content-type", ""),
        "bytes": len(resp.content),
        "note": note,
        **record_extra,
    }
    if save_to:  # save regardless of status — error bodies are evidence too
        path = OUT / save_to
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content[:5_000_000])
        record["saved_to"] = save_to
    _log(record)
    return resp


LINK_RE = re.compile(r"""(?:href|src|action)\s*=\s*["']([^"'#\s]+)["']""", re.I)
KEYWORDS = re.compile(
    r"(grievan|complaint|311|open311|georeport|sahaaya|sahaya|helpline|"
    r"samadhan|pgms|citizen|track|status|api)",
    re.I,
)


def scan_links(html: str, base_url: str) -> list[str]:
    """Absolute-ise links on a fetched page whose target looks relevant."""
    found = []
    seen = set()
    for m in LINK_RE.finditer(html):
        absu = urljoin(base_url, m.group(1))
        if absu.startswith(("mailto:", "javascript:", "tel:")):
            continue
        if not KEYWORDS.search(absu):
            continue
        if absu in seen:
            continue
        seen.add(absu)
        found.append(absu)
    return found


def scan_links_all(html: str, base_url: str) -> list[str]:
    """Same, without the keyword filter (for offline inspection in probe/out)."""
    out, seen = [], set()
    for m in LINK_RE.finditer(html):
        absu = urljoin(base_url, m.group(1))
        if not absu.startswith(("mailto:", "javascript:", "tel:", "data:")) and absu not in seen:
            seen.add(absu)
            out.append(absu)
    return out


def has_viewstate(text: str) -> bool:
    return "__VIEWSTATE" in text


def phase_p1() -> dict:
    """Item 1: sanctioned Open311 API on the MCD vendor domain?

    Also seeds items 3/4/5: what the site serves logged-out, and whether
    pages are ASP.NET WebForms (__VIEWSTATE) or JSON-driven.
    """
    print("\n=== P1: MCD (mcdonline.nic.in) — Open311 discovery + surface scan ===")
    base = "https://mcdonline.nic.in"
    std_paths = [
        "/robots.txt",
        "/",
        "/open311/v2/discovery.json",
        "/georeport/v2/discovery.json",
        "/georeport/v2/requests.json",
        "/api/v2/discovery.json",
        "/api/v2/",
    ]
    hits = {}
    for i, path in enumerate(std_paths):
        save = None
        if path == "/":
            save = "pages/mcd_home.html"
        elif path == "/robots.txt":
            save = "pages/mcd_robots.txt"
        r = fetch(base + path, save_to=save, note=f"std-path {i + 1}/{len(std_paths)}")
        if r is not None and r.status_code < 400:
            hits[path] = {
                "status": r.status_code,
                "ctype": r.headers.get("content-type", ""),
                "bytes": len(r.content),
                "viewstate": has_viewstate(r.text[:200_000]),
            }

    print("\n-- Standard-path results --")
    for path, info in hits.items():
        flags = []
        if info["viewstate"]:
            flags.append("__VIEWSTATE present")
        print(f"  {path}: {info['status']} {info['ctype']} {info['bytes']}B {' '.join(flags)}")

    home = (OUT / "pages/mcd_home.html")
    candidates: list[str] = []
    if home.exists():
        candidates = scan_links(home.read_text(encoding="utf-8", errors="replace"), base + "/")
        print(f"\n-- Relevant links on home page ({len(candidates)}) --")
        for c in candidates[:40]:
            print(f"  {c}")
        # second hop: MCD 311 lives under its own subpath; scan one level deep
        # for anything that looks like the 311/grievance app front door.
        three11 = [c for c in candidates if "311" in c or "grievan" in c.lower()]
        for u in three11[:3]:
            r = fetch(u, save_to="pages/" + re.sub(r"\W+", "_", u)[-80:] + ".html")
            if r is not None and r.status_code < 400:
                sub = scan_links(r.text, u)
                if sub:
                    print(f"  -- links under {u} --")
                    for s in sub[:20]:
                        print(f"    {s}")

    result = {"open311_hits": hits, "candidate_links": candidates}
    (OUT / "p1_result.json").write_text(json.dumps(result, indent=2))
    return result


def phase_p1b() -> dict:
    """P1 follow-up: the /portal front door + the 403 JSON on /api/v2/*."""
    print("\n=== P1b: mcdonline.nic.in/portal front door + /api/v2 403 bodies ===")
    result: dict = {}

    r = fetch("https://mcdonline.nic.in/api/v2/discovery.json",
              save_to="pages/mcd_apiv2_discovery_403.json", note="read 403 body")
    if r is not None:
        result["apiv2_discovery_body"] = r.text[:500]

    r = fetch("https://mcdonline.nic.in/api/v2/",
              save_to="pages/mcd_apiv2_403.json", note="read 403 body")
    if r is not None:
        result["apiv2_body"] = r.text[:500]
        for k, v in r.headers.items():
            if k.lower() in ("server", "www-authenticate", "allow", "content-type"):
                print(f"  header {k}: {v}")

    r = fetch("https://mcdonline.nic.in/portal", save_to="pages/mcd_portal.html",
              note="front door")
    if r is not None and r.status_code < 400:
        text = r.text
        print(f"  portal page: {len(r.content)} bytes; "
              f"__VIEWSTATE={has_viewstate(text)}; "
              f"angular/react hints: "
              f"ng-app={('ng-app' in text) or ('ng-app' not in text and 'angular' in text.lower())}, "
              f"react={'__NEXT_DATA__' in text or 'react' in text.lower()}, "
              f"nuxt={{'_nuxt' in text.lower()}}, "
              f"api-fetch-hints={len(re.findall(r'/api/', text))}")
        all_links = scan_links_all(text, "https://mcdonline.nic.in/portal")
        (OUT / "p1b_all_links.json").write_text(json.dumps(all_links, indent=2))
        relevant = [u for u in all_links if KEYWORDS.search(u)]
        print(f"  links total {len(all_links)} (dumped to p1b_all_links.json); keyword-matched:")
        for u in relevant[:40]:
            print(f"    {u}")
        result["portal_viewstate"] = has_viewstate(text)
        result["all_links"] = len(all_links)

    return result


ESBM_CONSOLE = ("https://mcdonline.nic.in/esbm-mcd/citizenMap/"
                "doShowRootMonitoringPublicConsole")


def phase_p1c() -> dict:
    """P1c: capture /api/v2 403 bodies; probe the public eSBM monitoring
    console on the allowed host."""
    print("\n=== P1c: /api/v2 403 bodies + eSBM public monitoring console ===")
    result: dict = {}

    r = fetch("https://mcdonline.nic.in/api/v2/discovery.json",
              save_to="pages/mcd_apiv2_discovery_403.json")
    if r is not None:
        print(f"  discovery.json 403 body: {r.text[:300]!r}")
        result["apiv2_discovery_body"] = r.text[:300]

    r = fetch(ESBM_CONSOLE, save_to="pages/mcd_esbm_console.html",
              note="public monitoring console")
    if r is not None and r.status_code < 400:
        text = r.text
        json_hints = len(re.findall(r"\.json|/api/|ajax", text, re.I))
        print(f"  console page {len(r.content)}B; __VIEWSTATE={has_viewstate(text)}; "
              f"json-hints={json_hints}")
        links = scan_links_all(text, ESBM_CONSOLE)
        (OUT / "p1c_esbm_links.json").write_text(json.dumps(links, indent=2))
        print(f"  links: {len(links)} (dumped)")
        for u in [u for u in links if KEYWORDS.search(u)][:25]:
            print(f"    {u}")
        # forms on the page = how a logged-out visitor queries it
        for m in re.findall(r"""<form[^>]*action=["']?([^"' >]+)""", text, re.I):
            print(f"  form action: {urljoin(ESBM_CONSOLE, m)}")
    return result


TARGET_PACKAGES = [
    "bbmp-grievances-data",
    "bbmp-fix-my-street-data",
    "bengaluru-central-city-corporation-pothole-filling-updates",
]


def phase_p2b() -> dict:
    """P2b: schemas of the three actually-relevant published datasets."""
    print("\n=== P2b: targeted package_show + datastore schemas ===")
    result = {}
    for name in TARGET_PACKAGES:
        r = fetch(f"{CKAN}/package_show?id={name}", note=f"show:{name}")
        if r is None or r.status_code != 200:
            continue
        pkg = r.json().get("result", {})
        print(f"\n-- {name} :: {pkg.get('title')} --")
        print(f"   updated {pkg.get('metadata_modified', '')[:10]}")
        notes = (pkg.get("notes") or "")[:400].replace("\n", " ")
        if notes:
            print(f"   notes: {notes}")
        entries = []
        for res in pkg.get("resources", []):
            entry = {"name": res.get("name") or res.get("description") or "",
                     "format": res.get("format"), "size": res.get("size"),
                     "url": res.get("url"), "id": res.get("id")}
            entries.append(entry)
            print(f"   resource [{entry['format']}] {entry['name']!r} "
                  f"size={entry['size']} id={entry['id']}")
            if res.get("datastore_active"):
                d = fetch(f"{CKAN}/datastore_search?resource_id={res['id']}&limit=1",
                          note=f"schema:{name}")
                if d is not None and d.status_code == 200:
                    payload = d.json().get("result", {})
                    fields = [f["id"] for f in payload.get("fields", [])]
                    entry["fields"] = fields
                    entry["rows_total"] = payload.get("total")
                    print(f"     -> fields ({len(fields)}): {fields}")
                    print(f"     -> rows ~{payload.get('total')}")
        result[name] = entries
    (OUT / "p2b_result.json").write_text(json.dumps(result, indent=2))
    return result


SAFE_FIELDS = {"_id", "complaint id", "category", "sub category", "grievance date",
               "ward name", "grievance status"}  # never print staff remarks/names


def phase_p2c() -> dict:
    """P2c: sanitized sample rows from the 2025 grievances CSV + scan
    bbmp.gov.in for the public complaint-tracking surface those IDs resolve."""
    print("\n=== P2c: sample rows (sanitised) + bbmp.gov.in surface scan ===")
    result = {}
    res_id = "1342a93b-9a61-4766-9c34-c8357b7926c2"  # BBMP Grievances 2025
    r = fetch(f"{CKAN}/datastore_search?resource_id={res_id}&limit=5", note="sample rows")
    if r is not None and r.status_code == 200:
        for rec in r.json().get("result", {}).get("records", []):
            safe = {k: v for k, v in rec.items() if k.strip().lower() in SAFE_FIELDS}
            print(f"   {safe}")
            result.setdefault("sample_ids", []).append(safe.get("Complaint ID"))

    base = "https://bbmp.gov.in"
    r = fetch(base + "/", save_to="pages/bbmp_home.html", note="BBMP home")
    if r is not None and r.status_code < 400:
        text = r.text
        print(f"\n  bbmp.gov.in home {len(r.content)}B __VIEWSTATE={has_viewstate(text)}")
        links = scan_links_all(text, base + "/")
        (OUT / "p2c_bbmp_links.json").write_text(json.dumps(links, indent=2))
        rel = [u for u in links if KEYWORDS.search(u)]
        print(f"  links {len(links)} total; keyword-matched:")
        for u in rel[:30]:
            print(f"    {u}")
        result["bbmp_links"] = rel
    return result


def phase_p2d() -> dict:
    """P2d: pull the GBA/BBMP React bundle and mine it for the JSON endpoints
    the SPA calls (Stage 0 item 5) — especially complaint tracking."""
    print("\n=== P2d: bbmp.gov.in (GBA) JS bundle -> endpoint mining ===")
    r = fetch("https://bbmp.gov.in/static/js/main.b20559ca.js",
              save_to="pages/bbmp_main_bundle.js", note="SPA bundle")
    if r is None:
        return {}
    js = r.text
    print(f"  bundle {len(r.content)} bytes")

    # absolute endpoints named in the code
    urls = sorted(set(re.findall(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", js)))
    interesting_urls = [u for u in urls if KEYWORDS.search(u)]
    print(f"-- absolute URLs mentioning grievance/complaint/etc ({len(interesting_urls)}) --")
    for u in interesting_urls[:30]:
        print(f"   {u}")

    # relative path literals that look like API routes
    rels = sorted(set(re.findall(
        r"[\"']((?:/[A-Za-z0-9_.-]+)+(?:/[A-Za-z0-9_.?=&-]+)?)[\"']", js)))
    rel_hits = [p for p in rels if KEYWORDS.search(p)]
    print(f"-- relative literals matching keywords ({len(rel_hits)}) --")
    for p in rel_hits[:40]:
        print(f"   {p}")

    # any baseURL-style constants near 'api'
    bases = sorted(set(re.findall(
        r"[\"']([^\"']*(?:api|API)[^\"']*)[\"']", js)))[:60]
    print(f"-- string literals containing 'api' ({len(bases)}, first 40) --")
    for b in bases[:40]:
        print(f"   {b[:120]}")

    (OUT / "p2d_endpoints.json").write_text(json.dumps(
        {"urls": interesting_urls, "rel": rel_hits, "api_literals": bases}, indent=2))
    return {}


def phase_p3a() -> dict:
    """P3a: probe Sahaaya v2 + ehelpline + GBA API base, all on *.bbmp.gov.in
    (allowlisted). Logged-out, link-following only."""
    print("\n=== P3a: sahaaya2 / ehelpline / api.bbmpgov.in surface ===")
    result = {}

    r = fetch("https://sahaaya2.bbmp.gov.in/", save_to="pages/sahaaya2_home.html",
              note="Sahaaya v2")
    if r is not None and r.status_code < 400:
        text = r.text
        print(f"  sahaaya2 home {len(r.content)}B __VIEWSTATE={has_viewstate(text)}")
        links = scan_links_all(text, "https://sahaaya2.bbmp.gov.in/")
        (OUT / "p3a_sahaaya_links.json").write_text(json.dumps(links, indent=2))
        rel = [u for u in links if KEYWORDS.search(u)]
        print(f"  links {len(links)}; keyword-matched:")
        for u in rel[:30]:
            print(f"    {u}")
        # one level deeper on the most promising tracking-style link
        track = [u for u in rel if re.search(r"track|status|detail", u, re.I)]
        for u in track[:2]:
            rr = fetch(u, save_to="pages/" + re.sub(r"\W+", "_", u)[-70:] + ".html")
            if rr is not None and rr.status_code < 400:
                print(f"    -> {u}: __VIEWSTATE={has_viewstate(rr.text)} "
                      f"forms={re.findall(r'<form', rr.text, re.I)}")
                sub = [s for s in scan_links_all(rr.text, u) if KEYWORDS.search(s)]
                for s in sub[:15]:
                    print(f"       {s}")

    r = fetch("https://support.bbmpgov.in/ehelpline/CitizensCreateTickets.aspx",
              save_to="pages/bbmp_ehelpline_create.html", note="ehelpline create-ticket")
    if r is not None:
        vs = has_viewstate(r.text)
        print(f"\n  ehelpline page {r.status_code} {len(r.content)}B __VIEWSTATE={vs}")
        result["ehelpline_viewstate"] = vs

    r = fetch("https://api.bbmpgov.in/gba/v1", note="API base probe")
    if r is not None:
        body = r.text[:200].replace("\n", " ")
        print(f"\n  api.bbmpgov.in/gba/v1 -> {r.status_code} {body!r}")
    return result


# Exact public URLs as printed on mcdonline.nic.in/portal (invariant 4: we
# browse these links as published; the embedded app_id/api_key is never reused
# against any other endpoint).
MCD_CREATE_URL = ("https://mcd.everythingcivic.com/citizen/createissue"
                  "?app_id=U2FsdGVkX180J3mGnJmT5QpgtPjhfjtzyXAAccBUxGU%3D"
                  "&api_key=e34ba86d3943bd6db9120313da011937189e6a9625170905"
                  "750f649395bcd68312cf10d264c9305d57c23688cc2e5120")
MCD_DETAIL_URL = ("https://mcd.everythingcivic.com/citizen/issuedetail"
                  "?app_id=U2FsdGVkX180J3mGnJmT5QpgtPjhfjtzyXAAccBUxGU%3D"
                  "&api_key=e34ba86d3943bd6db9120313da011937189e6a9625170905"
                  "750f649395bcd68312cf10d264c9305d57c23688cc2e5120")


def phase_p4a() -> dict:
    """P4a: fetch the two public MCD-311 vendor pages verbatim; identify the
    tech stack and any further public endpoints they reference."""
    print("\n=== P4a: mcd.everythingcivic.com public pages ===")
    result = {}
    for label, url, save in [
        ("createissue", MCD_CREATE_URL, "pages/mcd_ec_createissue.html"),
        ("issuedetail", MCD_DETAIL_URL, "pages/mcd_ec_issuedetail.html"),
    ]:
        r = fetch(url, save_to=save, note=label)
        if r is None:
            continue
        text = r.text
        print(f"\n-- {label}: {r.status_code} {len(r.content)}B "
              f"__VIEWSTATE={has_viewstate(text)}")
        # what loads next? script bundles, XHR paths, meta refresh
        scripts = sorted(set(re.findall(r"""<script[^>]*src=["']([^"']+)["']""", text, re.I)))
        for s in scripts[:15]:
            print(f"   script: {urljoin(url, s)}")
        xhrs = sorted(set(re.findall(
            r"""["']((?:/[A-Za-z0-9_.-]+){1,4}(?:\.(?:json|js))?["'])""",
            text)))[:20]
        if not scripts:
            head = re.sub(r"\s+", " ", text)[:400]
            print(f"   body head: {head}")
    return result


def phase_p4b() -> dict:
    """P4b: mine the MCD-311 vendor SPA bundle for API endpoints and routes."""
    print("\n=== P4b: everythingcivic SPA bundle -> endpoint/route mining ===")
    r = fetch("https://mcd.everythingcivic.com/static/js/main.5ecd4fb8.js",
              save_to="pages/mcd_ec_bundle.js", note="SPA bundle")
    if r is None:
        return {}
    js = r.text
    print(f"  bundle {len(r.content)} bytes")

    urls = sorted(set(re.findall(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", js)))
    ext = [u for u in urls if "everythingcivic" not in u]
    print(f"-- external hosts referenced --")
    hosts = sorted(set(re.match(r"https?://([^/]+)", u).group(1) for u in urls))
    for h in hosts:
        print(f"   {h}")

    rels = sorted(set(re.findall(
        r"[\"']((?:/[A-Za-z0-9_.-]+){1,5})[\"']", js)))
    kw = [p for p in rels if re.search(
        r"issue|track|status|complaint|grievance|detail|citizen", p, re.I)]
    print(f"-- path literals matching keywords ({len(kw)}) --")
    for p in kw[:50]:
        print(f"   {p}")

    # react-router style route table entries
    routes = sorted(set(re.findall(r"path:\s*[\"']([^\"']{1,60})[\"']", js)))
    print(f"-- router paths ({len(routes)}) --")
    for p in routes[:40]:
        print(f"   {p}")

    (OUT / "p4b_endpoints.json").write_text(json.dumps(
        {"hosts": hosts, "paths": kw, "routes": routes}, indent=2))
    return {}


def phase_p3b() -> dict:
    """P3b: retry api.bbmpgov.in; probe support.bbmpgov.in ehelpline with
    flagged SSL-unverified fallback."""
    print("\n=== P3b: api.bbmpgov.in retry + ehelpline (cert-flagged) ===")
    result = {}
    r = fetch("https://api.bbmpgov.in/gba/v1", note="retry after allowlist change")
    if r is not None:
        print(f"  api.bbmpgov.in/gba/v1 -> {r.status_code} {r.text[:150]!r}")
        result["api_status"] = r.status_code

    r = fetch("https://support.bbmpgov.in/ehelpline/CitizensCreateTickets.aspx",
              save_to="pages/bbmp_ehelpline_create.html", note="cert-fallback probe")
    if r is not None:
        text = r.text
        vs = has_viewstate(text)
        print(f"\n  ehelpline {r.status_code} {len(r.content)}B __VIEWSTATE={vs}")
        result["ehelpline_viewstate"] = vs
        links = scan_links_all(text, "https://support.bbmpgov.in/ehelpline/")
        rel = [u for u in links if KEYWORDS.search(u)]
        for u in rel[:20]:
            print(f"    {u}")
        # look for sibling .aspx pages referenced anywhere (status/track views)
        sibs = sorted(set(re.findall(
            r"""([A-Za-z0-9_]+\.aspx)["'?]""", text)))
        print(f"  aspx siblings: {sibs[:25]}")
        result["aspx_siblings"] = sibs
    return result


def phase_p3c() -> dict:
    """P3c: CitizensSearchTickets.aspx — public logged-out ticket lookup?
    Uses exactly one Complaint ID taken from BBMP's own published open
    dataset (not guessed, not enumerated). Raw response stays in probe/out;
    console shows structure/status/image URLs only."""
    import httpx

    print("\n=== P3c: ehelpline CitizensSearchTickets (logged-out lookup) ===")
    base = "https://support.bbmpgov.in/ehelpline/CitizensSearchTickets.aspx"
    r = fetch(base, save_to="pages/bbmp_search_tickets.html")
    if r is None:
        return {}
    html = r.text
    inputs = re.findall(r"""<input[^>]*name=["']([^"']+)["'][^>]*""", html)
    selects = re.findall(r"""<select[^>]*name=["']([^"']+)["']""", html)
    visible = [i for i in inputs if not i.startswith("__")]
    print(f"  form inputs: {visible}")
    print(f"  form selects: {selects}")
    print(f"  has EVENTVALIDATION: {'__EVENTVALIDATION' in html}")
    labels = re.findall(r"""<label[^>]*>([^<]{1,60})</label>""", html)
    print(f"  labels: {labels[:12]}")

    # Round-trip like a browser: GET -> post back VIEWSTATE/EVENTVALIDATION +
    # the first visible field filled with the one published ID.
    vs = re.search(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', html)
    ev = re.search(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', html)
    vg = re.search(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', html)
    if not (vs and ev and visible):
        print("  !! cannot round-trip: missing viewstate/validation/fields")
        return {}
    published_id = "20771690"  # from bbmp-grievances-data 2025 CSV row _id 1
    data = {
        "__VIEWSTATE": vs.group(1),
        "__EVENTVALIDATION": ev.group(1),
    }
    if vg:
        data["__VIEWSTATEGENERATOR"] = vg.group(1)
    ticket_field = [f for f in visible if f.lower().endswith("txtticketno")]
    data[ticket_field[0] if ticket_field else visible[-1]] = published_id
    print(f"  filling field: {ticket_field or visible[-1]}")
    # submit button name=value if present
    btn = re.search(r'<input[^>]*type="(?:submit|button)"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html)
    if btn and not btn.group(1).startswith("__"):
        data[btn.group(1)] = btn.group(2)
        print(f"  submitting via button {btn.group(1)}")

    LIMITER.wait()
    loose = httpx.Client(headers={"User-Agent": USER_AGENT},
                         follow_redirects=True, verify=False)
    resp = loose.post(base, data=data, timeout=30.0)
    (OUT / "pages/bbmp_search_result.html").write_bytes(resp.content[:5_000_000])
    print(f"  POST -> {resp.status_code} {len(resp.content)}B "
          f"(saved pages/bbmp_search_result.html)")
    imgs = sorted(set(re.findall(
        r"""(?:src|href)=["']([^"']*(?:\.jpe?g|\.png|image[^"']*))["']""",
        resp.text, re.I)))
    print(f"  image-ish refs ({len(imgs)}):")
    for u in imgs[:15]:
        print(f"    {urljoin(str(resp.url), u)[:140]}")
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", resp.text, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    print(f"  text head (PII-scan before quoting further): {txt[:300]!r}")
    return {"status": resp.status_code}


CKAN = "https://data.opencity.in/api/3/action"


def phase_p2() -> dict:
    """Item 2: is the data already published on data.opencity.in (CKAN)?"""
    print("\n=== P2: data.opencity.in — existing published datasets ===")
    packages: dict[str, dict] = {}
    for query in ("grievance", "bbmp", "pothole"):
        r = fetch(f"{CKAN}/package_search?q={query}&rows=40", note=f"search:{query}")
        if r is None or r.status_code != 200:
            continue
        payload = r.json().get("result", {})
        print(f"-- q={query}: {payload.get('count', '?')} datasets --")
        for pkg in payload.get("results", []):
            name = pkg.get("name", "")
            if name and name not in packages:
                packages[name] = {
                    "title": pkg.get("title", ""),
                    "notes_head": (pkg.get("notes") or "")[:160].replace("\n", " "),
                    "org": (pkg.get("organization") or {}).get("title", ""),
                    "updated": pkg.get("metadata_modified", ""),
                }
                print(f"  {name}  |  {packages[name]['title']}  [{packages[name]['org']}]")

    # Field-level look at the most promising packages, without downloading
    # whole resources: datastore_search returns the schema with limit=1.
    interesting = [n for n in packages if re.search(r"grievan|complaint|pothole|sahaaya|bbmp", n)]
    schemas = {}
    for name in sorted(interesting)[:6]:
        r = fetch(f"{CKAN}/package_show?id={name}", note=f"show:{name}")
        if r is None or r.status_code != 200:
            continue
        resources = r.json().get("result", {}).get("resources", [])
        listing = []
        for res in resources:
            entry = {
                "id": res.get("id"),
                "name": res.get("name") or res.get("description") or "",
                "format": res.get("format"),
                "size": res.get("size"),
                "url": res.get("url"),
            }
            listing.append(entry)
            if res.get("datastore_active"):
                d = fetch(f"{CKAN}/datastore_search?resource_id={res['id']}&limit=1",
                          note=f"schema:{name}")
                if d is not None and d.status_code == 200:
                    fields = [f["id"] for f in d.json().get("result", {}).get("fields", [])]
                    total = d.json().get("result", {}).get("total")
                    entry["fields"] = fields
                    entry["rows_total"] = total
                    print(f"  * {name} :: {entry['name']} -> fields={fields} rows~{total}")
        schemas[name] = listing

    result = {"packages": packages, "schemas": schemas}
    (OUT / "p2_result.json").write_text(json.dumps(result, indent=2))
    return result


PHASES = {
    "p1": ("Open311 discovery + MCD surface scan (items 1, 5)", phase_p1),
    "p1b": ("MCD /portal front door + /api/v2 403 bodies (items 1, 5)", phase_p1b),
    "p1c": ("/api/v2 403 bodies + eSBM public monitoring console (item 5)", phase_p1c),
    "p2": ("opencity.in published-dataset survey (item 2)", phase_p2),
    "p2b": ("schemas of the three target opencity datasets (item 2)", phase_p2b),
    "p2c": ("sample grievance rows + bbmp.gov.in tracking surface (items 2, 3)", phase_p2c),
    "p2d": ("GBA SPA bundle endpoint mining (item 5)", phase_p2d),
    "p3a": ("sahaaya2 / ehelpline / api base surface (items 3-5)", phase_p3a),
    "p3b": ("api.bbmpgov.in retry + ehelpline cert-flagged probe", phase_p3b),
    "p3c": ("ehelpline ticket lookup round-trip (items 3-6)", phase_p3c),
    "p4a": ("mcd.everythingcivic.com public pages (items 3-5, Delhi)", phase_p4a),
    "p4b": ("everythingcivic bundle endpoint mining (item 5)", phase_p4b),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=[*PHASES, "all"], required=True)
    args = ap.parse_args()
    print(f"GhostFixes Stage 0 probe — UA: {USER_AGENT}")
    selected = list(PHASES) if args.phase == "all" else [args.phase]
    failures = 0
    for key in selected:
        title, fn = PHASES[key]
        print(f"\n########## PHASE {key.upper()}: {title} ##########")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — a dead phase must not kill the rest
            failures += 1
            print(f"!! phase {key} crashed: {type(exc).__name__}: {exc}")
    print("\nDone." + (" (with phase failures)" if failures else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
