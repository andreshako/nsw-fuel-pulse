"""Export the fuel-price marts into the Google Sheet the Tableau Public
dashboard reads from.

Two tabs, cleared and fully overwritten on every run (never appended --
Tableau reads whatever's currently in the sheet, so a stale row left over
from a previous run, e.g. because this run has fewer rows than the last
one, must never be left sitting below the new data):

- "current_by_station" <- mart_fuel_price_latest_by_station, for the
  "current cheapest fuel by region" map tab (lat/long per row).
- "price_cycle" <- mart_fuel_price_cycle, for the price-cycle line-chart
  tab.

Both tabs must already exist in the target Sheet -- this script only
clears and writes existing tabs via the Sheets API's values.update, it
doesn't create new ones (spreadsheets().batchUpdate with an addSheet
request would be needed for that, and this project's dashboard tabs are a
small, fixed, hand-designed set rather than something meant to grow on
its own).

Run after `dbt build` -- see .github/workflows/scheduled_pipeline.yml for
the production schedule, or run locally after your own `dbt build`.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
from googleapiclient.discovery import build

MARTS_DATASET = "marts"

SHEET_TABS = {
    "current_by_station": "mart_fuel_price_latest_by_station",
    "price_cycle": "mart_fuel_price_cycle",
}

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _require_env() -> tuple[str, str, str]:
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    sheets_keyfile = os.environ.get("GOOGLE_SHEETS_KEYFILE", "")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")

    missing = [
        name
        for name, value in [
            ("GCP_PROJECT_ID", project_id),
            ("GOOGLE_SHEETS_KEYFILE", sheets_keyfile),
            ("GOOGLE_SHEET_ID", sheet_id),
        ]
        if not value
    ]
    if missing:
        print(f"ERROR: missing required environment variables: {missing}")
        sys.exit(1)

    return project_id, sheets_keyfile, sheet_id


def _stringify(value):
    # The Sheets API's values.update wants JSON-serializable cell values.
    # str/int/float/bool pass straight through; anything else BigQuery
    # might hand back (date, datetime, Decimal) is converted to its
    # string form rather than letting the API call fail on an
    # unserializable type.
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _fetch_rows(client: bigquery.Client, project_id: str, table: str) -> tuple[list[str], list[list]]:
    # ORDER BY 1: deterministic ordering (by each mart's first/leading
    # grain column) so reruns produce clean, reviewable diffs in the
    # Sheet's revision history, not a different row order every time.
    query = f"SELECT * FROM `{project_id}.{MARTS_DATASET}.{table}` ORDER BY 1"
    result = client.query(query).result()
    header = [field.name for field in result.schema]
    rows = [[_stringify(value) for value in row.values()] for row in result]
    return header, rows


def _write_tab(service, sheet_id: str, tab_name: str, header: list[str], rows: list[list]) -> None:
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=tab_name
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{tab_name}!A1",
        valueInputOption="RAW",
        body={"values": [header] + rows},
    ).execute()


def main() -> None:
    load_dotenv()
    project_id, sheets_keyfile, sheet_id = _require_env()

    # Explicit credentials for BigQuery, not bare bigquery.Client(project=...)
    # relying on ambient Application Default Credentials -- that only works
    # if GOOGLE_APPLICATION_CREDENTIALS happens to already be set in the
    # shell (true in scheduled_pipeline.yml, since google-github-actions/auth
    # sets it; not true for a plain local run, which would otherwise fail
    # with an unhelpful "default credentials not found" error). Reuses
    # DBT_KEYFILE -- the same nsw-fuel-dbt-runner identity already has read
    # access to marts, so there's no need for a fifth service account just
    # for this script.
    dbt_keyfile = os.environ.get("DBT_KEYFILE", "")
    if dbt_keyfile:
        bq_credentials = service_account.Credentials.from_service_account_file(dbt_keyfile)
        bq_client = bigquery.Client(project=project_id, credentials=bq_credentials)
    else:
        bq_client = bigquery.Client(project=project_id)

    sheets_credentials = service_account.Credentials.from_service_account_file(
        sheets_keyfile, scopes=SHEETS_SCOPES
    )
    sheets_service = build("sheets", "v4", credentials=sheets_credentials)

    for tab_name, table in SHEET_TABS.items():
        header, rows = _fetch_rows(bq_client, project_id, table)
        _write_tab(sheets_service, sheet_id, tab_name, header, rows)
        print(f"Wrote {len(rows)} rows to tab '{tab_name}' (from {table}).")

    print("Done.")


if __name__ == "__main__":
    main()
