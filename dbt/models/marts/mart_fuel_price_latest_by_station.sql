-- One row per (stationcode, fueltype): the most recently reported price
-- at each station, joined to station reference data for display. This is
-- what the dashboard's "current cheapest fuel by region" map tab reads
-- from -- each row plots as one point (latitude/longitude).
--
-- Inner join to stations, not a left join: a price row whose stationcode
-- doesn't match any known station (e.g. a station added after the
-- reference data's last refresh) is dropped rather than shown with NULL
-- station details, so a broken join shows up as a visible row-count gap
-- instead of a misleading unlabeled point on the map.

with prices as (

    select *
    from {{ ref('stg_fuel_prices') }}
    where last_updated_at is not null

),

latest as (

    select
        *,
        row_number() over (
            partition by stationcode, fueltype
            order by last_updated_at desc
        ) as recency_rank

    from prices

),

stations as (

    select *
    from {{ ref('stg_fuel_stations') }}

)

select
    latest.stationcode,
    latest.fueltype,
    latest.price_cents_per_litre,
    latest.last_updated_at,
    stations.station_name,
    stations.brand,
    stations.address,
    stations.suburb,
    stations.postcode,
    stations.state,
    stations.latitude,
    stations.longitude
from latest
inner join stations on latest.stationcode = stations.stationcode
where latest.recency_rank = 1
