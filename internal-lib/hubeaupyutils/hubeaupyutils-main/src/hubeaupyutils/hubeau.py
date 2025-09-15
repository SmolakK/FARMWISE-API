#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HubeauUtils

Fonctions collection intended do:
- pipe parameters to proper format for requesting
- to fetch data from Hub'eau APIS
- pipe the data to pandas dataframe
- operate transformations on data
"""

import re
import requests
import pandas as pd

from datetime import datetime, timedelta
from numpy import ndarray


DEFAULT_PARAMS = {
    'size': 20_000,
    'sort': 'asc',
}

RESPONSE_CODE = {
    # Response code - For memory
    200 : 'OK, all results fetched',
    206 : 'OK, but results remains',
    400 : 'Wrong request',
    401 : 'Unauthorized',
    403 : 'Forbidden',
    404 : 'Not Found',
    500 : 'Server internal error',
}


API = {
    'piezometry': {
        'endpoint': 'niveaux_nappes',
        'operator_sta': 'stations',
        'operator_obs': 'chroniques',
        'operator_tr' : 'chroniques_tr'
    },
    'hydrometry': {
        'endpoint': 'hydrometrie',
        'operator_sta': 'referentiel/stations',
        'operator_obs': 'obs_elab', # observationsElaborees
        'operator_tr' : 'observations_tr'
    },
    'withdrawal': {
        'endpoint' : 'prelevements',
        'operator_sta' : 'referentiel/points_prelevement',
        'operator_obs' : 'chroniques',
        'operator_tr'  :  None,
    },
    'groundwater_qual': {
        'endpoint': 'qualite_nappes',
        'operator_sta' : 'stations',
        'operator_obs' : 'analyses',
        'operator_tr'  : None,
    },
    'river_qual' : {
        'endpoint': 'qualite_rivieres',
        'operator_sta' : 'station_pc',
        'operator_obs' : 'analyse_pc'
    },
    'river_temperature': {
        'endpoint': 'temperature',
        'operator_sta' : 'station',
        'operator_obs' : 'chronique'
    },
    'river_drought': {
        'endpoint': 'ecoulement', #réseau ONDE in french
        'operator_sta' : 'stations',
        'operator_obs' : 'observations'
        # 'operator_tr'  : 'campagnes' # not tr, add another ?
    }
}


def get_api_description(api='piezometry'):
    if not api.lower() in list(API.keys()):
        raise ValueError(
            'API `{}` is not available. Please use one of the following: {}'.format(
                api, ', '.join(list(API.keys()))
            )
        )
    return API.get(api)


def _check_parameters(**kwargs):
    """ Filter/clean kwargs for requests parameters """
    kwargs = {k: join_list(v) if isinstance(v, (list, tuple, pd.Series, ndarray)) else v for k, v in kwargs.items()} # list as str
    kwargs['size'] = min(kwargs.get('size', 20_000), 20_000) # 20_000 is the max allowed
    kwargs = {k: v for k, v in kwargs.items() if v} # remove False or None values
    return kwargs


def join_list(values, ascii=False):
    if ascii:
        return "%2C".join(map(str, values))
    else:
        return ",".join(map(str, values))


def _session_timeout(url, sec=10):
    """ block request after x seconds 
    not used now --> __future__
    """
    try:
        session = requests.get(url, timeout=sec)
    except requests.exceptions.Timeout:
        session.ok = False
    return session



# TODO change to _get_json_data from Thib ?
# simplier, and nice recursive implementation
def _get_json_data(url: str, data: list) -> list:
    r = requests.get(url)

    if r.status_code == 200:
        data.extend(r.json()['data'])
        return data
    elif r.status_code == 206:
        data.extend(r.json()['data'])
        if r.json()['next']:
            return _get_json_data(r.json()['next'], data)
        else:
            # catch edge case (bug?) where return code is 206 (i.e.
            # remaining data to be fetched) but next URL is None (e.g.
            # this is the case for https://hubeau.eaufrance.fr/api/
            # v1/prelevements/referentiel/points_prelevement?
            # code_departement=40&page=2&size=10000)
            return data
    else:
        raise RuntimeError(
            f"data retrieval failed for query with URL {url}"
        )



def _curl_api(url, params={}, verbose=False):
    """
    Get request from an url
    using requests module and some parameters the API of an url is
    requested. Data (answer) are added according to status of response.

    Parameters
    ----------
    url: str, the url to request
    params: dict, parameters passed to `requests` method. Must match the API parameters of requested `url`.
    verbose: bool, option to print details about errors.

    Returns
    ------
    get: raw answer
    data: the data fetched from API

    """
    
    answ    = requests.get(url, params=params)
    url_req = answ.url
    
    if verbose:
        print(f'Requesting: {url_req}')
    
    status_code = answ.status_code
    data = []
    
    if status_code in [200, 206]:
        
        if status_code == 200:
            data.append(answ.json()['data'])
        
        while status_code == 206:
            if verbose:
                print('code_206, more results')
            data.append(answ.json()['data'])
            
            if answ.json()['next'] is not None:
                next_url = answ.json()['next']
                if verbose:
                    print(f'url next : {next_url}')
                answ = requests.get(next_url)
                status_code = answ.status_code
                if status_code not in [200, 206]:
                    if verbose:
                        print(f'Error code: {status_code}, reason:\n{answ.reason}')
                        print(f'parameters used : {params}')
                    if status_code == 400 and verbose:
                        print('Total size limit might have been reached. (20 000 data).',
                              f'Possible solution : request with more parameters to cut the answer in smaller pieces.\n{answ.json()}')
                        print(f'Allready fetch data size : {sum([len(e) for e in data])} in {len(data)} element in list')
            else:
                # status was 206 but no next page
                status_code = 200
                if verbose:
                    print(status_code)
    else:
        # 1st code is not 200,206
        print(f'Error code: {status_code},\n url = {url_req}')
        try:
            print(f'reason:\n{answ.reason}\n{answ.json()}')
        except requests.JSONDecodeError:
            pass

    return answ, data



class HubeauUtils:
    """
    HubeauUtils
    -----------
    Generic object to request Hubeau'API endpoints.
    """
    
    def __init__(self, endpoint='niveaux_nappes', operator='chroniques', version=1):

        self.hubeau_url   = "https://hubeau.eaufrance.fr/api/v{}/".format(version)
        self.doc_operator = "api-docs"
        
        self._endpoint    = endpoint
        self._operator    = operator

        if operator.endswith('.csv'):
            raise ValueError('csv format request is not yet implemented. Please use json operator')
    
        self.all_endpoints = [
            # default, can be reset with setter func
            "qualite_nappes",
            "niveaux_nappes",
            "qualite_rivieres",
            "temperature",
            "hydrometrie",
            "prelevements",
        ]

    @property
    def endpoint(self): # getter
        return self._endpoint
    @endpoint.setter
    def endpoint(self, endpoint: str):
        self._endpoint = endpoint
    
    @property
    def operator(self): # getter
        return self._operator
    @operator.setter
    def operator(self, operator: str):
        self._operator = operator


    def get_apis_documentation(self, endpoint: str|None = None)->dict:
        """
        Get documentation for a specific endpoint
        Param:
        endpoint: string. Authorized value : one of the available endpoint given by HubeauUtils.available_endpoints()
        """
        if endpoint is None:
            endpoint = self.endpoint
        if endpoint not in self.all_endpoints:
            raise ValueError(print(f'Parameter {endpoint} is not authorized. Please refer to API\'s documentation.'))
        
        url = f'{self.hubeau_url}/{endpoint}/{self.doc_operator}'
        get_answ = requests.get(url)
        
        if get_answ.status_code in [200]:
            api_doc = get_answ.json()
        else:
            # print('Response Error - the API status code was not 200')
            api_doc = {}
        
        return api_doc
    
    def get_operators(self) -> list:
        """
        Renvoie l'ensemble des opérations possibles pour le endpoint spécifié en paramètre
        Param:
        endpoint: string.
        Authorized value : one of the available endpoint given by HubeauUtils.available_endpoints()
        """
        docu = self.get_apis_documentation(endpoint=self.endpoint)
        available_operators = [
            docu['paths'][k]['get']['operationId'].replace(' csv','.csv') \
            for k in docu['paths'].keys()
        ]
        return available_operators

    def get_parameters(self, doc=None, operator=None, name_only: bool=False) -> dict:
        """
        list the available parameters in the get method for a specific operator
        in the selected endpoint
        """
        if doc is None:
            doc = self.get_apis_documentation()
        if operator is None:
            operator = self.operator
        params = [
            doc['paths'][key]['get']['parameters'] for key in doc['paths'].keys() \
            if key.endswith(operator)
        ]
        if name_only:
            params = [elem['name'] for elem in params[0]]
        return params

    def get_from_api(
        self,
        parameters: dict={'size':200},
        operator=None,
        verbose: bool=False,
        return_type='pandas',
        debug=False
    ):
        """
        This fonction is used to send request to hubeau and get results as
        json or pandas.DataFrame
        
        Parameters
        ----------
        parameters: dict
            e.g : size: size of the page
                  bbox=str, need to be in format 'long_min,lat_min,long_max,lat_max'
                  srid=int, e.g 4326
        
        operator: str, Optionnal.
            the operator to requests. By default, set to the operator chosen at class instanciation.
            Custom value allow to request a different operator of same endpoint, without creating another instance
            of `HubeauUtils`
        
        return_type: str, optionnal. 
            Default is 'pandas'
                    accepted values = 
                    'pandas' (or 'dataframe', return only df),
                    "answer" return answer from requests, data in json, data in pandas.DataFrame
        Returns
        -------
        get answer as provided by requests library,  data in json format, data in pandas dataframe format
        
        """

        if operator is None:
            operator = self.operator
        
        dict_param = _check_parameters(**parameters)
        url = f'{self.hubeau_url}{self.endpoint}/{operator}?'
        
        get, data = _curl_api(url, dict_param, verbose)
        
        if len(data) > 0:
            df = pd.concat([pd.DataFrame.from_dict(elem) for elem in data]) # or pandas.read_json() ?
        else:
            df = pd.DataFrame() # return an empty data.frame to avoid type error if no data
        
        if return_type.lower() in ['pandas', 'dataframe', 'df']:
            return df
        else:
            return get, data, df



class _AbstractHub(HubeauUtils):
    
    def __init__(self, api, version=1):
        self.api_key = api
        self.api = get_api_description(api)
        super().__init__(self.api.get('endpoint'), self.api.get('operator_sta'), version)

    def _get_station(self, verbose=False, **kwargs):
        return self.get_from_api(operator=self.api.get('operator_sta'), verbose=verbose, parameters=kwargs)

    def _get_data(
        self,
        operator=None,
        fields=[],
        labels=[],
        only_valid_data=False,
        date_fmt='%Y-%m-%d',
        freq='D',
        agg_func=None,
        verbose=False,
        **kwargs
    ):
        """ get [consolidated|real-time] data from api
        """
        
        if operator is None:
            operator = self.api.get('operator_obs')
        
        df  = self.get_from_api(operator=operator, parameters=kwargs, verbose=verbose)
        
        if df.empty:
            return df
        
        if only_valid_data:
            df = self._filter_valid_data(df, mode=self.api_key)
        
        if len(fields) > 0:
            df = df.loc[:, fields]
            if len(fields) == len(labels):
                df.columns = labels
        
        df = self._set_date_index(df, date_fmt=date_fmt)
        df = df.sort_index()
        
        if agg_func is not None:
            df = df.resample(freq).agg(agg_func)
        
        return df
    
    
    @staticmethod
    def _filter_valid_data(df, mode: str, verbose=False):
        if mode == 'piezometry':
            df_filter = df.loc[
                # drop wrong/uncertain measures
                (df['qualification'].str.lower() != 'incertaine') & (df['qualification'].str.lower() != 'incorrecte') & 
                # drop dynamic (d) and out of water/dry (s) measures
                (df['code_nature_mesure'].str.lower() != "d") & (df['code_nature_mesure'].str.lower() != "s"), 
                :
            ]
        elif mode == 'hydrometry':
            df_filter = df.loc[
                # Relevant values are `12` ("dubious"),
                # `16` ("correct"), and `20` ("good").
                df['code_qualification'].isin([16, 20]), :
            ]
        else:
            if verbose:
                print('Warning, all data are kept. Filter valid data only available for `piezometry` and `hydrometry` for now.')
            df_filter = df.copy()
        return df_filter
    
    
    @staticmethod
    def _set_date_index(df, date_fmt='%Y-%m-%dT%H:%M:%SZ'):
        col_date = [
            x for x in df.columns \
            if x in ['date', 'date_mesure', 'date_obs_elab', 'date_obs', 'annee', 'date_debut_prelevement', 'date_prelevement']
        ][0]
        # Remarks:
        # * In the 'river_qual' (qualite_rivieres) api, datetime is split into two columns (date_prelevement, heure_prelevement).

        # Dev note by Marc Laurencelle:
        # NOT NECESSARY YET: For most purposes, only the Date part (without time) is used, so xxxxx for now,
        # and yet it may be interesting to exploit the Hour info by improving the disabled code below,
        # that is why it is backed-up here:
                    # # Separated hour info: in 'river_qual' api only:
                    # col_heure = [
                    #     x for x in df.columns \
                    #     if x in ['heure_prelevement']
                    # ][0]
                    # if len(col_heure) == 0:
                    #     datetimedata = df[col_date]
                    # else:
                    #     print("TESTING prep datetimedata:")
                    #     print("TYPE OF df[col_date] =")
                    #     print(df[col_date].dtype)
                    #     print(type(df[col_date]))

                    #     datetimedata = df[col_date] + ' ' + df[col_heure]
                    # df['date']   = pd.to_datetime(datetimedata, format=date_fmt)
        # xxxxx END of disabled block.
        
        df['date']   = pd.to_datetime(df[col_date], format=date_fmt)
        df_timeindex = df.set_index('date')
        if col_date in df_timeindex.columns:
            # case date field was not `date`
            df_timeindex = df_timeindex.drop(col_date, axis=1)
        return df_timeindex
    
    
    @staticmethod
    def _merge_tr(df, df_tr):
        dff = pd.concat([df, df_tr])
        dff = dff[~dff.index.duplicated(keep='first')] # priority on valid data if same index
        return dff
    
    
    def _get_consolidated_and_realtime_data(
        self,
        fields=[], labels=[],
        fields_tr=[], labels_tr=[],
        add_real_time=True,
        agg_tr='mean',
        only_valid_data=True,
        verbose=False,
        params_tr={},
        **params
    ):
        """ Wrapper function to get consolidated and realtime data all at once.
        
        Parameters
        ----------
        
        fields: list of str, Optionnal.
            Fields to keep in consolidated data.
        
        labels: list of str, Optionnal.
            labels to rename fields kept in consolidated data.
        
        fields_tr: list of str, Optionnal.
            Fields to keep in real-time data.
        
        labels_tr: list of str, Optionnal.
            labels to rename fields kept in real-time data.
        
        add_real_time: bool, Optionnal (default is True).
            add real time data or only get consolidated data.
        
        only_valid_data: bool, Optionnal (default is True).
            filter valid data.
            For groundwater : uncertain, incorrect, drougth, pumped data are drop.
            For river discharge: only good, correct and dubious are kept.
        
        agg_tr: str, Optionnal (default is `mean`).
            Function to use to aggregate realtime data from hourly to daily.
            if None is passed, no aggregation is performed.
        
        verbose: bool, Optionnal (default is False).
        
        params_tr: dict, Optionnal.
            additional parameters to pass to `get_data_tr()` (ie real time data).
        
        kwargs:
            any parameters to pass to get_data (ie consolidated data)
        
        Returns
        -------
        pandas.DataFrame with data
        """
        
        code = [x for x in params.keys() if re.match('code.*', x)][0]
        code_station = params.get(code)
        
        df = self._get_data(
            fields=fields,
            labels=labels,
            only_valid_data=only_valid_data,
            verbose=verbose,
            **params
        )

        if df.empty:
            if verbose:
                print('Error while fecthing data, nothing for station : {}'.format(code_station))
                print('Parameters: {}'.format(params))
            last_date = datetime.now() - timedelta(days=93) # max 3 months days in TR API
        else:
            last_date = df.index.max()
        
        # get realtime data
        if add_real_time and last_date < datetime.now():
            df_tr = self._get_data(
                operator=self.api.get('operator_tr'),
                fields=fields_tr,
                labels=labels_tr,
                agg_func=agg_tr,
                date_fmt='%Y-%m-%dT%H:%M:%SZ',
                date_debut_mesure=last_date,
                verbose=verbose,
                **{**DEFAULT_PARAMS, **params_tr}
            )
            if df_tr.empty:
                if verbose:
                    print("No TR values : {}".format(code_station) )
            else:
                df = self._merge_tr(df, df_tr)
        
        if not df.empty:
            df = df.assign(indice=code_station)
            df = df.set_index('indice', append=True)
        else:
            df = pd.DataFrame() # force true empty df if no `valid` data ! otherwise, empty with one col but no mutliindex...
        
        return df


