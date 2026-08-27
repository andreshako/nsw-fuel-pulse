-- Singular test: fails (returns a row) if the mart is empty. See
-- assert_mart_fuel_price_latest_by_station_has_rows.sql for why this
-- exists.

select 1 as failing_check
from (select count(*) as row_count from {{ ref('mart_fuel_price_daily_by_region') }})
where row_count = 0
