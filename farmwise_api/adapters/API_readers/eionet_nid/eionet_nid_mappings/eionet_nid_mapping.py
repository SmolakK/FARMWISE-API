"""Column mappings for the Eionet CDR Nitrates Directive groundwater adapter."""

DATA_ALIASES = {
    'ND_AvgAnnValue': 'groundwater quality',
    'ND_MaxValue': 'groundwater quality',
    'ND_TrendValue': 'groundwater quality',
    'ND_NoOfSamples': 'groundwater quality',
}

# Units come from the Eionet data dictionary (table 7761), which makes mg/L NO3
# mandatory for every concentration. ND_TrendValue is defined there as
# "average current reporting period - average previous reporting period", so it
# is a difference between two four-year means, not an annual slope.
#
# Labels are deliberately distinct from the Hub'Eau ones, which use
# "GW Nitrates (mg/L)" for individual samples, to keep harmonization from
# averaging a four-year mean together with a single measurement.
GLOBAL_MAPPING = {
    'ND_AvgAnnValue': 'GW Nitrates Annual Mean (mg/L NO3)',
    'ND_MaxValue': 'GW Nitrates Max (mg/L NO3)',
    'ND_TrendValue': 'GW Nitrates Trend (mg/L NO3)',
    'ND_NoOfSamples': 'GW Nitrates Sample Count',
}
