"""Statistical analysis of frozen FARMWISE empirical collections.

Everything here reads files written by :mod:`evaluation.collect_empirical`
and never contacts a live API, so published tables and figures can be
regenerated from the preserved collection alone.

Statistics
----------
Live-API latency is heavy-tailed, so runtime and memory are summarised by the
median and interquartile range (IQR). The median carries a percentile
bootstrap confidence interval with a fixed seed; mean and standard deviation
are reported alongside for completeness only.

Cross-source comparisons are *agreement* statistics between two sources. No
source is treated as ground truth: for national-service vs ERA5 pairs the
difference is ``national - ERA5`` purely as a sign convention.
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 42
CONFIDENCE = 0.95
# Wet day as defined for the ETCCDI indices: daily precipitation >= 1 mm.
WET_DAY_THRESHOLD_MM = 1.0
REFERENCE_SOURCE = "ERA5"
DISPATCH_STATUSES = ("success", "empty", "failure", "timeout", "invalid_response")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_collection(collection_dir) -> dict:
    """Read one frozen collection directory."""
    collection_dir = Path(collection_dir)
    payload = json.loads((collection_dir / "empirical_runs.json").read_text(encoding="utf-8"))
    manifest_path = collection_dir / payload.get("manifest", "manifest.json")
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists() else {}
    )
    observations_path = collection_dir / "cross_source_observations.csv"
    observations = (
        pd.read_csv(observations_path, parse_dates=["timestamp"])
        if observations_path.exists() else pd.DataFrame()
    )
    return {
        "manifest": manifest,
        "payload": payload,
        "runs": flatten_runs(payload),
        "dispatch": flatten_dispatch(payload),
        "observations": observations,
        "quality_dir": collection_dir / payload.get("quality_report_dir", "quality"),
    }


def flatten_runs(payload: dict) -> pd.DataFrame:
    """One row per measured run with workload, memory and routing columns."""
    rows = []
    for run in payload.get("runs", []):
        precheck = run.get("coverage_precheck") or {}
        status_counts = run.get("dispatch_status_counts") or {}
        row = {
            "run_id": run.get("run_id"),
            "experiment": run.get("experiment"),
            "scenario": run.get("scenario"),
            "dimension": run.get("dimension"),
            "input_value": run.get("input_value"),
            "mode": run.get("mode"),
            "repeat": run.get("repeat"),
            "status": run.get("status"),
            "error": run.get("error"),
            "request_wall_seconds": run.get("request_wall_seconds"),
            "precheck_seconds": precheck.get("precheck_seconds"),
            "dispatched_sources": len(run.get("dispatch") or []),
            "dispatch_seconds_sum": run.get("dispatch_seconds_sum"),
            "dispatch_seconds_max": run.get("dispatch_seconds_max"),
            "quality_report_count": run.get("quality_report_count"),
            "region": (run.get("request") or {}).get("region"),
            "period": (run.get("request") or {}).get("period"),
            "level": (run.get("request") or {}).get("level"),
        }
        for status in DISPATCH_STATUSES:
            row[f"dispatch_{status}"] = status_counts.get(status, 0)
        row["unproductive_dispatches"] = row["dispatched_sources"] - row["dispatch_success"]
        row.update(run.get("workload") or {})
        row.update(run.get("memory") or {})
        row.update({f"planned_{k}": v for k, v in (run.get("planned_coverage") or {}).items()})
        rows.append(row)
    return pd.DataFrame(rows)


def flatten_dispatch(payload: dict) -> pd.DataFrame:
    """One row per adapter call: source, status and wall time."""
    rows = []
    for run in payload.get("runs", []):
        for item in run.get("dispatch") or []:
            rows.append({
                "run_id": run.get("run_id"),
                "experiment": run.get("experiment"),
                "scenario": run.get("scenario"),
                "dimension": run.get("dimension"),
                "input_value": run.get("input_value"),
                "mode": run.get("mode"),
                "source": item.get("source"),
                "source_short": str(item.get("source", "")).split(".")[-1],
                "status": item.get("status"),
                "wall_seconds": item.get("wall_seconds"),
                "error": item.get("error"),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Robust summaries
# ---------------------------------------------------------------------------

def bootstrap_median_ci(values, *, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
                        confidence=CONFIDENCE) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the median."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy()
    if len(values) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    medians = np.median(
        rng.choice(values, size=(resamples, len(values)), replace=True), axis=1
    )
    alpha = (1 - confidence) / 2
    return (float(np.quantile(medians, alpha)), float(np.quantile(medians, 1 - alpha)))


def robust_stats(values, **bootstrap) -> dict:
    """Median, IQR and bootstrap CI of the median, plus mean/SD for reference."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if values.empty:
        return {"n": 0, "median": np.nan, "q1": np.nan, "q3": np.nan, "iqr": np.nan,
                "median_ci_low": np.nan, "median_ci_high": np.nan, "min": np.nan,
                "max": np.nan, "mean": np.nan, "std": np.nan}
    q1, median, q3 = values.quantile([0.25, 0.5, 0.75])
    low, high = bootstrap_median_ci(values, **bootstrap)
    return {
        "n": int(len(values)), "median": float(median), "q1": float(q1), "q3": float(q3),
        "iqr": float(q3 - q1), "median_ci_low": low, "median_ci_high": high,
        "min": float(values.min()), "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else np.nan,
    }


