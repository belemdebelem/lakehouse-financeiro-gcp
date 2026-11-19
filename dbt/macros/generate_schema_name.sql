{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- set default_schema = target.schema -%}
  {%- if custom_schema_name is none -%}
    {{ default_schema }}
  {%- elif target.name == 'prod' or (node.resource_type == 'test' and custom_schema_name.endswith('_dbt_test__audit')) -%}
    {{ custom_schema_name }}
  {%- else -%}
    {{ custom_schema_name }}_{{ target.name }}
  {%- endif -%}
{%- endmacro %}
