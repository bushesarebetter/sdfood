"""How often does the band rule keep a band when points say nothing about the outcome?

Simulates the backtest the export runs, with no gradient: about 3,300 labelled City restaurants at
each of three origins three months apart, points drawn to match the real list's shares (2.5%, 7.5%
and 17.5% at 17, 12 and 8 points or more), and a major at the next routine inspection with the same
21% chance for every place. The origins overlap the way the real ones do: a place keeps its points
and, with probability `--carry`, the same label from one origin to the next (the same next
inspection falls in both label years). Reports the share of simulations in which validate_bands
keeps at least one band, for independent and for overlapping origins.

    python tools/band_null_sim.py            # 2,000 simulations each; takes about a minute
"""
import argparse, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_site as es  # noqa: E402

CUTS = [17.0, 12.0, 8.0]
SHARES = [(0.025, 17), (0.05, 12), (0.10, 8)]      # the share of the list in each band, top down


def points(rng, n):
    u = rng.random(n)
    p = rng.integers(0, 8, n).astype(float)           # below the bands: 0 to 7 points
    top = u < 0.025
    mid = (u >= 0.025) & (u < 0.075)
    low = (u >= 0.075) & (u < 0.175)
    p[top] = rng.integers(17, 30, top.sum())
    p[mid] = rng.integers(12, 17, mid.sum())
    p[low] = rng.integers(8, 12, low.sum())
    return p


def one(rng, n, rate, carry, origins=3):
    pts = points(rng, n)
    y = (rng.random(n) < rate).astype(float)
    out = []
    for k in range(origins):
        if k:
            redraw = rng.random(n) >= carry
            y = np.where(redraw, (rng.random(n) < rate).astype(float), y)
            move = rng.random(n) < 0.1                  # a tenth of places gain or lose a point or two
            pts = np.where(move, np.maximum(0, pts + rng.integers(-2, 3, n)), pts)
        out.append((pts.copy(), y.copy(), np.ones(n, bool), np.ones(n, bool)))
    return es.validate_bands(CUTS, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--n", type=int, default=3300)
    ap.add_argument("--rate", type=float, default=0.21)
    ap.add_argument("--carry", type=float, default=0.6, help="chance a place's label is the same at the next origin")
    a = ap.parse_args(argv)
    rng = np.random.default_rng(0)
    for carry, name in ((0.0, "independent origins"), (a.carry, f"overlapping origins (carry {a.carry})"),
                        (0.9, "heavily overlapping origins (carry 0.9)")):
        kept = sum(bool(one(rng, a.n, a.rate, carry)) for _ in range(a.sims))
        lo, hi = es.wilson(kept, a.sims)
        print(f"{name}: a band kept in {kept} of {a.sims} null simulations = {kept / a.sims:.2%} (95% {lo:.2%} to {hi:.2%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
