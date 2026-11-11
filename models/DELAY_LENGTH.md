# Delay-length model: barely beats "the usual length for that cause"

*Reproduce: `.venv/bin/python models/delay_length.py` (about 6 seconds, after `warehouse/build.py`). Numbers below are from `models/output/delay_length_metrics.json`, 2026-11-11.*

## Task

When a subway delay is first reported, predict:
1. **How long it will be** (`min_delay`, minutes).
2. **The chance it is a big one** (20+ minutes, where the Bike Share effect is clear).

Inputs are only what is known at that moment: cause code, line, station, single station or stretch, direction, hour, weekday, month. `min_gap` and `vehicle` are left out because they are recorded after the fact.

## Data and scoring

- Delays of 1+ minute on Lines 1, 2 and 4.
- **Train: 2014-2024** (73,171 delays). **Test: 2025-2026** (16,548 delays), held out and scored **once**.
- **Baseline:** the median length per cause code, and the share of 20+ minute delays per cause code, fitted on training years only.
- **Model:** gradient-boosted trees (scikit-learn `HistGradientBoosting`; absolute-error loss for length).

## Results on 2025-2026

| | Model | Baseline: per cause code | Baseline: one overall median |
|---|---|---|---|
| Length, mean absolute error | **3.88 min** | 4.01 min | 4.24 min |
| Big delay, AUC | 0.824 | 0.821 | - |
| Big delay, Brier score | 0.0400 | 0.0400 | - |
| Real big delays in the top 5% of scores | 29% | 30% | - |

- **Length:** the model is better by **0.12 minutes** (95% bootstrap range 0.11 to 0.14). Real, but about 3%.
- **Big-delay warning:** **no improvement.** AUC and Brier score are the same within noise, and the baseline catches slightly more big delays in its top 5%.

## What it means

Almost all the predictable information about a delay's length is in **its cause**. Station, line, time and direction add very little on top. Delay length is mostly noise beyond that: the median delay is 4-5 minutes, but the same cause can produce 2 minutes or 2 hours.

## Consequences for the project

- **Use the cause-code baseline in practice.** It is simpler, explainable ("medical emergencies usually last N minutes"), and as good.
- **The live side has less to go on.** Live TTC alerts carry no cause code, only text ("due to a medical emergency"). A live predictor would need that text mapped to codes first, and could at best match this baseline.
- **Signals that might add real information** (not tried; any attempt must be judged on data other than 2025-2026, which is now used): how many delays the same line had in the previous hour, and whether the live alert says "no service" or "slower than usual".
