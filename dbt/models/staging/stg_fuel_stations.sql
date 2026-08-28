-- One row per station. Passes through the Fivetran-ingested reference
-- data with light typing/renaming -- no business logic here (that
-- belongs in marts). Fivetran refreshes this source table in full on
-- every sync (see connector/connector.py), so there's no dedup/history
-- concern the way there is for stg_fuel_prices.
--
-- code cast to string: confirmed against a real production sync (not
-- just the local `fivetran debug` DuckDB warehouse, which -- misleadingly
-- -- displayed it looking like a string) that Fivetran's real BigQuery
-- schema inference typed this column as INT64, since every station code
-- happens to be all-digits. Cast to string to match
-- stg_fuel_prices.stationcode (also cast to string there) for the join.
--
-- location.latitude/longitude use lax_float64(), not safe_cast(): also
-- confirmed against a real production sync, `location` lands in BigQuery
-- as a native JSON-typed column, not a STRUCT/RECORD -- a plain CAST
-- from JSON to FLOAT64 errors outright, unlike a genuine type mismatch
-- that safe_cast/safe_cast would just NULL out. lax_float64() is
-- BigQuery's purpose-built lenient JSON-to-scalar extraction, matching
-- this project's "NULL on failure, not a broken build" philosophy for
-- exactly this situation.
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
        safe_cast(code as string) as stationcode,
        brand,
        name as station_name,
        address,
        -- NSW, TAS, or (confirmed in real data) ACT for a handful of
        -- border-region stations -- despite the scheme's documented
        -- NSW+TAS-only coverage.
        state,
        regexp_extract(address, r',\s*(.+?)\s+(?:NSW|TAS|ACT)\s+\d{4}\s*$') as suburb,
        regexp_extract(address, r'(\d{4})\s*$') as postcode,
        lax_float64(location.latitude) as latitude,
        lax_float64(location.longitude) as longitude

    from source
    where code is not null

)

select *
from renamed
