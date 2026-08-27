{% macro generate_schema_name(custom_schema_name, node) -%}
    {#-
        Use the custom schema name (staging / marts) verbatim instead of
        dbt's default `<target_schema>_<custom_schema>` concatenation, so
        each layer gets its own clearly-named BigQuery dataset -- matching
        the nsw-fuel-dbt-runner / nsw-fuel-ci service accounts' IAM roles
        (Viewer on `raw`, Editor on `staging`/`marts`) described in the
        README, and what scripts/export_dashboard_snapshot.py queries.

        Unlike tfnsw-transit-pulse's equivalent macro, this doesn't
        special-case the `ci` target into one collapsed dataset: this
        project's `ci` target is the real scheduled production pipeline
        (see .github/workflows/scheduled_pipeline.yml), not a disposable
        fixture run, so it uses the same per-layer datasets as `dev`
        rather than needing a separate throwaway dataset to provision.
    -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
