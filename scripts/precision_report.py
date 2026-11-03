"""Release gate (TRD.md 5.5): alert precision on field-verified alerts, lower 95% Wilson bound.

Run:  uv run python scripts/precision_report.py
Exits with code 1 when the gate is not met, so it can guard a release script.
"""

from __future__ import annotations

from collections import Counter

from kinara.api.store import open_store
from kinara.config import load_settings
from kinara.validate.metrics import precision_report

MIN_VERIFIED = 300


def main() -> None:
    cfg = load_settings()
    feats = open_store().alerts(limit=1_000_000)["features"]
    statuses = [f["properties"].get("status") for f in feats]
    r = precision_report(statuses, cfg["validation"]["target_precision"])
    print(f"alerts: {len(feats)}  " + "  ".join(f"{k}: {v}" for k, v in sorted(Counter(statuses).items())))
    if not r["n"]:
        print("no verified alerts yet (confirmed / false alarm)")
        raise SystemExit(1)
    print(f"precision {r['precision']:.3f} on {r['n']} verified; 95% Wilson {r['ci_low']:.3f} to {r['ci_high']:.3f}")
    ready = r["meets_target"] and r["n"] >= MIN_VERIFIED
    print(f"release gate (lower bound >= {cfg['validation']['target_precision']}, n >= {MIN_VERIFIED}): "
          f"{'MET' if ready else 'NOT MET'}")
    raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
