"""The city-adapter contract — the seam between mechanism and portal.

`pipeline/` contains no portal names, no field names, no category strings,
no URLs. Each city lives in one `adapters/<city>.py` implementing exactly
this interface. The Stage 7 forkability test is that a new portal fits by
writing that one file and touching nothing else here.

Invariant 1 (no PII ever persisted) is enforced structurally:
`TicketDetail` is a CLOSED WHITELIST of the facts this project holds about
a ticket. An adapter's `parse_detail` must copy from payloads only into
those fields; keys outside the whitelist (addresses, free-text descriptions,
staff names, contact details) are discarded by never being read.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .selection import SelectionRule


@dataclass(frozen=True)
class TicketDetail:
    """Every field a parsed ticket may carry. Adding a field requires a
    written argument that it is neither PII nor device-identifying
    (CLAUDE.md Stage 3 bans Make/Model outright)."""

    ticket_id: str
    ward: str | None = None
    category: str | None = None
    sub_category: str | None = None
    filed_at_raw: str | None = None   # raw live-API filing timestamp
    citizen_status: str | None = None
    staff_status: str | None = None
    image_urls: tuple = ()


@dataclass(frozen=True)
class ImageFetch:
    """How to fetch one image URL. TLS trust is per-host adapter policy,
    because broken chains are properties of specific portals' infrastructure,
    documented per city."""

    url: str
    verify_tls: bool = True


class CityAdapter(ABC):
    """One municipal portal. Normative prose: docs/adapter-interface.md."""

    name: str                  # short slug for the city, e.g. 'city1'
    selection: SelectionRule   # which category and window this run audits

    @abstractmethod
    def detail_url(self, ticket_id: str) -> str:
        """Per-ticket detail endpoint. IDs arrive verbatim from the
        publisher's own dataset — never guessed (invariant 4)."""

    @abstractmethod
    def parse_detail(self, payload) -> TicketDetail:
        """Map one detail-response payload onto TicketDetail, copying
        whitelist fields only (invariant 1). Tolerate missing/null fields;
        never raise on unexpected shapes — return what is safely readable."""

    def image_plan(self, url: str) -> ImageFetch | None:
        """Fetch parameters for one image URL; None when unfetchable.
        Default: same URL over verified TLS."""
        return ImageFetch(url=url)

    def staff_resolution_timestamp(self, filename: str) -> str | None:
        """Resolution moment encoded in a staff-photo filename, canonical
        'YYYY-MM-DDTHH:MM:SS', or None. Portals without such artifacts keep
        this default. None is never converted into a timestamp."""
        return None


def check_adapter(adapter) -> list:
    """Structural conformance self-check; an empty list means usable.
    Adapters should assert this in their own tests."""
    problems = []
    name = getattr(adapter, "name", None)
    if not isinstance(name, str) or not name:
        problems.append("name must be a non-empty string")
    if not isinstance(getattr(adapter, "selection", None), SelectionRule):
        problems.append("selection must be a SelectionRule instance")
    for member in ("detail_url", "parse_detail"):
        if not callable(getattr(adapter, member, None)):
            problems.append(f"{member} must be implemented")
    return problems
