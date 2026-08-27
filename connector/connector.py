"""Fivetran Connector SDK connector for the NSW Fuel API.

Two tables:

- `fuel_stations` -- station/brand/fuel-type reference data (Get Reference
  Data v2). Refreshed in full on every sync; it's small, and there's no
  cheap way to fetch only the stations that changed.
- `fuel_prices` -- price observations. Initial sync pulls the full current
  snapshot (Get All Prices v1); every sync after that pulls only the delta
  (Get All New Prices v1), using a Fivetran-checkpointed cursor. Each price
  update lands as its own row (see the primary key in `schema()` below) so
  the raw table is an append-only log of price changes, not a
  latest-value-only table -- the dbt marts need that history to compute
  daily aggregates and rolling price-cycle windows.

CONFIRM BEFORE DEPLOYING: see nsw_fuel_client.py's module docstring. The
field names read off each record below (`stationcode`, `fueltype`,
`lastupdated`, ...) are this project's best-known guess at the NSW Fuel
API's real response shape, not verified against a live subscription. Run
`fivetran debug` locally first and adjust to match what actually comes
back.
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
            "primary_key": ["stationcode"],
        },
        {
            # (stationcode, fueltype, lastupdated) as the key means a
            # price update that lands at the same station/fuel-type/
            # timestamp as an existing row overwrites it rather than
            # duplicating -- a real but so-far-unobserved edge case if the
            # API's `lastupdated` granularity is coarser than the true
            # update frequency (e.g. minute-level timestamps with more
            # than one update to the same pump in a minute).
            "table": "fuel_prices",
            "primary_key": ["stationcode", "fueltype", "lastupdated"],
        },
    ]


def _require_configuration(configuration: dict) -> tuple[str, str]:
    missing = [key for key in REQUIRED_CONFIG_KEYS if not configuration.get(key)]
    if missing:
        raise RuntimeError(f"Missing required configuration keys: {missing}")
    return configuration["client_id"], configuration["client_secret"]


def _response_cursor(raw_response: dict) -> str:
    """The API's own response timestamp becomes next sync's cursor, not
    "now" on our clock -- avoids a gap if this sync started running before
    the API's underlying data was actually current. Falls back to the
    current UTC time, logged clearly, if none of the candidate timestamp
    keys are present -- better than crashing the sync, but means a
    fallback-cursor sync could in principle miss updates that landed in
    the gap between the true data timestamp and "now".
    """
    for key in ("timestamp", "Timestamp", "asAt", "responsetimestamp"):
        value = raw_response.get(key)
        if value:
            return value
    fallback = datetime.now(timezone.utc).isoformat()
    log.warning(
        "No recognized timestamp field in the API response "
        f"(checked timestamp/Timestamp/asAt/responsetimestamp) -- "
        f"falling back to current UTC time ({fallback}) as the next "
        "sync's cursor."
    )
    return fallback


def update(configuration: dict, state: dict):
    client_id, client_secret = _require_configuration(configuration)
    client = NSWFuelClient(client_id, client_secret)

    for station in client.get_reference_data():
        yield op.upsert("fuel_stations", station)

    last_synced = state.get("last_synced")
    if last_synced is None:
        log.info("No prior state -- running initial sync (Get All Prices).")
        result = client.get_all_prices()
    else:
        log.info(f"Prior state found -- running incremental sync since {last_synced}.")
        result = client.get_new_prices(last_synced)

    for price in result["prices"]:
        yield op.upsert("fuel_prices", price)

    yield op.checkpoint({"last_synced": _response_cursor(result["raw"])})


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
