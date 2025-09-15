#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from .hubeau import _AbstractHub, DEFAULT_PARAMS

class HubPiezometrie(_AbstractHub):
    
    def __init__(self, **kwargs):
        super().__init__('piezometry', **kwargs)

    def get_station(
        self, bbox=None,
        srid=4326,
        code_station=None,
        bss_id=None,
        code_bdlisa=None,
        code_departement=None,
        code_commune=None,
        nb_mesures_min=None,
        date_active=None,
        **parameters
    ):
        
        return self._get_station(
            code_bss=code_station, bss_id=bss_id, bbox=bbox, srid=srid, code_bdlisa=code_bdlisa,
            code_commune=code_commune, code_departement=code_departement,
            nb_mesures_piezo_min=nb_mesures_min, date_recherche=date_active,
            **parameters
        )
    

    def get_data(self,
        code_station,
        start_date=None,
        end_date=None,
        only_valid_data=True,
        add_real_time=True,
        verbose=False
    ):
        """
        Wrapper function to get data from HubEau's piezometry API
        """
        params = dict(
            code_bss=code_station,
            date_debut_mesure=start_date,
            date_fin_mesure=end_date,
            **DEFAULT_PARAMS,
        )
        
        df = self._get_consolidated_and_realtime_data(
            fields=['date_mesure', 'niveau_nappe_eau'],
            labels=['date', 'value'],
            fields_tr=['date_mesure', 'niveau_eau_ngf'],
            labels_tr=['date', 'value'],
            only_valid_data=only_valid_data,
            add_real_time=add_real_time,
            agg_tr='max', # Daily max to convert hourly to daily piezometric data
            params_tr=dict(
                code_bss=code_station,
            ),
            **params
        )
        
        if not df.empty:
            df.index = df.index.set_levels(df.index.levels[1].str.slice(0,10), level=1) # 1st level is code_bss, only keep relevant char
        
        return df



class HubHydrometrie(_AbstractHub):
    
    def __init__(self, **kwargs):
        super().__init__('hydrometry', **kwargs)
    
    def get_station(
        self,
        code_station=None,
        bbox=None,
        srid=4326,
        code_departement=None,
        **parameters
    ):
        # for hydrometry, station api size limit is 10_000 and not 20_000
        if 'size' in parameters.keys():
            parameters.pop("size")

        if code_station is not None:
            _test = code_station if isinstance(code_station, str) else code_station[0]
            code_name = 'code_site' if len(_test) <= 8 else 'code_station'
            parameters = {**parameters, **{code_name: code_station}}

        return self._get_station(
            # code_station=code_station,
            # code_site=code_site,
            bbox=bbox,
            srid=srid,
            code_departement=code_departement,
            size=10_000,
            **parameters
        )
    

    def get_data(
        self,
        code_station,
        start_date=None,
        end_date=None,
        type_obs='QmJ',
        only_valid_data=True,
        add_real_time=True,
        factor=1e+3,
        verbose=False
    ):
        """
        Wrapper function to get data from HubEau's hydrometry API
        """
        params = dict(
            code_entite=code_station,
            grandeur_hydro_elab=type_obs,
            date_debut_obs_elab=start_date,
            date_fin_obs_elab=end_date,
            **DEFAULT_PARAMS,
        )
        df = self._get_consolidated_and_realtime_data(
            fields=['date_obs_elab', 'resultat_obs_elab'],
            labels=['date', 'value'],
            fields_tr=['date_obs', 'resultat_obs'],
            labels_tr=['date', 'value'],
            only_valid_data=only_valid_data,
            add_real_time=add_real_time,
            agg_tr='mean',
            params_tr=dict(
                code_entite=code_station,
                grandeur_hydro=type_obs[0], # only 'Q' here
            ),
            **params
        )
        if not df.empty:
            df['value'] /= factor # L/s to m3/s
        
        return df


