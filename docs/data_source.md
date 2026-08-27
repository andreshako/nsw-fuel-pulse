# Data source: NSW Fuel API

## What it is

The NSW Fuel API (also referred to as FuelCheck) is published by NSW Fair
Trading / Service NSW on the NSW Government's API Developer Portal. It
provides service-station fuel prices reported under the NSW Fuel Price
Reporting Scheme, refreshed as operators submit updates through the day.

- Developer portal / registration: https://api.nsw.gov.au
- Consumer-facing app built on the same data: https://www.fuelcheck.nsw.gov.au

## Registration

1. Create an account at [api.nsw.gov.au](https://api.nsw.gov.au) (free).
2. Register an **Application** in the portal. This generates an OAuth2
   **client id** and **client secret** for that application.
3. Subscribe the application to the **Fuel API** product (reference data +
   price endpoints). Subscription may require manual approval by the API
   owner before calls succeed -- don't assume the key is live immediately
   after subscribing.
4. Put the client id/secret in `.env` as `NSW_FUEL_API_CLIENT_ID` /
   `NSW_FUEL_API_CLIENT_SECRET` (see `.env.example`). Never commit them.

## Access method

**Auth**: OAuth2 client-credentials grant. The application's client
id/secret are exchanged for a short-lived bearer access token against the
portal's token endpoint, then that token is sent as an `Authorization:
Bearer <token>` header on each API call. The exact token endpoint path,
required headers (NSW's API gateway has historically required an
`apikey`/`transactionid`/`requesttimestamp` header set on top of the OAuth
token for some products), and token lifetime are documented per-product in
the portal's Swagger/API docs once you're subscribed -- confirm them there
rather than trusting a hardcoded guess, the same way this project's sibling
repo (tfnsw-transit-pulse) had to confirm its own feed URL after TfNSW
changed it. This will be pinned down precisely when the connector is built.

## Key endpoints

| Endpoint | Version | Purpose | Used for |
|---|---|---|---|
| Get Reference Data | v2 | NSW + TAS lists of stations, fuel types, and brands | Station/fuel-type/brand dimension data |
| Get All Prices | v1 | Full current snapshot of all reported prices | Initial sync |
| Get All New Prices | v1 | Delta of prices changed since the last call | Incremental syncs |

`Get All New Prices` is what makes an efficient incremental Fivetran sync
possible -- pulling the full snapshot on every sync would be wasteful once
the initial load is done. The exact cursor/paging shape of the delta
response, and how it maps to Fivetran's checkpoint state, is worked out
when the connector is built.

## Response shape

Not yet documented here -- captured from the live API once the connector
is being built, rather than guessed at up front.

## Coverage caveats

- Prices are **self-reported by service station operators**, not measured
  independently, and may lag the actual price at the bowser.
- Reporting compliance can vary by station and by region -- absence of a
  price update does not necessarily mean the price didn't change.
- The Fuel Price Reporting Scheme's reference data covers **NSW and TAS**
  only.

## Attribution

Data sourced from the NSW Fuel API, published by NSW Fair Trading / Service
NSW (https://api.nsw.gov.au). Confirm the exact licence terms for
redistribution in the API Developer Portal's terms of use when registering
-- not assumed here.
