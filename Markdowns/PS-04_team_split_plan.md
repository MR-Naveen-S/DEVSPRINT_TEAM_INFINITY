# PS-04 Team Split: Four Members, Phase-wise Implementation

Based on `PS-04_final_implementation_plan.md`. The work is split along the pipeline so members can build in parallel and only meet at clear data contracts.

## Roles at a glance

| Member | Role | Owns | Hands off to |
|---|---|---|---|
| **M1** | Data & Baseline Engineer | Loader, validation, derived metrics, baseline, MAD, noise floor, incident freeze | M2 (residual table) |
| **M2** | Detection & Classification Engineer | Persistence, hard rules, cross-metric logic, bid change, seasonality, alert type | M3 (flagged events) |
| **M3** | Severity, Routing & Explanation Engineer | Severity score, immediate vs digest, plain-English templates, first steps, JSON payload, output CSVs | M4 (alert files) |
| **M4** | Evaluation, Tuning & Reporting Lead | Metrics, threshold sweep, naive baseline, integration, plots, write-up, optional Isolation Forest | Final submission |

## Phase 0: Shared contract (all four, ~20 min, do first)

Agree on these interfaces before anyone codes, so the pieces plug together.

1. **Residual table (M1 -> M2):** one row per `campaign, date, metric` with columns `actual, expected, mad, noise_floor, robust_z, frozen_flag`.
2. **Flag table (M2 -> M3):** one row per flagged campaign-day with `campaign, date, type, metric, actual, expected, delta_pct, hard_rule (bool), seasonal (bool)`.
3. **Alert payload (M3 -> M4):** the JSON shape from section 3.1 of the final plan, written to `alerts_all.csv`, `alerts_immediate.csv`, `digest.csv`.
4. **Config file:** a single `config.py` holding `T`, `WINDOW=28`, `FREEZE_DAYS=14`, `PEER_DEV=0.08`, `PEER_SHARE=0.40`, volume guards. Only M4 changes values after tuning begins.
5. **Repo setup:** one repo, one module per member (`baseline.py`, `detect.py`, `route_explain.py`, `evaluate.py`) and `anomaly_alerting.py` as the entry point.
6. **Stub data:** M1 pushes a small synthetic dataset on day one so M2 to M4 can test without waiting for real data.

---

## M1: Data & Baseline Engineer (`baseline.py`)

**Phase 1: Baseline run (~30 min)**
- Build `load_real()` with alias mapping (`campaign_id`, `campaign_name`, `cost`, `conv`, `day`).
- Add validation: required columns, missing dates, duplicate campaign-days, negatives; fail loudly with clear messages.
- Derive CPA, CTR, CVR; handle divide-by-zero.
- Push the synthetic stub dataset.

