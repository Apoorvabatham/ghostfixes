"""Rate-limited portal client built on the adapter interface.

Every request's full lifetime sits inside GlobalLimiter.request()
(invariant 5: starts <= 1 per 3 s across all hosts, honest User-Agent on
each). TLS trust decisions come only from adapter.image_plan — mechanism
never decides them. The transport is injectable (httpx.MockTransport) so
tests never touch a network.
"""

import httpx

from .limiter import GlobalLimiter


class PortalClient:
    def __init__(self, user_agent, limiter=None, timeout=30.0,
                 transport=None):
        if not user_agent:
            raise ValueError("an honest identifying User-Agent is required "
                             "(invariant 5)")
        self._user_agent = user_agent
        self._limiter = limiter or GlobalLimiter()
        self._timeout = timeout
        self._transport = transport
        self._clients = {}
        self.requests_made = 0

    def client_for(self, verify_tls: bool) -> httpx.Client:
        """One cached client per trust level; adapters map hosts to levels."""
        key = bool(verify_tls)
        client = self._clients.get(key)
        if client is None:
            kwargs = {
                "headers": {"User-Agent": self._user_agent},
                "timeout": self._timeout,
                "follow_redirects": True,
            }
            if self._transport is not None:
                kwargs["transport"] = self._transport
            client = httpx.Client(verify=key, **kwargs)
            self._clients[key] = client
        return client

    def get_bytes(self, url) -> httpx.Response:
        """Rate-limited full-body GET over verified TLS, response held in
        memory only. Publisher bulk CSVs contain PII-bearing columns, so
        they must never touch disk: callers parse straight from
        resp.content and drop it."""
        with self._limiter.request():
            self.requests_made += 1
            return self.client_for(True).get(url)

    def fetch_detail(self, adapter, ticket_id) -> httpx.Response:
        """One rate-limited detail GET over verified TLS. The response is
        returned raw; the caller journals status and parses."""
        url = adapter.detail_url(str(ticket_id))
        with self._limiter.request():
            self.requests_made += 1
            return self.client_for(True).get(url)

    def fetch_image(self, adapter, url):
        """Rate-limited image GET per adapter.image_plan; None = unfetchable
        (adapter said so), Response otherwise. Caller checks status_code."""
        plan = adapter.image_plan(url)
        if plan is None:
            return None
        with self._limiter.request():
            self.requests_made += 1
            return self.client_for(plan.verify_tls).get(plan.url)

    def close(self):
        for client in self._clients.values():
            client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
