-- depends_on: {{ ref('periods') }}
-- depends_on: {{ ref('silver_general') }}
-- depends_on: {{ ref('silver_fuel') }}

{% set periods_query %}
    select period_id, period_name, start_date, end_date, period_type
    from {{ ref('periods') }}
{% endset %}
{% set periods = dbt_utils.get_query_results_as_dict(periods_query) %}

{% set factors = [
    {'name': 'dubai_crude_usd', 'relation': ref('silver_general'), 'date_col': 'Date', 'value_col': 'dubai_crude_usd'},
    {'name': 'exchange_rate',   'relation': ref('silver_general'), 'date_col': 'Date', 'value_col': 'exchange_rate'}
] %}

{% set fuels = ['Regular Petrol', 'Premium Petrol 95R', 'Diesel'] %}

{% set n_periods = periods['period_id'] | length %}
{% set blocks = [] %}

{% for p in range(n_periods) %}
  {% set p_start = periods["start_date"][p] %}
  {% set p_end = periods["end_date"][p] if periods["end_date"][p] else modules.datetime.date.today() %}
  {% set period_weeks = (p_end - p_start).days // 7 %}
  {% set period_max_lag = [10, (period_weeks // 3)] | min %}
  {% for factor in factors %}
    {% for fuel in fuels %}
      {% set target_relation %}
        (select Date, board_price from {{ ref('silver_fuel') }} where Fuel = '{{ fuel }}')
      {% endset %}
      {% set block %}
select
    '{{ periods["period_id"][p] }}' as period_id,
    '{{ periods["period_name"][p] }}' as period_name,
    '{{ periods["period_type"][p] }}' as period_type,
    '{{ factor.name }}' as factor,
    '{{ fuel }}' as fuel,
    lag_weeks, n, r
from (
    {{ lag_correlation_series(
        factor_relation=factor.relation,
        factor_date_col=factor.date_col,
        factor_value_col=factor.value_col,
        target_relation=target_relation,
        target_date_col='Date',
        target_value_col='board_price',
        period_start=periods["start_date"][p],
        period_end=periods["end_date"][p],
        max_lag=period_max_lag
    ) }}
) sub
      {% endset %}
      {% do blocks.append(block) %}
    {% endfor %}
  {% endfor %}
{% endfor %}

select * from (
{{ blocks | join('\nunion all\n') }}
) all_results
