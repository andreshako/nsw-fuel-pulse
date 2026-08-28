# NSW Fuel API connector (Fivetran Connector SDK)

- `connector.py` -- schema + update wiring Fivetran calls directly.
- `nsw_fuel_client.py` -- the actual HTTP/auth logic against the NSW Fuel
  API, kept separate so it can be read and adjusted on its own.
- `requirements.txt` -- **this connector's own** deploy manifest (separate
  from the repo root `requirements.txt`) -- see the comments in that file
  for why it's nearly empty.
- `configuration.json.example` -- copy to `configuration.json` (gitignored)
  and fill in your NSW Fuel API `client_id`/`client_secret` for local
  debugging. This is Fivetran's local-debug config, distinct from the repo
  root `.env` -- the deployed connector never reads `.env`.

## Verified against the live API

As of 2026-08-28, this connector has been run end-to-end with `fivetran
debug` against the real NSW Fuel API (13,892 rows upserted: 3,316
stations + 10,576 prices) -- not just guessed at. See
[`../docs/data_source.md`](../docs/data_source.md) for the confirmed
endpoint URLs, headers, and response shapes, and the module docstrings in
`connector.py`/`nsw_fuel_client.py` for what was corrected from the first,
unverified draft (wrong API host entirely, wrong endpoint versions,
missing headers, and a different incremental-sync mechanism than
originally assumed).

One thing still unconfirmed: whether the `location` field (a nested
`{latitude, longitude}` object) lands in real BigQuery as a native
RECORD/STRUCT column (what `stg_fuel_stations.sql`'s `location.latitude`
dot-access assumes) or as a JSON string -- `fivetran debug`'s local
DuckDB warehouse stores it as JSON text, which may just be a debug-tool
convenience rather than representative of real BigQuery schema inference.
Confirm once a real sync has landed in BigQuery (see the root README's
[Current limitations](../README.md#current-limitations)).

`fivetran debug` also runs `pipreqs` internally as part of its own
process, which was observed to delete `requirements.txt` in this
directory as a side effect -- if it's missing after a local debug run,
that's why; the committed version in git is unaffected.

## Local debugging

```bash
cd connector
cp configuration.json.example configuration.json   # fill in client_id/client_secret
fivetran debug --configuration configuration.json
```

`fivetran debug` runs `schema()` and `update()` locally against the real
NSW Fuel API and writes to a local DuckDB warehouse, without touching
Fivetran or BigQuery -- the fastest way to see the connector's actual
behavior and confirm/fix the response-parsing guesses above. `project_path`
defaults to the current directory, so run it from inside `connector/`.

## Deploying

```bash
cd connector
fivetran deploy \
  --api-key "$FIVETRAN_API_KEY" \
  --destination <your-bigquery-destination-name> \
  --connection nsw_fuel_pulse \
  --configuration configuration.json
```

This packages `connector.py`, `nsw_fuel_client.py`, and
`requirements.txt` and pushes them to Fivetran, which then runs the
connector on its own schedule (writing to the `raw` dataset via the
nsw-fuel-fivetran service account -- see the root
[README](../README.md#gcp-service-accounts)). `--destination` and
`--connection` names depend on what you've already set up in your
Fivetran account (`fivetran deploy --help` confirms the current flag set
for the installed SDK version).
