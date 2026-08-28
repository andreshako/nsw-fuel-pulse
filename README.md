# NSW Fuel Pulse

NSW Fuel Pulse ingests live service-station fuel prices from the NSW Fuel
API into BigQuery via a custom Fivetran Connector SDK connector, models
them with dbt, and publishes a Tableau Public dashboard that stays fresh
automatically -- no manual refresh -- via a scheduled Google Sheets export.

This is a portfolio project, built as a companion to
[tfnsw-transit-pulse](https://github.com/andreshako/tfnsw-transit-pulse),
[planning-pulse-nsw](https://github.com/andreshako/planning-pulse-nsw), and
[australian-energy-pulse](https://github.com/andreshako/australian-energy-pulse).

## Purpose

- Ingest fuel-price and station reference data from the NSW Fuel API into
  BigQuery using a custom Fivetran connector (Connector SDK), with a real
  incremental sync strategy rather than a full reload every time.
- Model the raw data into clean, tested staging and mart layers using dbt,
  including a mart purpose-built to surface the well-known NSW petrol
  price cycle.
- Keep a public Tableau dashboard current without any manual refresh step,
  by writing a small, reviewed snapshot of the marts to a Google Sheet on
  a schedule -- the one data-source type Tableau Public auto-refreshes.

## Project status

Everything is built, and the connector has been run end-to-end against
the live NSW Fuel API with `fivetran debug` (13,892 rows synced) -- see
[connector/README.md](connector/README.md#verified-against-the-live-api)
for what that verification caught and corrected from the first,
unverified draft. Real GCP infrastructure (a dedicated project, all four
service accounts, the `raw`/`staging`/`marts` datasets) is provisioned
and `dbt build` has been confirmed working against it live. What's left:
deploying the connector to Fivetran for its first real scheduled sync,
and building the Tableau Public workbook by hand once real data is
flowing -- see [Roadmap](#roadmap-future-iterations) below.

## Architecture

```mermaid
flowchart LR
    A[NSW Fuel API<br/>api.onegov.nsw.gov.au] -->|OAuth2 client credentials| B[Fivetran connector<br/>Connector SDK]
    B -->|first sync of the day: Get All Prices| C[(BigQuery raw)]
    B -->|later syncs same day: Get All New Prices<br/>server-side daily delta, no cursor needed| C
    C -->|dbt source| D[stg_fuel_prices<br/>stg_fuel_stations]
    D --> E[mart_fuel_price_latest_by_station]
    D --> F[mart_fuel_price_daily_by_region]
    D --> G[mart_fuel_price_cycle<br/>rolling 7/14-day min-max, DoD % change]

    H[GitHub Actions<br/>scheduled every 6h] -.dbt build + test.-> D
    H -.runs.-> I[scripts/export_dashboard_snapshot.py]
    E --> I
    F --> I
    G --> I
    I -->|Sheets API| J[(Google Sheet)]
    J -->|auto-refresh every 24h| K[Tableau Public dashboard]
```

Two BigQuery-writing identities, not one: Fivetran's service account only
ever writes `raw`; dbt's only ever reads `raw` and writes `staging`/
`marts`. A leaked credential in either place can't reach what the other
touches. See [GCP service accounts](#gcp-service-accounts) below.

## Data source

NSW Fuel API -- OAuth2 client-credentials auth, free registration at
`api.nsw.gov.au` (the developer portal; the real API host,
`api.onegov.nsw.gov.au`, is different -- see
[`docs/data_source.md`](docs/data_source.md) for why that distinction
matters). See that doc for the full registration steps, confirmed
endpoint URLs/headers/response shapes, and coverage caveats.

### Attribution

Data sourced from the NSW Fuel API, published by NSW Fair Trading /
Service NSW (https://api.nsw.gov.au). See
[`docs/data_source.md`](docs/data_source.md#attribution) for licence
terms to confirm on registration.

## GCP service accounts

Three separate service accounts, least-privilege and single-purpose --
same separation-of-duties pattern as tfnsw-transit-pulse:

| Service account | Roles | Used by |
|---|---|---|
| nsw-fuel-fivetran | BigQuery Data Editor + Job User, scoped to `raw` | The deployed Fivetran connector |
| nsw-fuel-dbt-runner | BigQuery Data Viewer on `raw`, Data Editor on `staging`/`marts` | Local `dbt build`, via the `dev` profile target |
| nsw-fuel-ci | Same roles as nsw-fuel-dbt-runner, separate identity/key | `.github/workflows/scheduled_pipeline.yml`, via the `ci` profile target |

A fourth, narrowly-scoped Google Sheets service account (editor on one
target Sheet only, nothing else in Drive) is used by
`scripts/export_dashboard_snapshot.py`.

## Data model

- **"Region" means suburb.** The NSW Fuel API's reference data covers
  stations/fuel types/brands, not a separate region list, so
  `mart_fuel_price_daily_by_region` and `mart_fuel_price_cycle` group by
  station suburb -- the finest geography actually available, rather than
  an invented, unverified region concept. Suburb itself is parsed out of
  the API's single combined address string (there's no dedicated
  suburb/postcode field) and is NULL for the ~3% of real addresses that
  don't match the expected format -- confirmed against a real snapshot,
  not assumed; see `dbt/models/staging/stg_fuel_stations.sql`.
- **`mart_fuel_price_latest_by_station`** -- grain `(stationcode,
  fueltype)`. The station's most recently reported price, inner-joined to
  station details (not left-joined: an unmatched stationcode is dropped
  rather than shown with NULL station details, so a broken join is a
  visible row-count gap, not a misleading unlabeled map point).
- **`mart_fuel_price_daily_by_region`** -- grain `(report_date, suburb,
  fueltype)`. Aggregates each station's *last* reported price for the
  day, not every intraday price change -- a station updating its price
  three times in a day counts once, at its end-of-day price, so
  frequently-updating stations don't get more weight in the regional
  average than stable ones. `report_date` is the Sydney-local calendar
  date (source timestamps are UTC).
- **`mart_fuel_price_cycle`** -- grain `(report_date, suburb, fueltype)`,
  built on the mart above. Day-over-day change via `LAG()`, plus rolling
  7/14-day min/max via a window frame (same pattern as
  `mart_daily_generation_trend` in australian-energy-pulse). The rolling
  windows are the last 7/14 *rows* for a partition, not strictly the last
  7/14 *calendar days* -- a suburb/fuel-type combination with a gap day
  (no price updates at all) makes the window silently span more real days
  than its name suggests. Not corrected here; see [Current
  limitations](#current-limitations).
- **Tests:** `not_null` and `accepted_values` on fuel type codes (and on
  station state), composite grain uniqueness on every mart
  (`dbt_utils.unique_combination_of_columns`), `dbt_utils.accepted_range`
  sanity bounds on price (50-400 cents/litre -- generous, catches
  impossible values like a unit error, not "unusually high" days), and a
  singular test per mart asserting it isn't empty (`dbt/tests/`) -- added
  proactively here after tfnsw-transit-pulse hit exactly that gap for
  real (an always-empty mart that passed every schema test).

## dbt setup

`dbt/` is a dbt-bigquery project (profile name `nsw_fuel_pulse`):

```
dbt/
  dbt_project.yml
  packages.yml              # dbt-labs/dbt_utils
  profiles.yml.example       # copy to profiles.yml (gitignored)
  models/
    staging/                 # stg_fuel_prices, stg_fuel_stations
    marts/                   # mart_fuel_price_latest_by_station,
                              # mart_fuel_price_daily_by_region,
                              # mart_fuel_price_cycle
  tests/                     # empty-mart guards, one per mart
```

```bash
cp dbt/profiles.yml.example dbt/profiles.yml
cd dbt
dbt deps
dbt build
```

Verified with the real `dbt-bigquery` adapter: `dbt parse`, `dbt list`,
and dependency resolution (`mart_fuel_price_cycle` ->
`mart_fuel_price_daily_by_region` -> staging -> sources) all succeed as
expected. `dbt build`/`dbt test` need real BigQuery credentials -- see
[CI](#ci) below.

## CI

Two workflows, deliberately separated by what they touch:

- **`.github/workflows/ci.yml`** -- runs on every push/PR that touches the
  dbt project. Validates the project parses (`dbt parse`) using
  CI-safe placeholder defaults baked into `profiles.yml.example`. Never
  touches real BigQuery data and needs no secrets.
- **`.github/workflows/scheduled_pipeline.yml`** -- runs every 6 hours (and
  on manual dispatch). Authenticates as the `nsw-fuel-ci` service account,
  runs `dbt build` and `dbt test` against real BigQuery data, then runs
  `scripts/export_dashboard_snapshot.py` to refresh the Google Sheet the
  Tableau dashboard reads from.

## Dashboard

A Tableau Public workbook connected to the Google Sheet that
`scripts/export_dashboard_snapshot.py` writes. Tableau Public
auto-refreshes Google Sheets connections every 24 hours -- the only data
source type it auto-refreshes without a paid Tableau Server/Cloud
subscription -- which is why the pipeline targets a Sheet rather than a
committed CSV snapshot (contrast with planning-pulse-nsw's `dashboard_data/`
folder, which works because that dashboard is Streamlit, not Tableau
Public). This is a deliberate design decision, not a workaround.

Two tabs, shaped for the workbook I'll build by hand in Tableau Public's
editor. Both tabs must already exist in the target Sheet -- the export
script only clears and rewrites existing tabs, it doesn't create new
ones:

| Sheet tab | Source mart | For |
|---|---|---|
| `current_by_station` | `mart_fuel_price_latest_by_station` | Map (lat/long per row) |
| `price_cycle` | `mart_fuel_price_cycle` | Line chart |

```bash
python scripts/export_dashboard_snapshot.py
```

Clears and fully overwrites both tabs on every run (never appends), so a
run with fewer rows than the last one never leaves stale rows behind.

## Data caveats

- Prices are self-reported by service station operators and may lag the
  actual price at the bowser.
- Sync frequency is governed by Fivetran's free-tier scheduling (hourly/
  daily), not real-time -- this is a polled, low-frequency pipeline, not a
  live feed.
- Coverage may vary by station and region depending on operator reporting
  compliance; absence of a price update does not necessarily mean the
  price didn't change.

## Current limitations

- No Tableau workbook yet, and the connector isn't deployed to Fivetran
  for scheduled production syncs yet -- see [Project status](#project-status).
- The export script is verified for imports/syntax against the real
  Google client libraries and a real Google Sheet (confirmed shared
  correctly with the export service account), but hasn't run against
  real mart data yet -- that needs the connector's first real sync.
- Whether the station reference data's nested `location` field
  (latitude/longitude) lands in real BigQuery as a native RECORD/STRUCT
  column, or as a JSON string, is unconfirmed -- `fivetran debug`'s local
  DuckDB warehouse stores it as JSON text, which may not represent real
  BigQuery schema inference. `stg_fuel_stations.sql`'s `location.latitude`
  dot-access assumes the former; confirm once a real sync lands.
- Suburb/postcode are parsed from a single combined address string with
  no dedicated fields (~97% match rate on a real snapshot) -- see [Data
  model](#data-model).
- No historical backfill: the pipeline's history starts the day the
  Fivetran connector's first real sync runs -- the NSW Fuel API doesn't
  expose historical price data.
- `mart_fuel_price_cycle`'s rolling 7/14-day windows will read as noise
  until at least that many days of real data have accumulated, and are
  measured in rows, not strictly calendar days -- see [Data
  model](#data-model).
- The NSW Fuel API's free tier caps at 2,500 calls/month and 5 calls/
  minute -- worth keeping in mind alongside Fivetran's own sync-frequency
  limits when choosing how often this runs.
- "Region" means suburb, not an official NSW region breakdown -- see
  [Data model](#data-model) for why.

## Roadmap (future iterations)

1. ~~**Repo scaffold** -- folders, dbt project config, `.env.example`, CI
   workflow shapes.~~ Done.
2. ~~**Fivetran connector** -- `connector/connector.py`: OAuth2 auth, initial
   sync via Get All Prices, incremental sync via Get All New Prices with
   Fivetran checkpoint/state.~~ Built; still needs validation against a
   live subscription (`fivetran debug`) and deployment via the Connector
   SDK's standard workflow -- see [connector/README.md](connector/README.md).
3. ~~**dbt staging models** -- `stg_fuel_prices`, `stg_fuel_stations`, and
   the `_staging__sources.yml` source contract for the raw tables the
   connector produces.~~ Built and `dbt parse`-verified; field names still
   need confirming against a live subscription (same caveat as the
   connector).
4. ~~**dbt marts and tests** -- `mart_fuel_price_latest_by_station`,
   `mart_fuel_price_daily_by_region`, `mart_fuel_price_cycle`, plus the
   grain/range/accepted-value tests described above.~~ Built and
   `dbt parse`/`dbt list`-verified; same field-name caveat as stages 2-3.
5. ~~**Export script** -- `scripts/export_dashboard_snapshot.py`, writing
   the two dashboard-ready tabs to Google Sheets.~~ Built and import/
   syntax-verified against the real Google client libraries; not yet run
   for real (needs a live Sheet, service-account key, and real mart data).
6. **Tableau Public dashboard** -- built by hand against the Sheet, once
   its data is stable.
7. **Optional: Snowflake target** -- a second dbt target using the
   `dbt-snowflake` adapter, run manually during a Snowflake trial and
   documented with screenshots, to demonstrate warehouse portability. Not
   part of the always-on pipeline.
8. **Optional: price-cycle vs. public holidays** -- cross-referencing
   `mart_fuel_price_cycle` troughs against NSW public holidays/events.

## Repository layout

```
connector/          Fivetran Connector SDK connector -- connector.py
                     (schema/update wiring), nsw_fuel_client.py (API
                     auth/HTTP), requirements.txt (own deploy manifest,
                     separate from the repo root requirements.txt)
dbt/
  models/staging/    stg_fuel_prices, stg_fuel_stations
  models/marts/      mart_fuel_price_latest_by_station,
                      mart_fuel_price_daily_by_region,
                      mart_fuel_price_cycle
  tests/             empty-mart guard, one singular test per mart
scripts/             export_dashboard_snapshot.py -- clears and rewrites
                     two Google Sheet tabs from the marts
docs/                data_source.md -- NSW Fuel API registration + endpoints
.github/workflows/   ci.yml (structural validation, no secrets) and
                     scheduled_pipeline.yml (real build/test/export, every 6h)
```

## License

TBD.
