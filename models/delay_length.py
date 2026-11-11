"""Predict how long a subway delay will last, scored against a simple baseline.

Usage: .venv/bin/python models/delay_length.py

Task: when a delay is first reported, predict (a) its length in minutes (min_delay) and
(b) the chance it is a big one (20+ minutes), using only what is known at that moment:
cause code, line, station, stretch or single station, direction, hour, weekday, month.
Not used: min_gap and vehicle, which are recorded after the fact.

Data: delays of 1+ minute on Lines 1/2/4. Train 2014-2024; test 2025-2026, held out
and scored once. Baselines, fitted on train only: median length per cause code, and
share of 20+ minute delays per cause code. Model: gradient-boosted trees
(scikit-learn HistGradientBoosting) on the inputs above.

Writes models/output/delay_length_metrics.json; prints a summary.
"""
import json
from pathlib import Path

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "warehouse" / "linedown.duckdb"
OUT = Path(__file__).resolve().parent / "output"
SEED = 20261111
BIG = 20          # minutes: a "big" delay (where the bike effect is clear)
RARE = 30         # cause codes with fewer training rows are pooled as OTHER
TEST_FROM = 2025
CATEGORICAL = ["code", "line", "station", "bound"]
NUMERIC = ["stretch", "hour", "dow", "month"]

QUERY = """
select year(occurred_at) as year, coalesce(code, 'NONE') as code, line,
       coalesce(station, 'UNKNOWN') as station, coalesce(bound, '?') as bound,
       (station_to is not null)::int as stretch, hour(occurred_at) as hour,
       dayofweek(occurred_at) as dow, month(occurred_at) as month, min_delay
from subway_delays
where line in ('1', '2', '4') and min_delay > 0
order by delay_id
"""


def load():
    con = duckdb.connect(str(DB), read_only=True)
    rows = con.execute(QUERY).fetchall()
    cols = [d[0] for d in con.description]
    return {c: np.array([r[i] for r in rows]) for i, c in enumerate(cols)}


def encode(data, train):
    """Categories -> integer codes learned on train; rare or unseen values -> OTHER."""
    X = []
    for c in CATEGORICAL:
        values, counts = np.unique(data[c][train], return_counts=True)
        vocab = {v: i for i, v in enumerate(values[counts >= RARE])}
        other = len(vocab)
        X.append(np.array([vocab.get(v, other) for v in data[c]]))
    X += [data[c].astype(float) for c in NUMERIC]
    return np.column_stack(X).astype(float)


def code_baselines(code, y, train):
    """Per-code median length and per-code big-delay share, fitted on train rows only.
    Rare codes fall back to the overall value; the share is smoothed toward the overall rate."""
    med_all = float(np.median(y[train]))
    big_all = float(np.mean(y[train] >= BIG))
    med, share = {}, {}
    for c in np.unique(code[train]):
        yc = y[train][code[train] == c]
        med[c] = float(np.median(yc)) if len(yc) >= RARE else med_all
        share[c] = (np.sum(yc >= BIG) + 10 * big_all) / (len(yc) + 10)
    return (np.array([med.get(c, med_all) for c in code]),
            np.array([share.get(c, big_all) for c in code]), med_all)


def boot_range(a, b, rng, n=1000):
    """95% bootstrap range of mean(a) - mean(b) over the same resampled rows."""
    idx = rng.integers(0, len(a), size=(n, len(a)))
    diffs = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    return [round(float(x), 3) for x in np.percentile(diffs, [2.5, 97.5])]


def main():
    data = load()
    y = data["min_delay"].astype(float)
    train, test = data["year"] < TEST_FROM, data["year"] >= TEST_FROM
    X = encode(data, train)
    cat_mask = [True] * len(CATEGORICAL) + [False] * len(NUMERIC)
    rng = np.random.default_rng(SEED)

    base_len, base_big, med_all = code_baselines(data["code"], y, train)

    reg = HistGradientBoostingRegressor(loss="absolute_error", categorical_features=cat_mask, max_iter=500,
                                        learning_rate=0.05, early_stopping=True, random_state=SEED)
    reg.fit(X[train], y[train])
    clf = HistGradientBoostingClassifier(categorical_features=cat_mask, max_iter=500, learning_rate=0.05,
                                         early_stopping=True, random_state=SEED)
    clf.fit(X[train], y[train] >= BIG)

    yt, big_t = y[test], y[test] >= BIG
    err_model = np.abs(reg.predict(X[test]) - yt)
    err_code = np.abs(base_len[test] - yt)
    err_flat = np.abs(med_all - yt)
    p_model, p_code = clf.predict_proba(X[test])[:, 1], base_big[test]

    m = {
        "train_rows": int(train.sum()), "test_rows": int(test.sum()), "test_years": f"{TEST_FROM}-2026",
        "length_mae_minutes": {
            "model": round(float(err_model.mean()), 3),
            "baseline_median_per_cause_code": round(float(err_code.mean()), 3),
            "baseline_overall_median": round(float(err_flat.mean()), 3),
            "model_better_than_code_baseline_by": round(float(err_code.mean() - err_model.mean()), 3),
            "improvement_95_range": boot_range(err_code, err_model, rng),
        },
        f"big_delay_{BIG}min": {
            "test_share": round(float(big_t.mean()), 4),
            "auc_model": round(float(roc_auc_score(big_t, p_model)), 4),
            "auc_code_baseline": round(float(roc_auc_score(big_t, p_code)), 4),
            "brier_model": round(float(brier_score_loss(big_t, p_model)), 5),
            "brier_code_baseline": round(float(brier_score_loss(big_t, p_code)), 5),
            "brier_improvement_95_range": boot_range((p_code - big_t) ** 2, (p_model - big_t) ** 2, rng),
        },
    }
    # how well does each rank actual big delays? share of real big delays in the top 5% of scores
    top = int(0.05 * len(yt))
    m[f"big_delay_{BIG}min"]["big_delays_caught_in_top_5pct_model"] = round(float(big_t[np.argsort(-p_model)[:top]].sum() / big_t.sum()), 4)
    m[f"big_delay_{BIG}min"]["big_delays_caught_in_top_5pct_baseline"] = round(float(big_t[np.argsort(-p_code, kind="stable")[:top]].sum() / big_t.sum()), 4)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "delay_length_metrics.json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()