**Phase 2: Tuning (~45 min)**
- Implement rolling 28-day median per campaign and metric, day-of-week factor, shifted one day.
- Implement MAD (x1.4826) per campaign and metric.
- Implement Poisson floor for counts and binomial floor for CVR; effective band = max(T x MAD, floor).
- Implement the incident freeze (flagged days excluded from the baseline for up to 14 days; needs a feedback hook from M2's flags).
- Output the residual table to the Phase 0 contract.

**Phase 3: Reporting support (~30 min)**
- Unit tests: today never in its own baseline; frozen days excluded; small-campaign floor widens the band.
- Provide baseline-window parameter so M4 can run the 21/28/35-day sensitivity check.
- Write the "Data and baseline" paragraph of the method section.

**Phase 4: Polish**
- Weekly aggregate view for the smallest campaigns.
- Baseline band data export for M4's plots.

---

## M2: Detection & Classification Engineer (`detect.py`)

**Phase 1: Baseline run (~30 min)**
- Consume the stub residual table; flag days where `|robust_z| > T`.
- Implement persistence: alert when flagged 2 of the last 3 days.
- Emit the flag table to contract.

**Phase 2: Tuning (~45 min)**
- Hard rules with volume guards:
  - tracking break: conversions = 0 for 2+ days while clicks and spend are normal and expected conversions exceed the guard;
  - budget exhausted: spend cap pattern or late-cycle click collapse with expected volume above guard.
- Bid strategy change: use the `bid_strategy` column if present; otherwise infer from joint CPA and spend shift with stable clicks.
- Cross-metric logic: spend up + conversions down = tracking or efficiency break; spend down + clicks down = delivery or budget issue.
- Seasonality: if at least 40% of campaigns move the same way by more than 8%, remove the peer median move; label seasonal if the residual returns to range. Route label "Seasonality / Normal Variance".
- Assign final type: `tracking_break`, `budget_exhausted`, `bid_strategy_change`, `seasonal_shift`, `other_anomaly`.
- Send flagged days back to M1 for the freeze.

**Phase 3: Reporting support (~30 min)**
- Review any alert that did not match a seeded incident together with M4: false positive or unseeded real anomaly.
- Write the "Detection rules and seasonality" paragraph.

**Phase 4: Polish**
- Optional: Isolation Forest on standardized residuals as a secondary "other anomaly" signal, never paging alone (coordinate with M4).

---

## M3: Severity, Routing & Explanation Engineer (`route_explain.py`)

**Phase 1: Baseline run (~30 min)**
- Write one plain-English template per alert type with metric, actual, expected, % change, baseline window.
- Add a first diagnostic step per type (e.g. tracking break: "Check the conversion tag and landing page snippet; test a conversion in preview mode.").
- Write the three output CSVs from stub flags so M4 can start evaluating.

**Phase 2: Tuning (~45 min)**
- Severity score = type weight x deviation size x campaign spend share; set HIGH cutoff.
- Routing: HIGH pages immediately; everything else goes to the digest; seasonal always goes to the digest.
- Build the final JSON payload including `route`, `severity`, `explanation`, `first_step`.
- Spot-check 2 to 3 messages per type: quoted numbers must match source data (do this with M1's baseline values).

**Phase 3: Reporting support (~30 min)**
- Provide the totals split: pages vs digest.
- Pick 3 to 4 example alerts for the write-up (one tracking break, one budget, one seasonal digest item, one miss-adjacent).
- Write the "Severity and routing" paragraph.

**Phase 4: Polish**
- Combine the digest into one daily summary message.
- Optional: simple HTML or markdown digest view.

---

## M4: Evaluation, Tuning & Reporting Lead (`evaluate.py`, `anomaly_alerting.py`)

**Phase 1: Baseline run (~30 min)**
- Build the entry point that chains M1 to M2 to M3 and runs end to end on stub data.
- Load `incidents.csv`; exclude `seasonal` rows from scoring.
- Implement matching: an alert matches an incident if same campaign and date within start/end window.
- Compute a first pass of recall, precision, per-incident detection lag.
- Run the acceptance checklist on the first end-to-end run.

**Phase 2: Tuning (~45 min)**
- Threshold sweep T = 3 to 6; choose T in the flat region of the sweep, not the single best value.
- Window sensitivity check (21, 28, 35 days); confirm recall and page count are stable.
- Confusion matrix at campaign-day level; FPR = FP / (FP + TN) on non-incident days; page-only precision; false-positive pages per month.
- Build the naive fixed-threshold baseline (e.g. +/-30% vs previous day) for the before/after comparison.
- Freeze final values in `config.py` and tell the team.

**Phase 3: Reporting (~30 min)**
- Assemble the submission: headline numbers, precision and recall (overall and pages only), missed incidents with reasons, method summary (merging the paragraphs from M1 to M3), before/after table, limitations.
- Limitations to state: tiny campaigns on conversions, gradual drift absorbed before the freeze, peer-based seasonality only, small incident set means wide uncertainty.
- Final run on real data; verify the acceptance checklist.

**Phase 4: Polish**
- Per-campaign plots: metric, baseline band, flagged day, incident window.
- Mermaid workflow diagram in the write-up.
- Optional: report Isolation Forest results separately.

---

## Timeline view

| Time | M1 | M2 | M3 | M4 |
|---|---|---|---|---|
| 0:00-0:20 | Phase 0 contract | Phase 0 | Phase 0 | Phase 0 |
| 0:20-0:50 | Loader, validation, stub data | Persistence on stub | Templates + first steps | End-to-end entry point, matching |
| 0:50-1:35 | Baseline, MAD, floor, freeze | Hard rules, seasonality, classification | Severity, routing, payload | Sweep, sensitivity, confusion matrix, naive baseline |
| 1:35-2:05 | Tests, window parameter | Review non-matching alerts | Example alerts, totals | Write-up, final real-data run |
| 2:05+ | Weekly view | Optional Isolation Forest | Daily digest message | Plots, diagram |

## Integration checkpoints

1. **After Phase 1 (~0:50):** full pipeline runs on stub data. Anyone who is blocked flags it now.
2. **After Phase 2 (~1:35):** real data run; M4 freezes `config.py`.
3. **Before submission:** all four tick the acceptance checklist together (script runs, explanations present, totals, precision/recall, misses, seasonal in digest, before/after, limitations).

## Risks specific to the split

| Risk | Mitigation |
|---|---|
| Interface mismatch between modules | Phase 0 contracts plus stub data on day one |
| M1/M2 freeze feedback loop is circular | M1 exposes a `freeze(flags)` function; M2 calls it after each pass; test on stub data |
| M4 is a bottleneck at the end | M1 to M3 each write their own method paragraph so M4 only assembles |
| Config changes mid-tuning | Only M4 edits `config.py` after Phase 2 starts |
