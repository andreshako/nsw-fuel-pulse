-- One row per (stationcode, fueltype, last_updated_at) price update -- an
-- append-only history of price changes, not a latest-price-only table
-- (see connector/connector.py's fuel_prices primary key). Marts derive
-- "current price" and daily/rolling aggregates from this full history, so
-- staging deliberately does not collapse to latest-per-station here.
--
-- safe_cast, not cast, on last_updated_at: the API's real timestamp
-- string format is unconfirmed (see _staging__sources.yml), so a
-- format mismatch surfaces as a NULL caught by this model's not_null
-- test in _staging__models.yml, not a hard model-build failure -- easier
-- to debug once real data is flowing.

with source as (

    select *
    from {{ source('raw', 'fuel_prices') }}

),

renamed as (

    select
        stationcode,
        fueltype,
        safe_cast(price as numeric) as price_cents_per_litre,
        safe_cast(lastupdated as timestamp) as last_updated_at

    from source
    where stationcode is not null and stationcode != ''
      and fueltype is not null and fueltype != ''
      and lastupdated is not null and lastupdated != ''

)

select *
from renamed
