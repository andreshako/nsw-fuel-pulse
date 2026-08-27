-- One row per station. Passes through the Fivetran-ingested reference
-- data with light typing/renaming -- no business logic here (that
-- belongs in marts). Fivetran refreshes this source table in full on
-- every sync (see connector/connector.py), so there's no dedup/history
-- concern the way there is for stg_fuel_prices.

with source as (

    select *
    from {{ source('raw', 'fuel_stations') }}

),

renamed as (

    select
        stationcode,
        brand,
        name as station_name,
        address,
        suburb,
        postcode,
        state,
        safe_cast(latitude as float64) as latitude,
        safe_cast(longitude as float64) as longitude

    from source
    where stationcode is not null
      and stationcode != ''

)

select *
from renamed
