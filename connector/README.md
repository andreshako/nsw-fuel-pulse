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

**Update, confirmed against a real production sync:** the `location`
field lands in real BigQuery as a native `JSON`-typed column, not a
STRUCT/RECORD -- `stg_fuel_stations.sql` uses `lax_float64()` (BigQuery's
lenient JSON-to-scalar extraction) rather than the plain-cast dot-access
this section originally flagged as unverified.

Also confirmed against the real production sync (not just the local
DuckDB debug warehouse): station `code` is typed `INT64` in real
BigQuery, despite the API's JSON returning it as a string -- the same
type as `fuel_prices.stationcode`. `stg_fuel_stations.sql` casts both to
`STRING` for a consistent join key.

**And a real Fivetran platform behavior, not obvious from the docs:** the
destination dataset this connector actually writes to is named after the
*connection name* (`nsw_fuel_pulse`), not the BigQuery destination's own
"Dataset name" setting -- that field doesn't control this for Connector
SDK connections the way the Fivetran UI implies. Set `BQ_RAW_DATASET` in
`.env` to match whatever you actually name your connection.

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