class HubPrelevements(_AbstractHub):
    
    def __init__(self, **kwargs):
        super().__init__('withdrawal', **kwargs)
    
    @staticmethod
    def _set_code_station_in_parameters(code_station, params={}):
        _test = code_station if isinstance(code_station, str) else code_station[0]
        if _test.startswith('OPR'):
            kwargs = {**{'code_ouvrage': code_station}, **params}
        elif _test.startswith('PTP'):
            kwargs = {**{'code_point_prelevement': code_station}, **params}
        return kwargs
    
    def get_station(self, code_station=None, code_dep=None, code_commune=None, **kwargs):
        
        kwargs = self._set_code_station_in_parameters(code_station, kwargs)

        return self._get_station(
            code_departement=code_dep,
            code_commune_insee=code_commune,
            **kwargs
        )
    
    def get_data(self, **kwargs):
        # set uniform `code_station` for user, then parse in code_point_prelevement or code_ouvrage
        codes = [ x for x in kwargs.keys() if re.match('code_*', x)]
        if any(codes):
            kwargs = self._set_code_station_in_parameters(kwargs.get(codes[0]), kwargs)

        return self._get_data(
            #fields=['annee', 'code_ouvrage', 'volume']
            date_fmt='%Y',
            **kwargs
        )



class HubQualRiv(_AbstractHub):
    
    def __init__(self, **kwargs):
        super().__init__('river_qual', **kwargs)
    
    def get_station(self, **kwargs):
        return self._get_station(**kwargs)
    
    def get_data(self, **kwargs):
        return self._get_data(**kwargs)


class HubQualSout(_AbstractHub):
    
    def __init__(self, **kwargs):
        super().__init__('groundwater_qual', **kwargs)

    def get_station(self, code_station=None, **kwargs):
        return self._get_station(bss_id=code_station, **kwargs)
    
    def get_data(self, code_station=None, **kwargs):
        """
        bss_id in API allow old and new "code_bss"
        """
        return self._get_data(bss_id=code_station, **kwargs)

   
# class HubQualAEP(_AbstractHub):
#     
#     def __init__(self, **kwargs):
#         super().__init__('', **kwargs)
#         print('Wrapper not yet available. Please construct request with HubeauUtils.get_data()')
# 
#     def get_station(self, **kwargs):
#         return self._get_station(**kwargs)
#     
#     def get_data(self, **kwargs):
#         return self._get_data(**kwargs)
# 


# class HubOnde(_AbstractHub):
#     
#     def __init__(self, **kwargs):
#         super().__init__('river_drought', **kwargs)
#         print('Wrapper not yet available. Please construct request with HubeauUtils.get_data()')
# 
#     def get_station(self, **kwargs):
#         return self._get_station(**kwargs)
#     
#     def get_data(self, **kwargs):
#         return self._get_data(**kwargs)
# 
# 
# 
# class HubTemperRiv(_AbstractHub):
#     
#     def __init__(self, **kwargs):
#         super().__init__('river_temperature', **kwargs)
#         print('Wrapper not yet available. Please construct request with HubeauUtils.get_data()')
# 
#     def get_station(self, **kwargs):
#         return self._get_station(**kwargs)
#     
#     def get_data(self, **kwargs):
#         return self._get_data(**kwargs)
# 
# 
# 
# class HubLittoral(_AbstractHub):
#     
#     def __init__(self, **kwargs):
#         super().__init__('', **kwargs)
#         print('Wrapper not yet available. Please construct request with HubeauUtils.get_data()')
# 
#     def get_station(self, **kwargs):
#         return self._get_station(**kwargs)
#     
#     def get_data(self, **kwargs):
#         return self._get_data(**kwargs)
# 
# 
# 
# class HubServices(_AbstractHub):
#     
#     def __init__(self, **kwargs):
#         super().__init__('', **kwargs)
#         print('Wrapper not yet available. Please construct request with HubeauUtils.get_data()')
# 
#     def get_station(self, **kwargs):
#         return self._get_station(**kwargs)
#     
#     def get_data(self, **kwargs):
#         return self._get_data(**kwargs)
# 
# 
# 
# class HubFish(_AbstractHub):
#     
#     def __init__(self, **kwargs):
#         super().__init__('', **kwargs)
#         print('Wrapper not yet available. Please construct request with HubeauUtils.get_data()')
# 
#     def get_station(self, **kwargs):
#         return self._get_station(**kwargs)
#     
#     def get_data(self, **kwargs):
#         return self._get_data(**kwargs)
# 
