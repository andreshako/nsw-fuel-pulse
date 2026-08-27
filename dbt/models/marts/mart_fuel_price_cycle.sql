-- One row per (report_date, suburb, fueltype). Built directly on
-- mart_fuel_price_daily_by_region -- adds day-over-day comparison (via
-- LAG()) and rolling 7/14-day min/max (via a window frame), both
-- partitioned by (suburb, fueltype) and ordered by report_date. This is
-- what's meant to surface the well-known NSW petrol price cycle (prices
-- creep up over several days, then drop sharply, repeat).
--
-- The rolling windows are "the last 7/14 rows for this suburb/fueltype,"
-- not "the last 7/14 calendar days": if a suburb/fueltype combination has
-- a gap day with no price updates at all, the 7-row window silently spans
-- more than 7 calendar days for that partition. A real, named limitation
-- of this approach, not corrected here -- correcting it would require
-- generating a complete date spine and filling gaps, which is more
-- machinery than this project's data volume currently justifies (see
-- mart_daily_generation_trend in australian-energy-pulse for the same
-- LAG()-based day-over-day pattern this model follows).
--
-- For each partition's first available date there's no previous day and
-- no full rolling window yet, so day_over_day_pct_change is NULL and the
-- rolling min/max are computed over however many days actually exist --
-- expected behaviour, not a data quality issue, and these numbers will
-- read as noise until enough real daily history has accumulated.

with daily as (

    select *
    from {{ ref('mart_fuel_price_daily_by_region') }}

),

with_window as (

    select
        *,
        lag(avg_price_cents_per_litre) over (
            partition by suburb, fueltype order by report_date
        ) as previous_avg_price_cents_per_litre,
        min(avg_price_cents_per_litre) over (
            partition by suburb, fueltype order by report_date
            rows between 6 preceding and current row
        ) as rolling_7day_min_price_cents_per_litre,
        max(avg_price_cents_per_litre) over (
            partition by suburb, fueltype order by report_date
            rows between 6 preceding and current row
        ) as rolling_7day_max_price_cents_per_litre,
        min(avg_price_cents_per_litre) over (
            partition by suburb, fueltype order by report_date
            rows between 13 preceding and current row
        ) as rolling_14day_min_price_cents_per_litre,
        max(avg_price_cents_per_litre) over (
            partition by suburb, fueltype order by report_date
            rows between 13 preceding and current row
        ) as rolling_14day_max_price_cents_per_litre

    from daily

)

select
    report_date,
    suburb,
    fueltype,
    avg_price_cents_per_litre,
    min_price_cents_per_litre,
    max_price_cents_per_litre,
    station_count,
    avg_price_cents_per_litre - previous_avg_price_cents_per_litre
        as day_over_day_change_cents_per_litre,
    (avg_price_cents_per_litre - previous_avg_price_cents_per_litre)
        / nullif(previous_avg_price_cents_per_litre, 0)
        as day_over_day_pct_change,
    rolling_7day_min_price_cents_per_litre,
    rolling_7day_max_price_cents_per_litre,
    rolling_14day_min_price_cents_per_litre,
    rolling_14day_max_price_cents_per_litre
from with_window
