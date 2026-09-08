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

## The pictures

Two, and they carry the limitation the text only names.

`research/art/nowcast_levels.py` -> `nowcast_levels_2026.png`. Petrol and
diesel through 2026, two weeks ahead, in c/L: what the price did, what the
model called, what the corrected model called. Each forecast is plotted on the
week it was a call **for**, not the week it was made. It shows the gain and it
shows March, where neither version came close.

`research/art/nowcast_chart.py` -> `nowcast_error_2026.png`. Running sum of
absolute errors through 2026: one line through the quiet weeks, parting from 6
February. Optional second image if one is not enough.

## The draft, ~1,500 characters

В моей модели прогноза цен на топливо была дыра, о которой я знал с самого
начала.

MBIE публикует данные раз в неделю, по средам. Модель прогнозирует на две
недели вперёд — но первая из этих двух недель **уже идёт**, и данных по ней
ещё нет.

При этом кое-что о ней известно. Затраты импортёра в статистике MBIE привязаны
к цене топлива в Сингапуре и к курсу доллара. Сингапурские котировки платные,
зато нефть и валюта торгуются каждый день, пока MBIE ждёт среды. К моменту
прогноза три торговых дня новой недели уже прошли.

Я взял эти три дня по Brent, перевёл в новозеландские доллары и добавил в
модель.

✅ Средняя ошибка прогноза на две недели упала на 13%. Проверено на 707
неделях с 2013 года: модель переобучалась заново каждую неделю, только на
данных до этой недели.

✅ Заметнее всего в кризис. Когда цена ходит на 5–20 центов за две недели,
модель промахивалась примерно на две трети движения — теперь примерно на
половину.

Но это не серебряная пуля, и графики показывают ограничения лучше, чем я мог
бы их описать.

⚠️ В спокойные недели разницы нет. Местами даже чуть хуже — на десятые доли
цента.

⚠️ Марта 2026-го не предвидела ни одна версия. Цена ушла вверх на 95 центов по
бензину и почти на 200 по дизелю. Поправка развернулась на неделю раньше и
держалась на 6–7 центов ближе к факту, но обе модели остались далеко позади.

⚠️ В шести самых резких неделях года выигрыш почти исчезает.

Так что это не предсказание будущего. Это использование информации, которая
уже существует — просто приходит раньше отчёта.

В сам отчёт пока не внедрено: сначала должна отработать перестроенная
еженедельная загрузка. Про неё следующий пост.

NZ Fuel Price Project — Part 9

## Notes on choices

- **The limitations are three bullets, not one apologetic sentence.** The
  charts show them anyway; naming them first is cheaper than being corrected
  in the comments.
- **"Not a silver bullet" is the spine.** The earlier draft led with 19% in
  the top decile of weeks, which was true and misleading: that decile spans
  moves from 8 to 56 c/L, so one number covered wildly different weeks. The
  5–20 c/L band with "two thirds of the move, now half" says the same thing
  without the bucket doing the work.
- **13%, not 13.9%**, and no second decimal anywhere: rounding down is the
  cheapest defence against a reader who recomputes.
- **No point-forecast language**, per the house rule. "Использование
  информации, которая уже существует" is the whole claim.
- Numbers: `docs/research.md`, "The week in progress is partly visible" and
  "The nowcast survives the walk-forward test". The 95 and ~200 c/L climbs
  are 20 Feb to 10 Apr (petrol, 252 -> 347) and 20 Feb to 17 Apr (diesel,
  187 -> 381).
- Links to GitHub and the public report go in the **first comment**.
