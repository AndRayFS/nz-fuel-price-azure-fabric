"""Page 1 headline: a decision table over two clauses, mirrored later in DAX.

Clause A - the price over four weeks, per fuel: rose / fell / held (|d| < FLAT).
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
    if len(up) == 3:
        return 'all-up', f"Pump prices rose {amount(vals)} c/L in four weeks."
    if len(down) == 3:
        return 'all-down', f"Pump prices fell {amount(vals)} c/L in four weeks."
    if not up and not down:
        return 'all-flat', "Pump prices barely moved in four weeks."
    pet = (d['91'] + d['95']) / 2
    def verb(x):
        return f"rose {r(x)} c/L" if x >= FLAT else f"fell {r(x)} c/L" if x <= -FLAT else "held steady"
    pv, dv = verb(pet), verb(d['D'])
    if pv == dv:
        return 'mixed-same', "Pump prices barely moved in four weeks." if pv == "held steady" else f"Pump prices {pv} in four weeks."
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
