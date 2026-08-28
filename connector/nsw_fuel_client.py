"""HTTP client for the NSW Fuel API.

Handles the OAuth2 client-credentials flow and the three endpoints this
connector uses. Kept separate from connector.py so the Fivetran-specific
schema/update wiring stays thin and this can be exercised on its own.

Verified against the live API on 2026-08-28 using NSW's own published
public trial credentials (from https://api.nsw.gov.au/Product/Index/22),
not just guessed at. Corrected several wrong assumptions from the first
draft of this file:

- The real API host is api.onegov.nsw.gov.au -- api.nsw.gov.au (used in
  the first draft) is only the developer portal for registration; it 404s
  on every actual API call.
- Get All Prices / Get All New Prices are v2, not v1.
- Three extra headers are required beyond Authorization: `apikey` (the
  client id), `transactionid` (a unique value per request), and
  `requesttimestamp` (DD/MM/YYYY HH:MM:SS AM/PM).
- Reference data wraps each list in `{"items": [...]}`; the prices
  endpoints return flat lists directly (`{"stations": [...], "prices":
  [...]}`) -- not the same shape, despite both endpoints returning
  "stations".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import requests

API_HOST = "https://api.onegov.nsw.gov.au"
TOKEN_URL = f"{API_HOST}/oauth/client_credential/accesstoken?grant_type=client_credentials"
REFERENCE_DATA_URL = f"{API_HOST}/FuelCheckRefData/v2/fuel/lovs"
ALL_PRICES_URL = f"{API_HOST}/FuelPriceCheck/v2/fuel/prices"
NEW_PRICES_URL = f"{API_HOST}/FuelPriceCheck/v2/fuel/prices/new"

REQUEST_TIMEOUT_SECONDS = 30


class NSWFuelClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None

    def _authenticate(self) -> str:
        # NSW's API gateway (Apigee-based) issues bearer tokens valid for
        # ~12 hours via HTTP Basic auth with the client id/secret --
        # fetched once per sync run rather than cached across runs, since
        # a sync only takes a few seconds and token lifetime isn't worth
        # tracking.
        response = requests.get(
            TOKEN_URL,
            auth=(self._client_id, self._client_secret),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _headers(self) -> dict:
        if self._access_token is None:
            self._access_token = self._authenticate()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "apikey": self._client_id,
            # A fresh value is required per request -- confirmed against
            # the live API, not just a guess this time.
            "transactionid": str(uuid.uuid4()),
            "requesttimestamp": datetime.now(timezone.utc).strftime("%d/%m/%Y %I:%M:%S %p"),
            "Content-Type": "application/json; charset=utf-8",
        }

    def get_reference_data(self) -> list[dict]:
        """Station/brand/fuel-type reference lists. Reference data wraps
        each list under an `items` key -- confirmed different from the
        prices endpoints below.
        """
        response = requests.get(
            REFERENCE_DATA_URL, headers=self._headers(), timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()["stations"]["items"]

    def get_all_prices(self) -> list[dict]:
        """Full current snapshot -- used for the first sync of each day
        (see connector.py's per-day full-sync logic, driven by this
        endpoint's documented "since the last full request... for that
        day" relationship to Get All New Prices).

        The response also embeds a `stations` list, but it isn't used
        here -- get_reference_data() is the single source of truth for
        station rows, and this endpoint's embedded stations aren't
        confirmed to be a complete/consistent refresh on every call.
        """
        response = requests.get(
            ALL_PRICES_URL, headers=self._headers(), timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()["prices"]

    def get_new_prices(self) -> list[dict]:
        """Delta of prices changed since this API key's last Get All
        Prices call *that day* -- per NSW's own documentation, this
        relationship resets daily, not just on the very first-ever call.
        No request parameter or cursor is needed or accepted -- confirmed
        against the live API, correcting the first draft's assumption of
        a client-supplied `modifiedsince` header.
        """
        response = requests.get(
            NEW_PRICES_URL, headers=self._headers(), timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()["prices"]
