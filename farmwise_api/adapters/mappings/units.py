"""Shared output conventions for quantities reported by several sources.

Groundwater level
-----------------
Every source that reports the elevation of the groundwater table returns it in
one column, ``GROUNDWATER_LEVEL_COLUMN``: metres, positive upwards, relative to
the source's national vertical datum (mean sea level as realised by that
datum). Sharing the column name lets harmonisation combine the sources.

The datums are not converted to a common European one:

* EPA Ireland - Ordnance Datum Malin (OSGM02), as stated in each export header
* Hub'Eau / ADES, France - "cote NGF", per the Hub'Eau API field description
* CORRECTIV, Germany - "metres above sea level" as compiled from the German
  state authorities; the specific datum is not stated in the published data

National datums are each tied to a different tide gauge, so absolute levels are
not exactly comparable across borders. A correct conversion needs the datum and
a height transformation per point, which FARMWISE does not ship; the datum is
therefore recorded per source in the registry instead of being converted.

Depth-type measurements are *not* groundwater levels and are kept separate:
a depth below ground cannot be turned into an elevation without the ground
elevation at the monitoring point.
"""

GROUNDWATER_LEVEL_COLUMN = "Groundwater level [m a.s.l.]"

__all__ = ["GROUNDWATER_LEVEL_COLUMN"]
