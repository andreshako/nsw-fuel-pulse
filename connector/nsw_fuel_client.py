"""HTTP client for the NSW Fuel API.

Handles the OAuth2 client-credentials flow and the three endpoints this
connector uses. Kept separate from connector.py so the Fivetran-specific
schema/update wiring stays thin and this can be exercised on its own.

CONFIRM AGAINST THE LIVE API BEFORE DEPLOYING: the exact token endpoint
path, header names, and response JSON shapes below are this project's
best-known defaults for NSW's API gateway conventions, not verified
against a live subscription (registration is a manual step -- see
../docs/data_source.md). Run `fivetran debug` locally against a real
client id/secret and adjust the parsing in `_items` below to match what
the API actually returns before trusting this in a sync.
"""

from __future__ import annotations

import requests

TOKEN_URL = "https://api.nsw.gov.au/oauth/client_credential/accesstoken?grant_type=client_credentials"
REFERENCE_DATA_URL = "https://api.nsw.gov.au/FuelCheckRefData/v2/fuel/lovs"
ALL_PRICES_URL = "https://api.nsw.gov.au/FuelPriceCheck/v1/fuel/prices"
NEW_PRICES_URL = "https://api.nsw.gov.au/FuelPriceCheck/v1/fuel/prices/new"

REQUEST_TIMEOUT_SECONDS = 30


class NSWFuelClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None

    def _authenticate(self) -> str:
        # NSW's API gateway (Apigee-based) issues short-lived bearer
        # tokens via HTTP Basic auth with the client id/secret -- fetched
        # once per sync run rather than cached across runs, since a sync
        # only takes a few seconds and token lifetime isn't worth tracking.
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
            # NSW's API gateway has required an `apikey` header (the OAuth
            # client id, not a separate value) on some products alongside
            # the bearer token -- confirm this is still needed for the
            # Fuel API once subscribed; harmless to send if not required.
            "apikey": self._client_id,
            "Content-Type": "application/json; charset=utf-8",
        }

    @staticmethod
    def _items(response_json: dict, *candidate_keys: str) -> list[dict]:
        """Pull a list of records out of a response using the first
        candidate top-level key that's present. The real key name(s) are
        unconfirmed -- see the module docstring -- so this tries a few
        plausible options rather than hard-failing on the wrong guess.
        """
        for key in candidate_keys:
            value = response_json.get(key)
            if isinstance(value, list):
                return value
        raise KeyError(
            f"None of {candidate_keys} found as a list in the response. "
            f"Actual top-level keys: {list(response_json.keys())}. "
            "Update NSWFuelClient._items()'s candidate keys to match."
        )

    def get_reference_data(self) -> list[dict]:
        response = requests.get(
            REFERENCE_DATA_URL, headers=self._headers(), timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return self._items(response.json(), "stations", "Stations")

    def get_all_prices(self) -> dict:
        """Full current snapshot -- used for the initial sync only."""
        response = requests.get(
            ALL_PRICES_URL, headers=self._headers(), timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        body = response.json()
        return {"prices": self._items(body, "prices", "Prices"), "raw": body}

    def get_new_prices(self, modified_since: str) -> dict:
        """Delta of prices changed since `modified_since` -- used for
        every sync after the first. `modified_since` is whatever cursor
        value the previous sync's response supplied as its own timestamp
        (see connector.py) -- confirm the actual request parameter name
        the API expects (`modifiedsince` header is this project's guess).
        """
        headers = {**self._headers(), "modifiedsince": modified_since}
        response = requests.get(
            NEW_PRICES_URL, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        body = response.json()
        return {"prices": self._items(body, "prices", "Prices"), "raw": body}
