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
4. Put the client id/secret in `connector/configuration.json` (see
   `connector/configuration.json.example`) for local `fivetran debug`
   testing -- never commit them.

Free trial: **2,500 calls/month**, with a hard cap of **5 calls/minute**
for unauthenticated/trial-tier usage -- worth keeping in mind when
choosing a sync schedule (see the root README's automation section).

## Access method

Everything below is confirmed against the *live* API (verified
2026-08-28), not guessed -- including using NSW's own published public
trial credentials from the [Fuel API product
page](https://api.nsw.gov.au/Product/Index/22) before this project's own
registration was even approved.

**The real API host is `api.onegov.nsw.gov.au`** -- `api.nsw.gov.au` is
only the developer portal for registration and documentation; it 404s on
every actual API call. This tripped up the first draft of the connector.

**Auth**: OAuth2 client-credentials grant, HTTP Basic auth with the
client id/secret as username/password:

```
GET https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken?grant_type=client_credentials
Authorization: Basic <base64(client_id:client_secret)>
```

Returns a bearer token (`access_token` field) valid for ~12 hours
(`expires_in` in the response, seconds).

**Every other call** needs four headers beyond the bearer token:

```
Authorization: Bearer <access_token>
apikey: <client_id>
transactionid: <a fresh unique value per request, e.g. a UUID>
requesttimestamp: <DD/MM/YYYY HH:MM:SS AM/PM>
Content-Type: application/json; charset=utf-8
```

## Key endpoints

| Endpoint | Version | Purpose | Used for |
|---|---|---|---|
| Get Reference Data | v2 (`/FuelCheckRefData/v2/fuel/lovs`) | NSW + TAS lists of stations, fuel types, and brands | Station dimension data |
| Get All Prices | v2 (`/FuelPriceCheck/v2/fuel/prices`) | Full current snapshot of all reported prices | First sync of each day |
| Get All New Prices | v2 (`/FuelPriceCheck/v2/fuel/prices/new`) | Prices changed since this API key's last Get All Prices call **that day** | Every sync after the first that day |

Get All New Prices needs **no request parameter or cursor** -- it's
tracked server-side, per API key, reset daily. This connector calls Get
All Prices once per UTC calendar day and Get All New Prices for every
sync after that on the same day (see
`connector/connector.py`'s module docstring) -- corrected from the first
draft's assumption of a client-supplied `modifiedsince` cursor, which
isn't how the real API works.

## Response shape

**Get Reference Data** (`/FuelCheckRefData/v2/fuel/lovs`) -- each list
wrapped under an `items` key:

```json
{
  "brands": {"items": [{"name": "BP", "state": "NSW"}, ...]},
  "fueltypes": {"items": [{"code": "U91", "name": "Unleaded 91", "state": "NSW"}, ...]},
  "stations": {"items": [
    {
      "brandid": "", "stationid": "", "brand": "United", "code": "972",
      "name": "United Petroleum Umina",
      "address": "307-313 Ocean Beach Road, UMINA BEACH NSW 2257",
      "location": {"latitude": -33.511231, "longitude": 151.318092},
      "state": "NSW"
    }
  ]},
  "trendperiods": {"items": [...]},
  "sortfields": {"items": [...]}
}
```

Note: no separate suburb/postcode fields -- only the single combined
`address` string. `stg_fuel_stations.sql` parses suburb/postcode out of it
via regex, matching ~97% of a real snapshot (see that model's own header
comment for the confirmed failure modes).

**Get All Prices** / **Get All New Prices** -- flat lists, **not** wrapped
in `items` (a different shape from Reference Data, despite both
responses being called "stations"):

```json
{
  "stations": [ /* same station shape as above, not used by this connector -- see nsw_fuel_client.py */ ],
  "prices": [
    {"stationcode": 1, "state": "NSW", "fueltype": "DL", "price": 258.9, "lastupdated": "26/08/2026 09:05:17"}
  ]
}
```

Two things to know about this shape:
- `stationcode` here is an **integer**; `stations[].code` in Reference
  Data is a **string** for the same station (confirmed 100% overlap
  against a real 3,275-station snapshot) -- `stg_fuel_prices.sql` casts
  to match.
- `lastupdated` is `DD/MM/YYYY HH:MM:SS`, not ISO 8601 -- parsed with an
  explicit format string, not a plain cast.

Confirmed real `fueltype` values on actual price rows (a subset of Get
Reference Data's full fuel-type list, which also includes combo/display
codes like `P95-P98` that don't appear on individual price rows): `U91`,
`P95`, `P98`, `E10`, `E85`, `DL`, `PDL`, `B20`, `LPG`, `EV`.

## Coverage caveats

- Prices are **self-reported by service station operators**, not measured
  independently, and may lag the actual price at the bowser.
- Reporting compliance can vary by station and by region -- absence of a
  price update does not necessarily mean the price didn't change.
- The Fuel Price Reporting Scheme's reference data is documented as NSW +
  TAS only, but a real snapshot shows a handful of `ACT` stations too
  (border-region stations, e.g. near Queanbeyan/Canberra) -- confirmed in
  live data, not assumed from the docs alone.

## Attribution

Data sourced from the NSW Fuel API, published by NSW Fair Trading / Service
NSW (https://api.nsw.gov.au). Confirm the exact licence terms for
redistribution in the API Developer Portal's terms of use when registering
-- not assumed here.
