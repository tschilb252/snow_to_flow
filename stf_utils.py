# -*- coding: utf-8 -*-
"""
Created on Fri Nov 17 14:00:27 2017

@author: Beau.Uriona
"""

import os
import csv
import json
import math
import datetime
import calendar as cal
from datetime import datetime as dt
from datetime import date as date
import pandas as pd
import numpy as np
from zeep import Client
from zeep.transports import Transport
from zeep.cache import InMemoryCache

STATIC_URL = f'https://www.usbr.gov/uc/water/hydrodata/assets'

this_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(os.path.dirname(this_dir), r'static')

def create_awdb():
    wsdl = r'https://wcc.sc.egov.usda.gov/awdbWebService/services?WSDL'
    transport = Transport(timeout=300, cache=InMemoryCache())
    awdb = Client(wsdl=wsdl, transport=transport).service
    return awdb

def isActive(x):
    endDate = dt.strptime(x['endDate'], "%Y-%m-%d %H:%M:%S").date()
    if endDate > dt.today().date():
        return True
    
def isAbove(x,elev):
    if x['elevation'] >= elev:
        return True
    
def isBelow(x,elev):
    if x['elevation'] <= elev:
        return True
    
def isYearsOld(x,yrs):
    s = str(x['beginDate'])
    c = dt.today().year - yrs
    if int(s[:4]) < c:
        return True
    
def get_last_non_zero_index(d, default=366):
    rev = (len(d) - idx for idx, item in enumerate(reversed(d), 1) if item)
    return next(rev, default)

