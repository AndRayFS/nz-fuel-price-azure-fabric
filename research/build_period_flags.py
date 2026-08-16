"""Build `seeds/period_flags.csv` — several independent regime axes, one row
per (week, fuel).

Replaces the single `period_type` axis of `seeds/periods.csv`, which mixes a
crude shock, a tax reform, a supply-chain change and a change of measurement
into one label. Rationale, thresholds and every number quoted in the docs:
`docs/period_labelling.md`.

Everything here is derived from `research/data/panel_weekly.csv` by rule.
Nothing is hand-drawn, so the whole seed is reproducible:

    source /Users/Ray/nz-fuel-price-project/.venv/bin/activate
    python research/build_period_flags.py

Two boundary dates are external facts rather than rule output — Marsden Point's
last refining week and the Envisory/Datamine changeover — and both are marked
as such below.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PANEL = Path(__file__).parent / "data" / "panel_weekly.csv"
OUT = Path(__file__).parents[1] / "seeds" / "period_flags.csv"

# --- crude volatility regime -------------------------------------------------
#
# Measured on log changes of `dubai_crude_nzd`, which is scale-free and so
# immune to the level drift that makes full-history percentiles of a *level*
# meaningless here (mbie_notes: importer margin has tripled since 2004).
#
# The window is CENTRED. This is retrospective classification of history, not a
# real-time signal: a trailing window would date every episode ~4 weeks after it
# began. Anything using these flags as a live indicator must re-derive them
# with a trailing window.
VOL_SPAN = 9
VOL_MIN_PERIODS = 5  # so the first/last 4 weeks still get a value

# Hysteresis, to stop one quiet week splitting an episode in two. Enter on
# p92 of the full-sample distribution, stay until p85, discard runs shorter
# than a month. Sensitivity to all three is tabulated in the docs.
VOL_ENTER = 0.060
VOL_STAY = 0.045
VOL_MIN_LEN = 4

# Direction over 8 weeks, published as a continuous column rather than an
# episode-level up/down label: 5 of the 9 detected episodes contain both a
# >+15% and a <-15% 8-week move, so any single direction label would be wrong
# for part of the episode.
MOVE_SPAN = 8

# Narrative shorthand for the detected episodes, keyed by the week the rule
# opens them. Names are labels for charts, NOT causal claims — the boundaries
# are measured, the attribution is not. Nothing downstream should branch on
# these strings.
EPISODE_NAMES = {
    "2004-11-19": "2004_run_up",
    "2008-08-29": "2008_gfc_crash",
    "2008-12-12": "2009_rebound",
    "2014-12-26": "2015_glut_onset",
    "2015-10-16": "2016_glut_trough",
    "2016-09-09": "2016_opec_cuts",
    "2020-02-14": "2020_covid_crash",
    "2022-02-18": "2022_ukraine",
    "2026-02-06": "2026_iran_us",
}

# --- fixed boundaries --------------------------------------------------------
#
# IDENTITY_FROM is rule output, not an external fact: it is the first week the
# published components reconcile exactly. The last non-zero residual week is
# 2010-01-01. Board price also stops being quantised to 0.1 c/L on the same
# date, which is an independent fingerprint of the same break.
IDENTITY_FROM = pd.Timestamp("2010-01-08")

# External facts, from MBIE's methodology document (docs/mbie_notes.md).
DATAMINE_FROM = pd.Timestamp("2022-01-01")  # retail source Envisory -> Datamine
IMPORT_ONLY_FROM = pd.Timestamp("2022-04-01")  # Marsden Point stopped refining

# ETS auctions began Mar 2021 and are held in the final month of each quarter.
ETS_AUCTIONS_FROM = pd.Timestamp("2021-01-01")

# Publication status, from MBIE's own pages (read by the ADL thread, Aug 2026).
# Everything from 1 Apr 2026 is Provisional and finalises only when Stats NZ
# releases the June-quarter CPI — so "provisional" here means *awaiting an
# external input*, not estimated or interpolated. This turned out to be
# load-bearing: the diesel pass-through instability is these weeks, not the
# crisis (docs/period_labelling.md §7).
PROVISIONAL_FROM = pd.Timestamp("2026-04-01")

# Separately, MBIE *suspended* publication of Importer cost and Importer margin
# from 18 Mar to 1 Jul 2026 over conflict-driven volatility, then backfilled
# them. Only those two series were paused; retail, board, tax, ETS and FX ran
# normally throughout. So this is a narrower and stronger caveat than
# PROVISIONAL_FROM, and it applies to exactly the two columns most of this
# project's margin work depends on.
COST_BACKFILL_FROM = pd.Timestamp("2026-03-18")
COST_BACKFILL_TO = pd.Timestamp("2026-07-01")

# Magnitude, deliberately separate from volatility. The volatility axis
# measures jaggedness and is blind to a large *smooth* move: Nov 2021 - May
# 2022 took crude 114 -> 170 NZD/bbl, +49%, at a weekly sd of only 5.3%, and
# two thirds of it scores `normal`. A half-year window is what catches a drift
# that slow; 8 or 13 weeks does not. Threshold is just below the p90 of |26-week
# move| (0.405), and 100 of the 168 weeks it flags are `normal` on volatility,
# so the two axes are genuinely not substitutes.
MOVE_LONG_SPAN = 26
MOVE_LONG_THRESHOLD = 0.35

# c/L. Before 2010 `taxes` is quantised to 0.1, and diesel's rounds back and
# forth between 0.3 and 0.4 for years, so any threshold at or below 0.1 picks up
# 257 "steps" of which 223 are that rounding. At 0.2 the count is 34 and every
# one is a real excise, RUC or regional-fuel-tax change.
TAX_STEP_MIN = 0.2
TAX_SMEAR_WEEKS = 1  # a step lands across the step week and the one after


def volatility_regime(crude: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Centred rolling volatility, and the hysteresis episode mask over it."""
    vol = (
        np.log(crude)
        .diff()
        .rolling(VOL_SPAN, center=True, min_periods=VOL_MIN_PERIODS)
        .std()
    )

    hot = (vol >= VOL_ENTER).to_numpy()
    warm = (vol >= VOL_STAY).to_numpy()

    state = np.zeros(len(vol), dtype=bool)
    on = False
    for i in range(len(vol)):
        on = hot[i] if not on else warm[i]
        state[i] = on

    # The forward pass can only open an episode once volatility has already
    # crossed the high threshold, which clips the run-up. Walk back over weeks
    # that were above the stay threshold to recover it.
    for i in range(len(vol) - 1, 0, -1):
        if state[i] and not state[i - 1] and warm[i - 1]:
            state[i - 1] = True

    state = pd.Series(state, index=vol.index)
    runs = (state != state.shift()).cumsum()
    keep = pd.Series(False, index=vol.index)
    for _, run in state.groupby(runs):
        if run.iloc[0] and len(run) >= VOL_MIN_LEN:
            keep.loc[run.index] = True

    return vol, keep


