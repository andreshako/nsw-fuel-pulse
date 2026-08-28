-- One row per station. Passes through the Fivetran-ingested reference
-- data with light typing/renaming -- no business logic here (that
-- belongs in marts). Fivetran refreshes this source table in full on
-- every sync (see connector/connector.py), so there's no dedup/history
-- concern the way there is for stg_fuel_prices.
--
-- suburb/postcode: the API only provides a single combined address
-- string (e.g. "307-313 Ocean Beach Road, UMINA BEACH NSW 2257"), not
-- separate fields. Parsed here via regex, matching ~97% of a real
-- snapshot (3179/3275 stations) -- confirmed by testing against live
-- data, not assumed. The unmatched ~3% are real, varied address quality
-- issues (no comma before the suburb, "NEW SOUTH WALES" spelled out
-- instead of "NSW", a trailing ", AU", suburb-only addresses with no
-- street) -- NULL for those rather than a wrong guess, which is exactly
-- what mart_fuel_price_daily_by_region's "region" grouping (suburb) will
-- silently drop those stations from, a real and worth-documenting
-- limitation covered in the README.

with source as (

    select *
    from {{ source('raw', 'fuel_stations') }}

),

renamed as (

    select
        code as stationcode,
        brand,
        name as station_name,
        address,
        -- NSW, TAS, or (confirmed in real data) ACT for a handful of
        -- border-region stations -- despite the scheme's documented
        -- NSW+TAS-only coverage.
        state,
        regexp_extract(address, r',\s*(.+?)\s+(?:NSW|TAS|ACT)\s+\d{4}\s*$') as suburb,
        regexp_extract(address, r'(\d{4})\s*$') as postcode,
        safe_cast(location.latitude as float64) as latitude,
        safe_cast(location.longitude as float64) as longitude

    from source
    where code is not null
      and code != ''

)

select *
from renamed