def ordinal(n):
    return "%d%s" % (n,"tsnrhtdd"[(math.floor(n//10)%10!=1)*(n%10<4)*n%10::4])

def fillMissingData(x,daysBack):
    daysBack = -1*daysBack
    if math.isnan(sum(x[daysBack:])) or not x:
        return x
    else:
        if len(x) < daysBack:
            daysBack = len(x)
        if math.isnan(x[-1]):
            x[-1] = [i for i in x if not math.isnan(i)][-1]
        y = x[daysBack:]
        x[:] = (x[:daysBack] + 
         pd.DataFrame(y).interpolate().values.ravel().tolist())
        return x
    
def nonLeapDaysBetween(_sDateLeap,_eDateLeap):
    nonLeapDays = 0    
    if _sDateLeap.month > 2:
        sYear = _sDateLeap.year + 1
    else:
        sYear = _sDateLeap.year
    if _eDateLeap.month < 3:
        eYear = _eDateLeap.year - 1
    else:
        eYear = _eDateLeap.year
    for t in range(sYear,eYear+1):
            if not cal.isleap(t): nonLeapDays += 1    
    return nonLeapDays

def padMissingData(x,_sDate,_eDate):
    if not x['endDate']:
        print(x)
        return None                            
    eDateChkSite = dt.strptime(x['endDate'],"%Y-%m-%d %H:%M:%S").date()
    eDateChkBasin = dt.strptime(_eDate,"%Y-%m-%d").date()
    if eDateChkBasin > eDateChkSite:
        eDiff = ((eDateChkBasin - eDateChkSite).days + 
                 nonLeapDaysBetween(eDateChkSite, eDateChkBasin))
        x['values'] = list(x['values'] + [np.nan]*eDiff)
    sDateChkSite = dt.strptime(
            x['beginDate'],"%Y-%m-%d %H:%M:%S").date()
    sDateChkBasin =dt.strptime(_sDate,"%Y-%m-%d").date()
    if sDateChkBasin < sDateChkSite:
        sDiff = ((sDateChkSite - sDateChkBasin).days + 
                 nonLeapDaysBetween(sDateChkBasin, sDateChkSite))
        x['values'] = list([np.nan]*sDiff + x['values'])
    if sDateChkBasin > sDateChkSite: 
        sDiff = ((sDateChkBasin - sDateChkSite).days + 
                 nonLeapDaysBetween(sDateChkSite,sDateChkBasin))
        x['values'] = list(x['values'][sDiff:])
    return x  

def getBasinSites(basinName,basinTable):
    siteListStr = basinTable.get(basinName).get(r'BasinSites')
    siteList = []
    if siteListStr:
        siteList = siteListStr.split(r';')
    if siteList:
        return siteList
    
def getBasinTable():
    delimiter = ','
    basinTable = {}
    with open(os.path.join(static_dir,'basinDef.csv'), 'r') as data_file:
        data = csv.reader(data_file, delimiter=delimiter)
        headers = next(data)[1:]
        for row in data:
            temp_dict = {}
            name = row[0]
            while name in basinTable:
                name = name + '\u0080'
            values = []
            for x in row[1:]:
                values.append(x)
            for i in range(len(values)):
                temp_dict[headers[i]] = values[i]
            basinTable[name] = temp_dict
    return basinTable

def getGeoData(hucList):
    geoData = {'type' : 'FeatureCollection', 'features' : []}
    equalLength = False
    if all(len(i) == len(hucList[0]) for i in hucList):
        equalLength = True
        hucLength = str(len(hucList[0]))
        geojson_path = (os.path.join(static_dir,'GIS/huc' + hucLength + r'.json'))
        with open(geojson_path) as f:
            geoDataJson = json.loads(f.read())
    for huc in hucList:
        if not equalLength:
            hucLength = str(len(huc))
            geojson_path = (os.path.join(static_dir,'GIS/huc' + hucLength + r'.json'))
            with open(geojson_path) as f:
                geoDataJson = json.loads(f.read())
        geoDataTemp = [d for d in geoDataJson['features'] if
                    d['properties'].get('HUC' + hucLength) == huc]
        geoData['features'].extend(geoDataTemp)
    return geoData

def getSWEsites(terms):
    swe_trips = list(set([i['stationElement']['stationTriplet'] for sub in 
             terms for i in sub 
             if i['stationElement']['elementCd'] == 'WTEQ' and
             i['stationElement']['stationTriplet'][-4:] == 'SNTL']))
#    swe_trips = list(set([i['stationElement']['stationTriplet'] for i in terms 
#             if i['stationElement']['elementCd'] == 'WTEQ' and
#             i['stationElement']['stationTriplet'][-4:] == 'SNTL']))
    return swe_trips

def getUpstreamUSGS(terms):
    upstream_trips = list(set([i['stationElement']['stationTriplet'] for sub in 
             terms for i in sub 
             if i['stationElement']['elementCd'] == 'SRVO' and
             i['upstreamForecast']]))
#    upstream_trips = list(set([i['stationElement']['stationTriplet'] for i in terms 
#             if i['stationElement']['elementCd'] == 'SRVO' and
#             i['upstreamForecast']]))
    return upstream_trips

def get_bootstrap():
    
    return {
        'css': f'{STATIC_URL}/bootstrap/css/bootstrap.min.css',
        'js': f'{STATIC_URL}/bootstrap/js/bootstrap.bundle.js',
        'jquery': f'{STATIC_URL}/jquery.js',
        'popper': f'{STATIC_URL}/popper.js',
        'fa': f'{STATIC_URL}/font-awesome/css/font-awesome.min.css',
    }

def get_plotly_js():
    
    return f'{STATIC_URL}/plotly.js'

def get_favicon():
    
    return f'{STATIC_URL}/img/favicon.ico'

def get_bor_seal(orient='default', grey=False):
    
    color = 'cmyk'
    if grey:
        color = 'grey'
    seal_dict = {
        'default': f'BofR-horiz-{color}.png',
        'shield': f'BofR-shield-cmyk.png',
        'vert': f'BofR-vert-{color}.png',
        'horz': f'BofR-horiz-{color}.png'
        }
    return f'{STATIC_URL}/img/{seal_dict[orient]}'

def get_plot_config(img_filename):
    return {
        'modeBarButtonsToRemove': [
            'sendDataToCloud',
            'lasso2d',
            'select2d'
        ],
        'showAxisDragHandles': True,
        'showAxisRangeEntryBoxes': True,
        'displaylogo': False,
        'toImageButtonOptions': {
            'filename': img_filename,
            'width': 1200,
            'height': 700
        }
    }

def get_log_scale_dd():
    log_scale_dd = [
        {
            'active': 0,
            'showactive': True,
            'x': 1.1,
            'y': -0.025,
            'xanchor': 'left',
            'yanchor': 'top',
            'bgcolor': 'rgba(0,0,0,0)',
            'type': 'buttons',
            'direction': 'down',
            'font': {
                'size': 10
            },
            'buttons': [
                {
                    'label': 'Linear Scale',
                    'method': 'relayout',
                    'args': [
                        'yaxis2', 
                            {
                                'type': 'linear', 'rangemode': 'nonnegative',
                                'overlaying': 'y', 'side':'right', 
                                'anchor':'free', 'position': 1,
                                'title': 'Q (cfs)','tickformat': "f", 
                                'tick0': 0
                            }
                    ]
                },
                {
                    'label': 'Log Scale',
                    'method': 'relayout',
                    'args': [
                        'yaxis2',
                            {
                                'type': 'log', 'rangemode': 'nonnegative',
                                'overlaying': 'y', 'side':'right', 
                                'anchor':'free', 'position': 1,
                                'title': 'Q (cfs)','tickformat': "f", 
                                'tick0': 1, 'dtick': 'D2'
                            }
                    ]
                },
            ]
        }
    ]
    return log_scale_dd
if __name__ == '__main__':
    import os
    print('why are you running this?')
    dirpath = os.getcwd()
    print(os.path.basename(dirpath))