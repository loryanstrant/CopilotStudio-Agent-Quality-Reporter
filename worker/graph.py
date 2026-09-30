"""Microsoft Graph client, scoped to resolving one known person at a time.

There is exactly one read in this file, and it takes a UPN:
``GET /v1.0/users/{upn}``. There is deliberately **no** call to the ``/users``
collection, no ``$filter`` over it and no paging helper — so a tenant-wide
directory enumeration is not something this module is configured not to do, it
is something it cannot do. That was the owner's ruling on the feature and this
is where it is enforced; ``tests/test_creators_sync.py`` asserts the URL shape.

Authentication reuses the service principal already configured for Dataverse
(the same one ``api/oidc.py`` uses for group checks), so no second app
registration is needed — but it does need the **User.Read.All** application
permission and admin consent, which is a step on the tenant's side. Without it
Graph answers 403 and :class:`GraphConsentError` is raised once for the whole
sync rather than once per person.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any
from urllib.parse import quote

import httpx
import msal

logger = logging.getLogger("worker.graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = ["https://graph.microsoft.com/.default"]
_MAX_RETRIES = 4
_MAX_BACKOFF_SECONDS = 30.0

# The fields the creator directory stores. Requesting only these keeps the
# lookup to what the product shows, rather than pulling a whole user object.
_USER_SELECT = "id,userPrincipalName,displayName,department,jobTitle,officeLocation"


class GraphError(RuntimeError):
    """Graph returned an error this client cannot recover from."""


class GraphAuthError(GraphError):
    """An app-only token could not be acquired (credentials wrong or expired)."""


class GraphConsentError(GraphError):
    """Graph refused the call: ``User.Read.All`` has not been consented.

    Separate from :class:`GraphError` because the remedy is a one-off consent
    step by a tenant administrator, not a retry — so the sync stops and says so
    instead of walking every creator to collect the same 403 each time.
    """


class GraphNotFound(GraphError):
    """No such user. The creator is kept, unresolved, by the caller."""


class GraphUserLookup:
    """Resolves individual UPNs to their directory details.

    Use as an async context manager; the HTTP client and the MSAL token cache
    live for the life of the instance, which is one sync.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        concurrency: int = 5,
        timeout: float = 30.0,
    ) -> None:
        # MSAL fetches the authority's OIDC metadata when the application is
        # constructed, so building it here would make creating a lookup a network
        # call — which fails in an offline test run and would turn a
        # misconfigured tenant into an error raised in the wrong place.
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._app: msal.ConfidentialClientApplication | None = None
        self._client = httpx.AsyncClient(timeout=timeout)
        # Bounded, because a tenant with a few hundred makers would otherwise
        # open a few hundred sockets and earn a 429 for its trouble.
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "GraphUserLookup":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def token(self) -> str:
        """An app-only access token (MSAL caches it between calls)."""
        if self._app is None:
            self._app = await asyncio.to_thread(
                msal.ConfidentialClientApplication,
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                client_credential=self._client_secret,
            )
        result = await asyncio.to_thread(
            self._app.acquire_token_for_client, scopes=_SCOPE
        )
        access = result.get("access_token")
        if not access:
            raise GraphAuthError(
                result.get("error_description") or result.get("error") or "token failed"
            )
        return str(access)

    async def get_user(self, upn: str) -> dict[str, Any]:
        """Directory details for one person, by UPN.

        Returns a dict with the keys the ``agent_creators`` row needs, including
        the manager's id and display name. Raises :class:`GraphNotFound` when
        the UPN does not resolve, and :class:`GraphConsentError` when the
        permission is missing.
        """
        # The manager is expanded rather than fetched separately: one request
        # per person instead of two, and it is the field the team grouping falls
        # back to when departments are not populated.
        user = await self._get(
            f"{GRAPH_BASE}/users/{quote(upn, safe='@')}",
            params={"$select": _USER_SELECT, "$expand": "manager($select=id,displayName)"},
        )
        manager = user.get("manager") or {}
        return {
            "entra_user_id": user.get("id"),
            "upn": user.get("userPrincipalName") or upn,
            "display_name": user.get("displayName"),
            "department": user.get("department"),
            "job_title": user.get("jobTitle"),
            "office_location": user.get("officeLocation"),
            "manager_id": manager.get("id"),
            "manager_name": manager.get("displayName"),
        }

    async def _get(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        """GET with Retry-After-aware backoff on 429 and 5xx."""
        for attempt in range(_MAX_RETRIES + 1):
            token = await self.token()
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            async with self._sem:
                resp = await self._client.get(url, params=params, headers=headers)

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= _MAX_RETRIES:
                    raise GraphError(f"Graph {resp.status_code} after retries")
                delay = self._retry_delay(resp, attempt)
                logger.warning(
                    "Graph %s (attempt %d); retrying in %.1fs",
                    resp.status_code,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code == 404:
                raise GraphNotFound(upn_from(url))
            if resp.status_code in (401, 403):
                raise GraphConsentError(
                    "Graph refused the directory lookup "
                    f"({resp.status_code}). The app registration needs the "
                    "User.Read.All application permission with admin consent."
                )
            if resp.status_code >= 400:
                raise GraphError(f"Graph {resp.status_code}: {resp.text[:300]}")
            return dict(resp.json())
        raise GraphError("exhausted retries")  # pragma: no cover

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return min(2.0**attempt, _MAX_BACKOFF_SECONDS) + random.random()


def upn_from(url: str) -> str:
    """The UPN out of a ``/users/{upn}`` URL, for readable error messages."""
    return url.rsplit("/", 1)[-1]
