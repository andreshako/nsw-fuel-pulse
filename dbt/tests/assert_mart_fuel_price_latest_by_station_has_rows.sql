-- Singular test: fails (returns a row) if the mart is empty.
--
-- Every schema test on this mart (not_null, accepted_values,
-- accepted_range, unique_combination_of_columns) passes vacuously on
-- zero rows, so a broken upstream join could silently build an empty
-- table and still show a fully green `dbt build`. Added proactively here
-- rather than after the fact -- tfnsw-transit-pulse hit exactly this gap
-- for real (its LEARNING_NOTES, section 12: an inner join to the wrong
-- reference data quietly produced an always-empty mart that passed every
-- existing test) and only added this kind of test afterward.

select 1 as failing_check
from (select count(*) as row_count from {{ ref('mart_fuel_price_latest_by_station') }})
where row_count = 0
