"""Fivetran Connector SDK connector for the NSW Fuel API.

Two tables:

- `fuel_stations` -- station/brand reference data (Get Reference Data
  v2). Refreshed in full on every sync; it's small, and there's no cheap
  way to fetch only the stations that changed.
- `fuel_prices` -- price observations. Each price update lands as its own
  row (see the primary key in `schema()` below) so the raw table is an
  append-only log of price changes, not a latest-value-only table -- the
  dbt marts need that history to compute daily aggregates and rolling
  price-cycle windows.

Sync strategy, corrected after testing against the live API (see
nsw_fuel_client.py's module docstring): NSW's Get All New Prices endpoint
returns prices changed "since the last [Get All Prices] request... using
the current API key for that day" -- a *daily*-scoped relationship, not
a one-time "call full once, then delta forever" relationship. So this
connector calls Get All Prices once per UTC calendar day (the first sync
of that day) and Get All New Prices for every sync after that on the same
day, tracked via `state["last_full_sync_date"]`. The first draft of this
file assumed a client-supplied cursor timestamp instead, which doesn't
match how the real API works.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from nsw_fuel_client import NSWFuelClient

REQUIRED_CONFIG_KEYS = ("client_id", "client_secret")


def schema(configuration: dict):
    return [
        {
            "table": "fuel_stations",
            "primary_key": ["code"],
        },
        {
            # (stationcode, fueltype, lastupdated) as the key means a
            # price update that lands at the same station/fuel-type/
            # timestamp as an existing row overwrites it rather than
            # duplicating -- a real but so-far-unobserved edge case if
            # two updates to the same pump land within the same second.
            "table": "fuel_prices",
            "primary_key": ["stationcode", "fueltype", "lastupdated"],
        },
    ]


def _require_configuration(configuration: dict) -> tuple[str, str]:
    missing = [key for key in REQUIRED_CONFIG_KEYS if not configuration.get(key)]
    if missing:
        raise RuntimeError(f"Missing required configuration keys: {missing}")
    return configuration["client_id"], configuration["client_secret"]


def update(configuration: dict, state: dict):
    client_id, client_secret = _require_configuration(configuration)
    client = NSWFuelClient(client_id, client_secret)

    for station in client.get_reference_data():
        yield op.upsert("fuel_stations", station)

    # UTC calendar date, not Sydney-local: the API doesn't document which
    # timezone its own "day" boundary uses, and UTC is the safer default
    # -- worst case (a timezone mismatch near local midnight) is one
    # extra full-price pull instead of an incremental one, not data loss.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_full_sync_date = state.get("last_full_sync_date")

    if last_full_sync_date != today:
        log.info(f"No full sync yet today ({today}) -- running Get All Prices.")
        prices = client.get_all_prices()
    else:
        log.info(f"Already ran today's full sync -- running Get All New Prices.")
        prices = client.get_new_prices()

    for price in prices:
        yield op.upsert("fuel_prices", price)

    yield op.checkpoint({"last_full_sync_date": today})


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
