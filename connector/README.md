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

## Before running this for real

The exact response shapes this connector parses (`nsw_fuel_client.py`'s
`_items()` candidate keys, `connector.py`'s cursor field candidates) are
this project's best-known guesses at NSW's API gateway conventions, not
verified against a live subscription -- see the module docstrings and
[`../docs/data_source.md`](../docs/data_source.md). Register, subscribe to
the Fuel API product, and run `fivetran debug` locally before trusting
this in a real sync; adjust the candidate keys to match whatever comes
back.

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
