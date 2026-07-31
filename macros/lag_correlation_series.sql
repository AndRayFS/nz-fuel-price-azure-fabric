{% macro lag_correlation_series(factor_relation, factor_date_col, factor_value_col,
                                  target_relation, target_date_col, target_value_col,
                                  period_start, period_end, max_lag) %}

select
    lag_weeks,
    n,
    case
        when n < 3 then null
        when (n*sum_x2 - sum_x*sum_x) <= 0 or (n*sum_y2 - sum_y*sum_y) <= 0 then null
        else (n*sum_xy - sum_x*sum_y)
             / sqrt((n*sum_x2 - sum_x*sum_x) * (n*sum_y2 - sum_y*sum_y))
    end as r
from (
    select
        lag_weeks,
        count(*) as n,
        sum(x) as sum_x,
        sum(y) as sum_y,
        sum(x*y) as sum_xy,
        sum(x*x) as sum_x2,
        sum(y*y) as sum_y2
    from (
        select
            l.lag_weeks,
            f.{{ factor_value_col }} as x,
            t.{{ target_value_col }} as y
        from (
            select 0 as lag_weeks
            {% for i in range(1, max_lag + 1) %}
            union all select {{ i }}
            {% endfor %}
        ) l
        inner join {{ factor_relation }} f
            on f.{{ factor_date_col }} between '{{ period_start }}' and {% if period_end %}'{{ period_end }}'{% else %}cast(getdate() as date){% endif %}
        inner join {{ target_relation }} t
            on t.{{ target_date_col }} = dateadd(week, l.lag_weeks, f.{{ factor_date_col }})
    ) paired
    group by lag_weeks
) stats

{% endmacro %}
