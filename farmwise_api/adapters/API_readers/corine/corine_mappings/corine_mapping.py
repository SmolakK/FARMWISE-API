"""CORINE Land Cover nomenclature.

The adapter returns the provider's own level-3 class code (the ``Code_YY``
field of the EEA feature layer) unchanged. This module gives those codes their
meaning; it does not alter what ``corine_read.read_data`` returns.

Labels are transcribed from the legend published by the service that supplies
the data:
https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC2018_WM/MapServer/legend

CLC uses a three-level hierarchy encoded in the digits of the code: the first
digit is the level-1 class, the first two digits the level-2 class, and all
three the level-3 class. ``level_1`` and ``level_2`` below therefore derive
from the code rather than being a separate list to keep in step.
"""

from __future__ import annotations

#: Level-3 class code -> label. The complete CLC nomenclature, 44 classes.
CLC_CLASSES: dict[int, str] = {
    111: "Continuous urban fabric",
    112: "Discontinuous urban fabric",
    121: "Industrial or commercial units",
    122: "Road and rail networks and associated land",
    123: "Port areas",
    124: "Airports",
    131: "Mineral extraction sites",
    132: "Dump sites",
    133: "Construction sites",
    141: "Green urban areas",
    142: "Sport and leisure facilities",
    211: "Non-irrigated arable land",
    212: "Permanently irrigated land",
    213: "Rice fields",
    221: "Vineyards",
    222: "Fruit trees and berry plantations",
    223: "Olive groves",
    231: "Pastures",
    241: "Annual crops associated with permanent crops",
    242: "Complex cultivation patterns",
    243: (
        "Land principally occupied by agriculture, with significant areas of "
        "natural vegetation"
    ),
    244: "Agro-forestry areas",
    311: "Broad-leaved forest",
    312: "Coniferous forest",
    313: "Mixed forest",
    321: "Natural grasslands",
    322: "Moors and heathland",
    323: "Sclerophyllous vegetation",
    324: "Transitional woodland-shrub",
    331: "Beaches, dunes, sands",
    332: "Bare rocks",
    333: "Sparsely vegetated areas",
    334: "Burnt areas",
    335: "Glaciers and perpetual snow",
    411: "Inland marshes",
    412: "Peat bogs",
    421: "Salt marshes",
    422: "Salines",
    423: "Intertidal flats",
    511: "Water courses",
    512: "Water bodies",
    521: "Coastal lagoons",
    522: "Estuaries",
    523: "Sea and ocean",
}

#: First digit of the code -> level-1 label.
CLC_LEVEL_1: dict[int, str] = {
    1: "Artificial surfaces",
    2: "Agricultural areas",
    3: "Forest and semi-natural areas",
    4: "Wetlands",
    5: "Water bodies",
}

#: First two digits of the code -> level-2 label.
CLC_LEVEL_2: dict[int, str] = {
    11: "Urban fabric",
    12: "Industrial, commercial and transport units",
    13: "Mine, dump and construction sites",
    14: "Artificial, non-agricultural vegetated areas",
    21: "Arable land",
    22: "Permanent crops",
    23: "Pastures",
    24: "Heterogeneous agricultural areas",
    31: "Forests",
    32: "Scrub and/or herbaceous vegetation associations",
    33: "Open spaces with little or no vegetation",
    41: "Inland wetlands",
    42: "Maritime wetlands",
    51: "Inland waters",
    52: "Marine waters",
}


def describe(code: int | str) -> str | None:
    """Return the level-3 label for a CLC code, or None if unknown."""
    try:
        return CLC_CLASSES.get(int(code))
    except (TypeError, ValueError):
        return None


def level_1(code: int | str) -> str | None:
    """Return the level-1 label for a CLC code, or None if unknown."""
    try:
        return CLC_LEVEL_1.get(int(code) // 100)
    except (TypeError, ValueError):
        return None


def level_2(code: int | str) -> str | None:
    """Return the level-2 label for a CLC code, or None if unknown."""
    try:
        return CLC_LEVEL_2.get(int(code) // 10)
    except (TypeError, ValueError):
        return None


__all__ = [
    "CLC_CLASSES",
    "CLC_LEVEL_1",
    "CLC_LEVEL_2",
    "describe",
    "level_1",
    "level_2",
]
