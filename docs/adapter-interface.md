# The city-adapter contract

**Status: binding from 2026-08-25. This document is what Stage 7 tests.**

CLAUDE.md Stage 6 sets the rule: a pipeline carrying city-specific logic has
already failed forkability. This file defines the seam that keeps it true.
Code lives on one side of a line:

| `pipeline/` owns (mechanism) | `adapters/<city>.py` owns (portal) |
|---|---|
| selection-rule FORM (`SelectionRule`) | category string, window constants |
| global limiter (invariant 5) | detail endpoint + route quirks |
| resumable sweep journal | response → `TicketDetail` field mapping |
| hashing + detection ladder | image hosts, TLS trust policy |
| HTTP client plumbing | staff-filename timestamp grammar |

`pipeline/` may contain no portal names, no payload field names, no category
strings, no URLs. Everything about one portal lives in its single adapter
file. The reference implementation is `adapters/bengaluru.py`.

## The interface (`pipeline/adapter_api.py`)

An adapter provides a `CityAdapter` instance (module-level, e.g. `ADAPTER`)
with:

- `name: str` — short slug.
- `selection: SelectionRule` — the category and window this run audits.
- `detail_url(ticket_id) -> str` *(required)* — per-ticket endpoint; IDs
  arrive verbatim from the publisher's own dataset, never guessed
  (invariant 4).
- `parse_detail(payload) -> TicketDetail` *(required)* — whitelist mapping;
  tolerates missing/null fields, never raises on unexpected shapes.
- `image_plan(url) -> ImageFetch | None` — fetch parameters; TLS trust is
  per-host adapter policy because broken chains are documented properties of
  specific portals' infrastructure. `None` = unfetchable.
- `staff_resolution_timestamp(filename) -> str | None` — artifact-encoded
  resolution moment or None. A None is never turned into a timestamp.

Dataclasses `TicketDetail` and `ImageFetch` are the only shapes crossing the
seam. `check_adapter()` gives a structural self-check adapters assert in
their own tests.

## Invariant 1 is structural

`TicketDetail` is a closed whitelist of ticket facts. Adapters copy from
payloads ONLY into those fields; anything else on a payload — addresses,
free-text descriptions, staff names, contact details, device Make/Model
(banned outright by CLAUDE.md Stage 3) — is discarded by never being read.
Tests pin both sides: the field set, and that synthetic PII never survives
parsing.

## Adding a city (Stage 7 procedure)

1. Stage 0 probe for the new portal first — every finding is portal-specific;
   assume nothing carries over (CLAUDE.md Stage 7).
2. Ask for the new domains before anything else; they will not be reachable.
3. Write `adapters/<city>.py` and nothing else. If a portal seems to need a
   `pipeline/` change, the interface is wrong — fix the interface so the
   change lives in the adapter. A pipeline with `if city == ...` in it has
   failed Stage 6.
4. Assert `check_adapter(ADAPTER) == []` in the adapter's tests.
5. Re-measure precision per city at Stage 4 — thresholds do not transfer.

## Deliberately minimal

This interface has had exactly one implementer. It is a guess that has fit
one portal. Extend it only when a real second portal demands the change
(CLAUDE.md Stage 6); correcting a wrong guess with the second portal in hand
is cheaper than designing around one in advance.
