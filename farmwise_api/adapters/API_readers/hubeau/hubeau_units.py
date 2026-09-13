"""Per-result unit validation and conversion for Hub'Eau water-quality data.

Hub'Eau reports the unit of every analytical result separately
(``symbole_unite``), and one SANDRE parameter can arrive in several units.
Sampled live on 2026-09-13, river nitrate came as mg(NO3)/L, mg(N)/L, mg/L,
mg(CO3)/L and µg/L; river arsenic as µg(As)/L, µg/L, mg(As)/L and, from
sediment fractions, mg(As)/kg; groundwater total phosphorus as mg(P)/L and
mg(P2O5)/L. Averaging those values under one label changes what the numbers
mean, so every result is converted to the parameter's declared output unit
before any aggregation, and a result that cannot be converted without guessing
is dropped and counted rather than passed through.

The same applies to the analysed fraction: dissolved (filtered), raw-water
and unspecified-water results are different quantities for particle-bound
species, so they are kept in separate output columns. Non-water matrices
(sediment, suspended matter) and results of unknown fraction are dropped.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

# Molar masses (g/mol), IUPAC 2021 standard atomic weights.
_N = 14.007
_O = 15.999
_P = 30.974
NITRATE_PER_NITROGEN = (_N + 3 * _O) / _N  # mg(NO3) per mg(N)
PHOSPHORUS_PER_P2O5 = (2 * _P) / (2 * _P + 5 * _O)  # mg(P) per mg(P2O5)

# SANDRE parameter code -> (English name, output unit). The unit names the
# chemical form the value is expressed as, e.g. nitrate as NO3, not as N.
PARAMETERS: dict[str, tuple[str, str]] = {
    "1302": ("Hydrogen potential", "pH units"),
    "1303": ("Conductivity at 25°C", "µS/cm"),
    "1337": ("Chlorides", "mg(Cl)/L"),
    "1340": ("Nitrates", "mg(NO3)/L"),
    "1350": ("Total phosphorus", "mg(P)/L"),
    "1367": ("Potassium", "mg(K)/L"),
    "1369": ("Arsenic", "µg(As)/L"),
    "1372": ("Magnesium", "mg(Mg)/L"),
    "1374": ("Calcium", "mg(Ca)/L"),
    "1375": ("Sodium", "mg(Na)/L"),
    "1382": ("Lead", "µg(Pb)/L"),
    "1383": ("Zinc", "µg(Zn)/L"),
    "1388": ("Cadmium", "µg(Cd)/L"),
    "5347": ("Perfluorooctanoic acid (PFOA)", "µg/L"),
    "5977": ("Perfluoroheptanoic acid (PFHpA)", "µg/L"),
    "5978": ("Perfluorohexanoic acid (PFHxA)", "µg/L"),
    "5979": ("Perfluoropentanoic acid (PFPeA)", "µg/L"),
    "5980": ("Perfluorobutanoic acid (PFBA)", "µg/L"),
    "6025": ("Perfluorobutane sulfonic acid (PFBS)", "µg/L"),
    "6276": ("Total pesticides", "µg/L"),
    "6507": ("Perfluorododecanoic acid (PFDoA)", "µg/L"),
    "6508": ("Perfluorononanoic acid (PFNA)", "µg/L"),
    "6509": ("Perfluorodecanoic acid (PFDA)", "µg/L"),
    "6510": ("Perfluoroundecanoic acid (PFUnA)", "µg/L"),
    "6542": ("Perfluoroheptane sulfonic acid (PFHpS)", "µg/L"),
    "6549": ("Perfluorotridecanoic acid (PFTrDA)", "µg/L"),
    "6550": ("Perfluorodecane sulfonic acid (PFDS)", "µg/L"),
    "6560": ("Perfluorooctane sulfonic acid (PFOS, SANDRE 6560)", "µg/L"),
    "6561": ("Perfluorooctane sulfonate (PFOS, SANDRE 6561)", "µg/L"),
    "6830": ("Perfluorohexane sulfonic acid (PFHxS)", "µg/L"),
    "8738": ("Perfluoropentane sulfonic acid (PFPeS)", "µg/L"),
    "8739": ("Perfluorononane sulfonic acid (PFNS)", "µg/L"),
    "8740": ("Perfluoroundecane sulfonic acid (PFUnDS)", "µg/L"),
    "8741": ("Perfluorododecane sulfonic acid (PFDoDS)", "µg/L"),
    "8742": ("Perfluorotridecane sulfonic acid (PFTrDS)", "µg/L"),
}

# Stoichiometric conversions between explicitly stated chemical forms:
# (parameter code, reported basis) -> factor to the output basis.
BASIS_CONVERSIONS: dict[tuple[str, str], float] = {
    ("1340", "N"): NITRATE_PER_NITROGEN,
    ("1350", "P2O5"): PHOSPHORUS_PER_P2O5,
}

# SANDRE water fractions kept, each as its own output column.
FRACTIONS: dict[str, str] = {
    "3": "dissolved",
    "23": "raw water",
    "22": "water, fraction unspecified",
}

_MASS_IN_UG = {"ng": 1e-3, "µg": 1.0, "mg": 1e3, "g": 1e6}
_CONCENTRATION = re.compile(r"(ng|µg|mg|g)(?:\(([^)]*)\))?/[lL]")
# Parameters whose mass can only be expressed as the element itself, so a
# unit without a stated form (mg/L, µg/L) is not ambiguous.
BARE_UNIT_IS_UNAMBIGUOUS = frozenset(
    {"1337", "1367", "1369", "1372", "1374", "1375", "1382", "1383", "1388"}
)


@dataclass(frozen=True)
class Conversion:
    """Outcome for one (parameter, reported unit) pair."""
    factor: float | None
    reason: str | None = None  # why the result is rejected, if it is


def sampling_day(values: pd.Series) -> pd.Series:
    """Calendar day of each sample in French local time, as naive timestamps.

    Hub'Eau returns sampling times such as '2015-03-02T11:00:00Z'. Keeping the
    time made two samples from one day separate rows, and the adapters' later
    daily resample kept only the first of them.
    """
    stamps = pd.to_datetime(values, format="ISO8601")
    if stamps.dt.tz is not None:
        stamps = stamps.dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    return stamps.dt.normalize()


def output_label(prefix: str, code: str, fraction: str) -> str:
    """Column label for a parameter and fraction, ending in its output unit."""
    name, unit = PARAMETERS[code]
    return f"{prefix} {name} ({FRACTIONS[fraction]}) [{unit}]"


def output_labels(prefix: str) -> dict[str, str]:
    """Every possible output label, keyed by 'SANDRE code:fraction code'."""
    return {
        f"{code}:{fraction}": output_label(prefix, code, fraction)
        for code in PARAMETERS
        for fraction in FRACTIONS
    }


def _clean(symbol: str) -> str:
    # Hub'Eau uses both MICRO SIGN (U+00B5) and GREEK SMALL LETTER MU (U+03BC).
    return symbol.strip().replace("μ", "µ").replace(" ", "")


def _parse_concentration(symbol: str) -> tuple[float, str | None] | None:
    """Return (mass factor to µg, chemical basis or None) for a '<mass>(<basis>)/L' unit."""
    match = _CONCENTRATION.fullmatch(_clean(symbol))
    if not match:
        return None
    basis = match.group(2)
    if basis is not None:
        basis = basis.rstrip("+-") or None
    return _MASS_IN_UG[match.group(1)], basis


def conversion(code: str, symbol) -> Conversion:
    """How a result of parameter `code` reported in unit `symbol` is converted."""
    if code not in PARAMETERS:
        return Conversion(None, "parameter not in the FARMWISE table")
    if symbol is None or (isinstance(symbol, float) and pd.isna(symbol)):
        return Conversion(None, "no unit reported")
    symbol = str(symbol).strip()
    _name, target = PARAMETERS[code]

    if target == "pH units":
        ok = symbol.lower() in {"unité ph", "unite ph", "ph"}
        return Conversion(1.0) if ok else Conversion(None, f"'{symbol}' is not a pH unit")
    if target == "µS/cm":
        scale = {"µS/cm": 1.0, "mS/cm": 1e3}.get(_clean(symbol))
        return Conversion(scale) if scale else Conversion(None, f"'{symbol}' is not a conductivity unit")

    reported = _parse_concentration(symbol)
    wanted = _parse_concentration(target)
    assert wanted is not None, target
    if reported is None:
        return Conversion(None, f"'{symbol}' is not a mass concentration per litre")
    reported_scale, reported_basis = reported
    wanted_scale, wanted_basis = wanted
    scale = reported_scale / wanted_scale

    if reported_basis == wanted_basis:
        return Conversion(scale)
    if reported_basis is None:
        # A bare mg/L is accepted only where the form cannot differ: arsenic
        # in mg/L can only be mg of As. Nitrate (as N or NO3) and phosphorus
        # (as P, PO4 or P2O5) are routinely reported in several forms.
        if wanted_basis is None or code in BARE_UNIT_IS_UNAMBIGUOUS:
            return Conversion(scale)
        return Conversion(None, f"'{symbol}' does not state the chemical form")
    factor = BASIS_CONVERSIONS.get((code, reported_basis))
    if factor is not None:
        return Conversion(scale * factor)
    return Conversion(None, f"'{symbol}' is expressed as {reported_basis}, not {wanted_basis}")


def normalise_results(
    df: pd.DataFrame,
    *,
    prefix: str,
    code_column: str = "code_param",
    unit_column: str = "symbole_unite",
    fraction_column: str = "code_fraction",
    value_column: str = "resultat",
    label_column: str = "parameter",
) -> tuple[pd.DataFrame, dict]:
    """Convert every result to its output unit and label it by parameter and fraction.

    Returns the kept rows, with ``value_column`` converted and ``label_column``
    added, and a report of how many results were converted and why the others
    were dropped.
    """
    frame = df.copy()
    codes = frame[code_column].astype(str).str.strip()
    fractions = (
        pd.to_numeric(frame[fraction_column], errors="coerce").astype("Int64").astype(str)
        if fraction_column in frame.columns
        else pd.Series("<missing>", index=frame.index)
    )

    cache: dict[tuple[str, object], Conversion] = {}
    factors = []
    reasons = []
    for code, symbol, fraction in zip(codes, frame[unit_column], fractions):
        key = (code, symbol)
        if key not in cache:
            cache[key] = conversion(code, symbol)
        result = cache[key]
        if result.factor is not None and fraction not in FRACTIONS:
            result = Conversion(None, f"fraction {fraction} is not a kept water fraction")
        factors.append(result.factor)
        reasons.append(result.reason)

    frame["_factor"] = pd.to_numeric(pd.Series(factors, index=frame.index), errors="coerce")
    keep = frame["_factor"].notna()
    rejected = Counter(
        (code, str(symbol), reason)
        for code, symbol, reason, kept in zip(codes, frame[unit_column], reasons, keep)
        if not kept
    )
    converted = Counter(
        (code, str(symbol))
        for code, symbol, factor, kept in zip(codes, frame[unit_column], frame["_factor"], keep)
        if kept and factor != 1.0
    )

    kept_frame = frame.loc[keep].copy()
    kept_frame[value_column] = pd.to_numeric(kept_frame[value_column], errors="coerce") * kept_frame["_factor"]
    kept_frame[label_column] = [
        output_label(prefix, code, fraction)
        for code, fraction in zip(codes[keep], fractions[keep])
    ]
    kept_frame = kept_frame.drop(columns="_factor")

    report = {
        "results_received": int(len(frame)),
        "results_kept": int(keep.sum()),
        "results_converted": {f"{c} [{s}]": n for (c, s), n in sorted(converted.items())},
        "results_dropped": {f"{c} [{s}]: {r}": n for (c, s, r), n in sorted(rejected.items())},
    }
    if rejected:
        logger.warning(
            "Hub'Eau: dropped %s of %s results whose unit or fraction could not be "
            "converted without guessing: %s",
            sum(rejected.values()), len(frame), report["results_dropped"],
        )
    return kept_frame, report