def main() -> None:
    panel = pd.read_csv(PANEL, parse_dates=["Date"]).sort_values(["Fuel", "Date"])

    # Crude is not fuel-specific, so the regime is derived once on one fuel's
    # rows and broadcast, rather than fitted twice on identical inputs.
    weeks = (
        panel.loc[panel.Fuel == "Diesel", ["Date", "dubai_crude_nzd"]]
        .drop_duplicates("Date")
        .sort_values("Date")
        .reset_index(drop=True)
    )

    vol, high = volatility_regime(weeks.dubai_crude_nzd)
    weeks["crude_vol_9w"] = vol.round(4)
    weeks["crude_vol_regime"] = np.where(high, "high", "normal")
    weeks["crude_move_8w"] = np.log(weeks.dubai_crude_nzd).diff(MOVE_SPAN).round(4)

    # The centred window is truncated at both ends of the sample; say so rather
    # than letting the first and last few weeks pass as fully measured.
    edge = VOL_SPAN // 2
    weeks["crude_vol_window_full"] = True
    weeks.loc[weeks.index[:edge], "crude_vol_window_full"] = False
    weeks.loc[weeks.index[-edge:], "crude_vol_window_full"] = False

    runs = (high != high.shift()).cumsum()
    weeks["crude_episode_id"] = ""
    for _, run in high.groupby(runs):
        if not run.iloc[0]:
            continue
        start = weeks.Date[run.index[0]].strftime("%Y-%m-%d")
        weeks.loc[run.index, "crude_episode_id"] = EPISODE_NAMES.get(start, "")

    move_long = np.log(weeks.dubai_crude_nzd).diff(MOVE_LONG_SPAN)
    weeks["crude_move_26w"] = move_long.round(4)
    weeks["crude_move_regime"] = np.select(
        [move_long >= MOVE_LONG_THRESHOLD, move_long <= -MOVE_LONG_THRESHOLD],
        ["large_up", "large_down"],
        default="normal",
    )

    weeks["ets_auction_quarter"] = (weeks.Date >= ETS_AUCTIONS_FROM) & (
        weeks.Date.dt.month % 3 == 0
    )
    weeks["data_status"] = np.where(
        weeks.Date >= PROVISIONAL_FROM, "provisional", "final"
    )
    weeks["cost_backfilled"] = weeks.Date.between(
        COST_BACKFILL_FROM, COST_BACKFILL_TO
    )
    weeks["data_regime"] = np.select(
        [weeks.Date < IDENTITY_FROM, weeks.Date < DATAMINE_FROM],
        ["pre2010_unreconciled", "envisory"],
        default="datamine",
    )
    weeks["identity_holds"] = weeks.Date >= IDENTITY_FROM
    weeks["supply_chain"] = np.where(
        weeks.Date < IMPORT_ONLY_FROM, "domestic_refinery", "import_only"
    )

    # Tax is the one axis that genuinely differs by fuel: diesel is taxed via
    # road user charges, not at the pump, so it has 2 steps in 22 years against
    # petrol's 25.
    out = []
    for fuel, rows in panel.groupby("Fuel", sort=True):
        rows = rows.sort_values("Date").reset_index(drop=True)
        step = rows.taxes.diff().fillna(0.0)
        step[step.abs() < TAX_STEP_MIN] = 0.0

        window = step != 0
        for k in range(1, TAX_SMEAR_WEEKS + 1):
            window |= (step != 0).shift(k, fill_value=False)

        out.append(
            pd.DataFrame(
                {
                    "week_date": rows.Date.dt.strftime("%Y-%m-%d"),
                    "fuel": fuel,
                    "tax_step_cpl": step.round(4),
                    "tax_step_window": window,
                }
            ).merge(
                weeks.drop(columns=["dubai_crude_nzd"]).assign(
                    week_date=weeks.Date.dt.strftime("%Y-%m-%d")
                ).drop(columns=["Date"]),
                on="week_date",
                how="left",
                validate="one_to_one",
            )
        )

    flags = pd.concat(out, ignore_index=True)
    flags = flags[
        [
            "week_date",
            "fuel",
            "crude_vol_regime",
            "crude_vol_9w",
            "crude_vol_window_full",
            "crude_episode_id",
            "crude_move_8w",
            "crude_move_26w",
            "crude_move_regime",
            "tax_step_cpl",
            "tax_step_window",
            "data_regime",
            "data_status",
            "cost_backfilled",
            "identity_holds",
            "supply_chain",
            "ets_auction_quarter",
        ]
    ].sort_values(["fuel", "week_date"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    flags.to_csv(OUT, index=False)

    print(f"{len(flags)} rows -> {OUT}")
    print(flags.crude_vol_regime.value_counts().to_string())
    print(flags.data_regime.value_counts().to_string())
    print(flags.crude_move_regime.value_counts().to_string())
    print(flags.data_status.value_counts().to_string())
    print(f"cost_backfilled rows: {flags.cost_backfilled.sum()}")
    print(f"tax step weeks: {(flags.tax_step_cpl != 0).sum()}")
    print(f"named episodes: {flags.crude_episode_id.nunique() - 1}")


if __name__ == "__main__":
    main()
