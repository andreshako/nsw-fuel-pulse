-- One row per (stationcode, fueltype, last_updated_at) price update -- an
-- append-only history of price changes, not a latest-price-only table
-- (see connector/connector.py's fuel_prices primary key). Marts derive
-- "current price" and daily/rolling aggregates from this full history, so
-- staging deliberately does not collapse to latest-per-station here.
--
-- stationcode cast to string: the raw column is an integer, but
-- stg_fuel_stations.stationcode (sourced from the reference data's
-- `code` field) is a string for the same station id -- confirmed 100%
-- overlap against a real snapshot, but the two need a matching type to
-- join on.
--
-- last_updated_at: the raw `lastupdated` string is DD/MM/YYYY HH:MM:SS
-- (confirmed against real data, e.g. "26/08/2026 09:05:17"), not ISO
-- 8601 -- safe.parse_timestamp with an explicit format, not a plain
-- cast, which would silently return NULL on every row against this
-- format.

with source as (

    select *
    from {{ source('raw', 'fuel_prices') }}

),

renamed as (

    select
        safe_cast(stationcode as string) as stationcode,
        fueltype,
        safe_cast(price as numeric) as price_cents_per_litre,
        safe.parse_timestamp('%d/%m/%Y %H:%M:%S', lastupdated) as last_updated_at

    from source
    where stationcode is not null
      and fueltype is not null and fueltype != ''
      and lastupdated is not null and lastupdated != ''

)

select *
from renamed