def robust_summary(df: pd.DataFrame, by, value: str, **bootstrap) -> pd.DataFrame:
    """``robust_stats`` of ``value`` for each group in ``by``."""
    by = [by] if isinstance(by, str) else list(by)
    rows = []
    for keys, group in df.groupby(by, dropna=False, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        rows.append({**dict(zip(by, keys)), **robust_stats(group[value], **bootstrap)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------

WORKLOAD_COLUMNS = (
    "requested_s2_cells", "returned_s2_cells", "returned_values", "area_km2",
    "duration_days", "requested_factors",
)


def scaling_summary(runs: pd.DataFrame, value: str = "request_wall_seconds") -> pd.DataFrame:
    """Per scaling scenario: robust summary of ``value`` and its median workload.

    Only successful runs are summarised; ``failed_runs`` counts the rest so a
    scenario with failures is visible rather than silently faster.
    """
    scaling = runs[runs["experiment"] == "scaling"]
    if scaling.empty:
        return pd.DataFrame()
    successful = scaling[scaling["status"] == "success"]
    keys = ["dimension", "input_value"]
    summary = robust_summary(successful, keys, value)
    workload = (
        successful.groupby(keys)[[c for c in WORKLOAD_COLUMNS if c in successful]]
        .median().add_prefix("median_").reset_index()
    )
    failures = (
        scaling.assign(failed=scaling["status"] != "success")
        .groupby(keys)["failed"].sum().rename("failed_runs").reset_index()
    )
    return (summary.merge(workload, on=keys, how="left")
            .merge(failures, on=keys, how="left")
            .sort_values(keys).reset_index(drop=True))


def scaling_fit(runs: pd.DataFrame, dimension: str, *, x: str, y: str = "request_wall_seconds") -> dict:
    """Log-log least-squares slope of ``y`` against workload ``x`` for one sweep.

    The slope is a descriptive scaling exponent (1 = linear), fitted on
    successful runs with positive values. It is not a significance test.
    """
    subset = runs[(runs["experiment"] == "scaling") & (runs["dimension"] == dimension)
                  & (runs["status"] == "success")]
    subset = subset[(pd.to_numeric(subset[x], errors="coerce") > 0)
                    & (pd.to_numeric(subset[y], errors="coerce") > 0)]
    if subset[x].nunique() < 2:
        return {"dimension": dimension, "x": x, "y": y, "n": len(subset),
                "slope": np.nan, "intercept": np.nan, "r_squared": np.nan}
    log_x = np.log10(subset[x].astype(float))
    log_y = np.log10(subset[y].astype(float))
    slope, intercept = np.polyfit(log_x, log_y, 1)
    predicted = slope * log_x + intercept
    ss_res = float(((log_y - predicted) ** 2).sum())
    ss_tot = float(((log_y - log_y.mean()) ** 2).sum())
    return {"dimension": dimension, "x": x, "y": y, "n": int(len(subset)),
            "slope": float(slope), "intercept": float(intercept),
            "r_squared": 1 - ss_res / ss_tot if ss_tot else np.nan}


# ---------------------------------------------------------------------------
# Coverage pre-check vs factor-only routing
# ---------------------------------------------------------------------------

def coverage_comparison(runs: pd.DataFrame) -> pd.DataFrame:
    """Per scenario and routing mode: dispatch counts, outcomes and runtime."""
    coverage = runs[runs["experiment"] == "coverage"]
    if coverage.empty:
        return pd.DataFrame()
    keys = ["scenario", "mode"]
    runtime = robust_summary(coverage, keys, "request_wall_seconds").add_prefix("runtime_")
    runtime = runtime.rename(columns={"runtime_scenario": "scenario", "runtime_mode": "mode"})
    counts = coverage.groupby(keys).agg(
        runs=("run_id", "count"),
        planned_configured_sources=("planned_configured_sources", "first"),
        planned_factor_eligible_sources=("planned_factor_eligible_sources", "first"),
        planned_precheck_dispatched_sources=("planned_precheck_dispatched_sources", "first"),
        planned_requests_avoided_vs_factor_only=("planned_requests_avoided_vs_factor_only", "first"),
        median_dispatched_sources=("dispatched_sources", "median"),
        median_unproductive_dispatches=("unproductive_dispatches", "median"),
        total_empty=("dispatch_empty", "sum"),
        total_failure=("dispatch_failure", "sum"),
        total_timeout=("dispatch_timeout", "sum"),
        median_precheck_seconds=("precheck_seconds", "median"),
        request_errors=("status", lambda s: int((s == "error").sum())),
    ).reset_index()
    return counts.merge(runtime, on=keys, how="left")


def coverage_effect(runs: pd.DataFrame, **bootstrap) -> pd.DataFrame:
    """Runtime saved per scenario: median(factor-only) - median(pre-check).

    The CI is a percentile bootstrap of the difference in medians, resampling
    each mode independently (runs are not paired across modes).
    """
    coverage = runs[runs["experiment"] == "coverage"]
    rows = []
    for scenario, group in coverage.groupby("scenario"):
        pre = group.loc[group["mode"] == "precheck", "request_wall_seconds"].dropna()
        base = group.loc[group["mode"] == "factor-only", "request_wall_seconds"].dropna()
        pre_overhead = group.loc[group["mode"] == "precheck", "precheck_seconds"].dropna()
        low, high = _bootstrap_median_difference(base, pre, **bootstrap)
        rows.append({
            "scenario": scenario,
            "n_precheck": len(pre), "n_factor_only": len(base),
            "median_runtime_precheck": pre.median() if len(pre) else np.nan,
            "median_runtime_factor_only": base.median() if len(base) else np.nan,
            "median_runtime_saved": (base.median() - pre.median()) if len(pre) and len(base) else np.nan,
            "saved_ci_low": low, "saved_ci_high": high,
            "median_precheck_seconds": pre_overhead.median() if len(pre_overhead) else np.nan,
            "requests_avoided_vs_factor_only": group["planned_requests_avoided_vs_factor_only"].iloc[0],
        })
    return pd.DataFrame(rows)


def _bootstrap_median_difference(a, b, *, resamples=BOOTSTRAP_RESAMPLES,
                                 seed=BOOTSTRAP_SEED, confidence=CONFIDENCE):
    a = pd.to_numeric(pd.Series(a), errors="coerce").dropna().to_numpy()
    b = pd.to_numeric(pd.Series(b), errors="coerce").dropna().to_numpy()
    if len(a) < 2 or len(b) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    diffs = (np.median(rng.choice(a, (resamples, len(a))), axis=1)
             - np.median(rng.choice(b, (resamples, len(b))), axis=1))
    alpha = (1 - confidence) / 2
    return (float(np.quantile(diffs, alpha)), float(np.quantile(diffs, 1 - alpha)))


# ---------------------------------------------------------------------------
# Quality-assessment overhead
# ---------------------------------------------------------------------------

def quality_overhead(runs: pd.DataFrame, **bootstrap) -> dict:
    """Runtime and memory with quality assessment off vs on for one request."""
    quality = runs[(runs["experiment"] == "quality-overhead") & (runs["status"] == "success")]
    off = quality[quality["mode"] == "off"]
    on = quality[quality["mode"] == "on"]
    low, high = _bootstrap_median_difference(
        on["request_wall_seconds"], off["request_wall_seconds"], **bootstrap
    )
    result = {
        "runtime_off": robust_stats(off["request_wall_seconds"], **bootstrap),
        "runtime_on": robust_stats(on["request_wall_seconds"], **bootstrap),
        "median_overhead_seconds": (
            on["request_wall_seconds"].median() - off["request_wall_seconds"].median()
            if len(on) and len(off) else np.nan
        ),
        "overhead_ci_low": low,
        "overhead_ci_high": high,
    }
    if "peak_rss_mb" in quality:
        result["peak_rss_off"] = robust_stats(off["peak_rss_mb"], **bootstrap)
        result["peak_rss_on"] = robust_stats(on["peak_rss_mb"], **bootstrap)
    return result


# ---------------------------------------------------------------------------
# Cross-source agreement
# ---------------------------------------------------------------------------

PAIR_KEY = ["scenario", "timestamp", "cell", "variable"]


def pair_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Pair values from two sources sharing scenario, timestamp, S2 cell and variable.

    Pairing is strict: nothing is interpolated or shifted in time. Duplicate
    values from one source for the same key are averaged and counted in
    ``duplicates_a``/``duplicates_b``. The pair is oriented so that ERA5, when
    present, is source B.
    """
    if observations.empty:
        return pd.DataFrame()
    obs = observations.copy()
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")
    obs = obs.dropna(subset=["value"])
    context = [c for c in ("region", "period") if c in obs]
    per_source = (
        obs.groupby(PAIR_KEY + context + ["source"], dropna=False)["value"]
        .agg(value="mean", records="size").reset_index()
    )
    rows = []
    for keys, same in per_source.groupby(PAIR_KEY + context, dropna=False):
        if len(same) < 2:
            continue
        for (_, first), (_, second) in combinations(same.iterrows(), 2):
            a, b = _orient(first, second)
            rows.append({
                **dict(zip(PAIR_KEY + context, keys)),
                "source_a": a["source"], "source_b": b["source"],
                "source_pair": f"{a['source']} - {b['source']}",
                "value_a": a["value"], "value_b": b["value"],
                "duplicates_a": int(a["records"] - 1), "duplicates_b": int(b["records"] - 1),
            })
    pairs = pd.DataFrame(rows)
    if not pairs.empty:
        pairs["difference"] = pairs["value_a"] - pairs["value_b"]
        pairs["absolute_difference"] = pairs["difference"].abs()
    return pairs


def _orient(first, second):
    if first["source"] == REFERENCE_SOURCE:
        return second, first
    if second["source"] == REFERENCE_SOURCE:
        return first, second
    return (first, second) if first["source"] <= second["source"] else (second, first)


def _correlation(a: pd.Series, b: pd.Series, method: str) -> float:
    if len(a) < 3 or a.nunique() < 2 or b.nunique() < 2:
        return np.nan
    return float(a.corr(b, method=method))


def agreement_metrics(pairs: pd.DataFrame, by=("variable", "source_pair")) -> pd.DataFrame:
    """n, mean bias (A - B), MAE, RMSE, Pearson r and Spearman rho per group."""
    by = list(by)
    rows = []
    for keys, group in pairs.groupby(by, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        diff = group["difference"]
        rows.append({
            **dict(zip(by, keys)),
            "n_pairs": int(len(group)),
            "n_cells": int(group["cell"].nunique()),
            "mean_bias": float(diff.mean()),
            "median_bias": float(diff.median()),
            "mae": float(diff.abs().mean()),
            "rmse": float(np.sqrt((diff ** 2).mean())),
            "pearson_r": _correlation(group["value_a"], group["value_b"], "pearson"),
            "spearman_rho": _correlation(group["value_a"], group["value_b"], "spearman"),
        })
    return pd.DataFrame(rows)


def precipitation_agreement(pairs: pd.DataFrame, by=("source_pair",),
                            threshold_mm: float = WET_DAY_THRESHOLD_MM) -> pd.DataFrame:
    """Wet-day agreement and accumulated-total differences for daily precipitation.

    Wet day: value >= ``threshold_mm``. Accumulations are summed per S2 cell
    over the days on which *both* sources have a value, so a gap in one source
    cannot masquerade as a difference in totals.
    """
    precip = pairs[pairs["variable"] == "precipitation"]
    by = list(by)
    rows = []
    for keys, group in precip.groupby(by, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        wet_a = group["value_a"] >= threshold_mm
        wet_b = group["value_b"] >= threshold_mm
        both_wet = int((wet_a & wet_b).sum())
        only_a = int((wet_a & ~wet_b).sum())
        only_b = int((~wet_a & wet_b).sum())
        both_dry = int((~wet_a & ~wet_b).sum())
        n = len(group)
        observed = (both_wet + both_dry) / n if n else np.nan
        expected = (
            ((both_wet + only_a) * (both_wet + only_b) + (both_dry + only_b) * (both_dry + only_a))
            / n ** 2 if n else np.nan
        )
        totals = group.groupby("cell")[["value_a", "value_b"]].sum()
        relative = (totals["value_a"] - totals["value_b"]) / totals["value_b"].where(totals["value_b"] > 0)
        rows.append({
            **dict(zip(by, keys)),
            "n_pairs": n,
            "wet_threshold_mm": threshold_mm,
            "both_wet": both_wet, "wet_only_a": only_a, "wet_only_b": only_b, "both_dry": both_dry,
            "wet_day_agreement": observed,
            "wet_day_kappa": (
                (observed - expected) / (1 - expected) if n and expected < 1 else np.nan
            ),
            "total_a_mm": float(totals["value_a"].sum()),
            "total_b_mm": float(totals["value_b"].sum()),
            "median_cell_accumulation_difference_mm": float(
                (totals["value_a"] - totals["value_b"]).median()
            ),
            "median_cell_relative_accumulation_difference": (
                float(relative.median()) if relative.notna().any() else np.nan
            ),
            "cells": int(len(totals)),
        })
    return pd.DataFrame(rows)
