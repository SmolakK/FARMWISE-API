#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .hubeau import *
from .wrappers import *

__version__ = '0.1.0'


WRAPPERS = {
    'piezometry': HubPiezometrie,
    'hydrometry': HubHydrometrie,
    'withdrawal': HubPrelevements,
    'groundwater_qual': HubQualSout,
    'river_qual' : HubQualRiv,
    # 'river_temperature': HubTemperRiv,
    # 'river_drought': HubOnde,
    # 'drinking_quality': HubQualAEP,
    # 'services': HubServices,
    # 'coastal': HubLittoral,
    # 'fish': HubFish,
}


def init_api(api='piezometry', version=1):
    """ HubEau class accessor, instancies a wrapper class for any api
    methods get_station(), get_data(), [get_data_tr()]
    """
    # interface for instancing wrapper class. Simplier than Multiple Heritage
    if not api.lower() in list(API.keys()):
        raise ValueError(
            'API `{}` is not available. Please use one of the following: {} or use HubeauUtils to construct your API request'.format(
                api, ', '.join(list(API.keys()))
            )
        )
    _api = WRAPPERS.get(api.lower())
    return _api(version=version)
