"""Page 1 headline: a decision table over two clauses, mirrored later in DAX.

Clause A - the price over four weeks, per fuel: rose / fell / held (|d| < FLAT).
A turn inside the window comes first: when a group's weekly high (or low) clears
both ends of the window by FLAT or more, the clause names the turn and its week
instead of comparing the ends (15 Nov 2026: "held steady" over +7.5 then -9.4).
Clause B - the importer margin against its 104-week norm, per fuel group:
below / close to / above (|gap| < NEAR). Petrol = mean of 91 and 95.
"still" when the group was in the same state four weeks earlier.
"""
import csv, sys, collections, datetime as dt

FLAT, NEAR, SPREAD = 3.0, 5.0, 5.0
P = {'Regular Petrol': '91', 'Premium Petrol 95R': '95', 'Diesel': 'D'}

def load(z):
    price = collections.defaultdict(dict)
    for r in csv.DictReader(open(f'{z}/weekly_prices.csv')):
        if r['adjusted_retail_price']:
            price[r['week_date']][P[r['fuel']]] = float(r['adjusted_retail_price'])
    gap = collections.defaultdict(dict)
    for r in csv.DictReader(open(f'{z}/margin.csv')):
        if r['importer_margin'] and r['margin_norm_104w']:
            gap[r['week_date']][P[r['fuel']]] = float(r['importer_margin']) - float(r['margin_norm_104w'])
    return price, gap

def back(w, n):
    return (dt.date.fromisoformat(w) - dt.timedelta(weeks=n)).isoformat()

def r(x):
    return f"{abs(x):.0f}"

def verb(x):
    return f"rose {r(x)} c/L" if x >= FLAT else f"fell {r(x)} c/L" if x <= -FLAT else "held steady"

def path(price, w, group):
    """The group's price in each week from w-4 to w that has all three fuels, oldest first."""
    out = []
    for n in range(4, -1, -1):
        wk = back(w, n); v = price.get(wk)
        if v and len(v) == 3:
            out.append((wk, (v['91'] + v['95']) / 2 if group == 'pet' else v['D']))
    return out

def turn(pts):
    """A turn inside the window: the path's high (low) clears both ends by FLAT or more.
    Returns (kind, first leg, second leg, week of the turn) or None. Both at once is
    a swing, reported as the width of the range."""
    xs = [v for _, v in pts]; s, e, hi, lo = xs[0], xs[-1], max(xs), min(xs)
    peak, trough = hi - max(s, e) >= FLAT, min(s, e) - lo >= FLAT
    if peak and trough:
        return 'swing', hi - lo, None, None
    if peak:
        return 'peak', hi - s, hi - e, pts[xs.index(hi)][0]
    if trough:
        return 'trough', s - lo, e - lo, pts[xs.index(lo)][0]
    return None

def day(wk):
    d = dt.date.fromisoformat(wk); return f"{d.day} {d:%b}"

