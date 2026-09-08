# Part 9 draft — the week the model could not see

Status: **drafted 8 Sep 2026**, not published. Russian first, at the owner's
request; the series is published in English, so a translation is still owed.

Ordering, both of which are the owner's call:

- **Part 8 has not gone out yet** (Part 7 published 18 Aug). This is Part 9
  and cannot precede it.
- **`draft_part8.md` says Part 9 should not be written until the nowcast is
  implemented in `pipeline/backtest.py`.** It is measured and validated, not
  implemented — deployment waits on the rebuilt weekly load settling. The
  draft below therefore says plainly that it is not in the report, which
  meets the spirit of that condition but not its letter.

Numbers: `docs/research.md`, "The week in progress is partly visible" and
"The nowcast survives the walk-forward test". Chart:
`research/art/nowcast_chart.py` -> `nowcast_error_2026.png`.

## The picture

Two curves through 2026 for Regular Petrol at two weeks ahead: today's model,
and the same model told what the week in progress has done so far. The y axis
is the **running sum of absolute errors** — every week's |forecast − actual|
added on, no averaging — and the label says so in full, because "error piled
up" read equally well as a running mean. Cumulative rather than week-by-week,
because the weekly version is a sawtooth.

One forecast is made each week and each covers a fortnight, so the windows
overlap and the 33 errors are not independent. That is standard for a rolling
backtest and is stated in the footer rather than left for a reader to work
out.

Five quiet weeks in January where the lines are one line, then the Iran-US
episode from 6 February where they part. Ends 202.5 against 170.3 c/L —
32.3 c/L, 16%.

## The draft, ~1,300 characters

Полтора месяца я строил модель, которая по определению не видела самого
важного.

MBIE публикует цены на топливо раз в неделю, по средам. Модель берёт их и
прогнозирует на две недели вперёд. Загвоздка в том, что неделя, которую она
прогнозирует, **уже идёт** — данных по ней просто ещё нет.

❓ Можно ли узнать про неё хоть что-то заранее?

💡 Оказалось, да. Затраты импортёра в новозеландской статистике — это цена
сингапурского топлива на текущей неделе по текущему курсу. А нефть и валюта
торгуются каждый день, пока MBIE ждёт среды. К моменту прогноза три торговых
дня новой недели уже прожиты.

Я взял эти три дня по Brent, перевёл в новозеландские доллары и отдал модели.

✅ Ошибка прогноза на две недели упала на 13%. Проверено на 707 неделях с 2013
года, с переобучением на каждой неделе, чтобы модель никогда не подглядывала
вперёд.

✅ В спокойные недели не изменилось ничего. Весь выигрыш пришёлся на 2026-й:
за январь две кривые на графике — одна линия, а с началом кризиса 6 февраля
они расходятся. К августу разница 32 цента на литр накопленной ошибки, 16%.

✅ Проверка от самообмана: вместо свежих данных подставил прошлонедельные.
Прогноз стал **хуже**. Значит, работает новая информация, а не лишний
коэффициент в формуле.

⚠️ В отчёте этого пока нет. Сначала должна отработать перестроенная
еженедельная загрузка — про неё следующий пост.

Иногда лучший способ улучшить модель — не усложнять её, а посмотреть в окно ☕

NZ Fuel Price Project — Part 9

## Notes on choices

- **No point-forecast language**, per the house rule: the post is about the
  error of a method, never about where prices go next.
- **The limitation is the closing beat, not a footnote.** Saying "not in the
  report" in the body is what lets the post exist before the code ships.
- The placebo bullet is there because it is the one check a sceptical reader
  would ask for, and it is cheap to state in one line.
- 13% is the walk-forward average at h=2 across both fuels and all regimes;
  16% is 2026 alone for petrol. Both are in `research.md`; quoting either
  without the other would be picking.
- Links to GitHub and the public report go in the **first comment**, per the
  series convention.
