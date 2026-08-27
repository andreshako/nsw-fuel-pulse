-- One row per (report_date, suburb, fueltype): daily avg/min/max price,
-- grouped by station suburb -- the finest regional grain the reference
-- data actually provides (the NSW Fuel API's reference data covers
-- stations/fuel types/brands, not a separate "region" list, so suburb is
-- the grouping this project can actually support rather than guess at).
-- report_date is the Sydney-local calendar date of the price update
-- (last_updated_at is stored as UTC).
--
-- Aggregates each station's LAST reported price for that day, not every
-- price update: a station that changes price three times in one day
-- should count once in that day's regional average, at its end-of-day
-- price, not three times -- averaging every intraday change would give
-- frequently-updating stations more weight than stable ones for no
-- analytical reason.

with prices as (

    select
        stationcode,
        fueltype,
        price_cents_per_litre,
        last_updated_at,
        date(last_updated_at, 'Australia/Sydney') as report_date
    from {{ ref('stg_fuel_prices') }}
    where last_updated_at is not null
      and price_cents_per_litre is not null

),

daily_last_price as (

    select
        *,
        row_number() over (
            partition by stationcode, fueltype, report_date
            order by last_updated_at desc
        ) as recency_rank

    from prices

),

stations as (

    select stationcode, suburb
    from {{ ref('stg_fuel_stations') }}

)

select
    daily_last_price.report_date,
    stations.suburb,
    daily_last_price.fueltype,
    avg(daily_last_price.price_cents_per_litre) as avg_price_cents_per_litre,
    min(daily_last_price.price_cents_per_litre) as min_price_cents_per_litre,
    max(daily_last_price.price_cents_per_litre) as max_price_cents_per_litre,
    count(*) as station_count
from daily_last_price
inner join stations on daily_last_price.stationcode = stations.stationcode
where daily_last_price.recency_rank = 1
group by daily_last_price.report_date, stations.suburb, daily_last_price.fueltype
