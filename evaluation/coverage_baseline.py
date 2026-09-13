"""Factor-only routing baseline for the coverage pre-check experiment.

FARMWISE decides which adapters to call with ``plan_source_dispatch``: a source
is dispatched only if it is enabled, provides a requested factor, and its
registry entry overlaps the request in space and time. The baseline answers
the counterfactual question "what if the spatial and temporal metadata were
not used?": every enabled source that provides a requested factor is called.

Disabled sources (licensing, broken upstream) stay disabled in the baseline.
Removing that check would measure a different thing - and, for IMGW and
CORRECTIV, would contact sources FARMWISE is not permitted to use.

The swap is made on the name ``read_data`` looks up at call time, only for the
duration of the ``with`` block, and only inside the evaluation process; the
library itself is not modified.
"""

from __future__ import annotations

from contextlib import contextmanager

from farmwise_api.core import main_call


def factor_eligible(decision: dict) -> bool:
    """Whether factor-only routing would dispatch this source."""
    return bool(not decision["disabled_reason"] and decision["factor_overlap"])


def coverage_counts(plan: list[dict]) -> dict:
    """Candidate/dispatch counts for a pre-check plan, with the baseline for comparison.

    ``requests_avoided_vs_factor_only`` is the number of adapter calls the
    pre-check saves relative to factor-only routing: enabled sources that
    provide a requested factor but do not overlap in space or time.
    """
    enabled = [d for d in plan if not d["disabled_reason"]]
    factor_only = [d for d in plan if factor_eligible(d)]
    dispatched = [d for d in plan if d["dispatched"]]
    return {
        "configured_sources": len(plan),
        "enabled_sources": len(enabled),
        "factor_eligible_sources": len(factor_only),
        "precheck_dispatched_sources": len(dispatched),
        "requests_avoided_vs_factor_only": len(factor_only) - len(dispatched),
        "rejected_spatial": sum(
            1 for d in factor_only if not d["spatial_overlap"]
        ),
        "rejected_temporal": sum(
            1 for d in factor_only if not d["temporal_overlap"]
        ),
    }


@contextmanager
def factor_only_routing():
    """Within the block, ``read_data`` dispatches without the coverage check."""
    original = main_call.plan_source_dispatch

    def plan_without_coverage(*args, **kwargs):
        plan = original(*args, **kwargs)
        return [{**decision, "dispatched": factor_eligible(decision)} for decision in plan]

    main_call.plan_source_dispatch = plan_without_coverage
    try:
        yield
    finally:
        main_call.plan_source_dispatch = original