def clause_a(price, w):
    now, then = price.get(w), price.get(back(w, 4))
    if not now or not then or len(now) < 3 or len(then) < 3:
        return None, None
    d = {f: now[f] - then[f] for f in now}
    up = [f for f in d if d[f] >= FLAT]; down = [f for f in d if d[f] <= -FLAT]
    vals = sorted(d.values())
    def amount(xs):
        xs = sorted(abs(x) for x in xs)
        return r(sum(xs) / len(xs)) if xs[-1] - xs[0] <= SPREAD else f"{xs[0]:.0f}–{xs[-1]:.0f}"
    # A turn in either group overrides the endpoint comparison below: "held steady"
    # over a rise and fall, or "rose" over a rise already falling back, misreads the path.
    tp, td = turn(path(price, w, 'pet')), turn(path(price, w, 'dsl'))
    if tp or td:
        def phrase(t, net):
            if t is None:
                return verb(net)
            kind, a, b, wk = t
            if kind == 'swing':
                return f"swung within a {r(a)} c/L range"
            return (f"rose {r(a)} c/L to {day(wk)}, then fell {r(b)}" if kind == 'peak'
                    else f"fell {r(a)} c/L to {day(wk)}, then rose {r(b)}")
        if tp and td and tp[0] == td[0] and tp[0] != 'swing' and tp[3] == td[3]:
            v1, v2 = ('rose', 'fell') if tp[0] == 'peak' else ('fell', 'rose')
            return 'turn-same', (f"Over four weeks, prices paid {v1} {amount([tp[1], td[1]])} c/L"
                                 f" to {day(tp[3])}, then {v2} {amount([tp[2], td[2]])}.")
        return 'turn-split', f"Over four weeks, petrol {phrase(tp, (d['91'] + d['95']) / 2)}; diesel {phrase(td, d['D'])}."
    if len(up) == 3:
        return 'all-up', f"Prices paid rose {amount(vals)} c/L in four weeks."
    if len(down) == 3:
        return 'all-down', f"Prices paid fell {amount(vals)} c/L in four weeks."
    if not up and not down:
        return 'all-flat', "Prices paid barely moved in four weeks."
    pet = (d['91'] + d['95']) / 2
    pv, dv = verb(pet), verb(d['D'])
    if pv == dv:
        return 'mixed-same', "Prices paid barely moved in four weeks." if pv == "held steady" else f"Prices paid {pv} in four weeks."
    return 'split', f"Petrol {pv} in four weeks; diesel {dv}."

def state(x):
    return 'below' if x <= -NEAR else 'above' if x >= NEAR else 'near'

def clause_b(gap, w):
    g, g4 = gap.get(w), gap.get(back(w, 4))
    if not g or len(g) < 3:
        return None, None
    pet, dsl = (g['91'] + g['95']) / 2, g['D']
    sp, sd = state(pet), state(dsl)
    still = {}
    if g4 and len(g4) == 3:
        still['p'] = state((g4['91'] + g4['95']) / 2) == sp
        still['d'] = state(g4['D']) == sd
    def phrase(who, x, s, key, its):
        st = 'still ' if still.get(key) and s != 'near' else ''
        if s == 'near':
            return f"{who} is close to {its} two-year average"
        return f"{who} is {st}about {r(x)} c/L {s} {its} two-year average"
    if sp == sd:
        if sp == 'near':
            return 'both-near', "Importer margins are close to their two-year average."
        lo, hi = sorted([abs(pet), abs(dsl)])
        amt = 'about ' + r((lo + hi) / 2) if hi - lo <= SPREAD else f"{lo:.0f}–{hi:.0f}"
        st = 'still ' if still.get('p') and still.get('d') else ''
        return f'both-{sp}', f"Importer margins are {st}{amt} c/L {sp} their two-year average."
    a = phrase("Petrol's margin", pet, sp, 'p', 'its')
    if sd == 'near':
        b = "diesel's is close to it"
    else:
        b = f"diesel's is {'still ' if still.get('d') else ''}about {r(dsl)} c/L {sd} it"
    return f'split-{sp}-{sd}', f"{a}; {b}."

if __name__ == '__main__':
    z = sys.argv[1]
    price, gap = load(z)
    weeks = sorted(w for w in price if w >= '2013-02-01')
    ca = collections.Counter(); cb = collections.Counter(); ex = {}
    for w in weeks:
        ka, ta = clause_a(price, w); kb, tb = clause_b(gap, w)
        ca[ka] += 1
        if kb: cb[kb] += 1
        for k, t in ((ka, ta), (kb, tb)):
            if k and k not in ex: ex[k] = (w, t)
    print('clause A, weeks since Feb 2013:', dict(ca))
    print('clause B, weeks since 29 Mar 2024:', dict(cb))
    print()
    for k, (w, t) in sorted(ex.items()): print(f"{k:22} {w}  {t}")
    print()
    for w in weeks[-6:]:
        print(w, '|', clause_a(price, w)[1], clause_b(gap, w)[1])
