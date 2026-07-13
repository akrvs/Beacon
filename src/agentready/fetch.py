"""Polite HTTP client and the Site object passed to every check."""

from __future__ import annotations

import asyncio

import httpx

USER_AGENT = "AgentReadyBot/0.1 (+https://github.com/akrvs/agentready)"


def normalize_base_url(domain: str) -> str:
    domain = domain.strip().rstrip("/")
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    return domain


class Fetcher:
    """Caches GETs and serializes requests so an audit never hammers a host."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._cache: dict[str, httpx.Response | None] = {}
        self._lock = asyncio.Lock()

    def url_for(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return f"{self.base_url}/{path_or_url.lstrip('/')}"

    async def get(self, path_or_url: str) -> httpx.Response | None:
        """GET a URL, returning None on network-level failure."""
        url = self.url_for(path_or_url)
        async with self._lock:
            if url in self._cache:
                return self._cache[url]
            try:
                response: httpx.Response | None = await self._client.get(url)
            except httpx.HTTPError:
                response = None
            self._cache[url] = response
            await asyncio.sleep(0.2)
            return response

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class Site:
    """A domain under audit, with cached accessors for shared resources."""

    def __init__(self, domain: str, fetcher: Fetcher | None = None) -> None:
        self.base_url = normalize_base_url(domain)
        self.domain = httpx.URL(self.base_url).host
        self.fetcher = fetcher or Fetcher(self.base_url)

    async def get(self, path_or_url: str) -> httpx.Response | None:
        return await self.fetcher.get(path_or_url)

    async def robots_txt(self) -> str | None:
        response = await self.get("/robots.txt")
        if response is not None and response.status_code == 200:
            return response.text
        return None

    async def homepage(self) -> httpx.Response | None:
        return await self.get(self.base_url)

    async def aclose(self) -> None:
        await self.fetcher.aclose()
