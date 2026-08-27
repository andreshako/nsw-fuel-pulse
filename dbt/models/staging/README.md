# Staging models

Empty for now. This directory will hold:

- `_staging__sources.yml` -- the source contract for the raw tables the
  Fivetran connector writes into `raw` (station/fuel-type/brand reference
  data and price observations), once the connector's schema is defined.
- `stg_fuel_prices.sql` -- typed, cleaned, one row per station/fuel
  type/price update.
- `stg_fuel_stations.sql` -- typed station reference data.

Staging models come after the Fivetran connector is built, since the
source contract depends on the raw table shape the connector produces.
