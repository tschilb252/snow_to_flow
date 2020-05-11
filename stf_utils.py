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
from os import path
from datetime import datetime as dt
from datetime import date as date
import pandas as pd
import numpy as np
import folium
import branca
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

def get_bor_js():
    
    return [
        ('leaflet',
          f'{STATIC_URL}/js/leaflet/leaflet.js'),
        ('jquery',
          f'{STATIC_URL}/js/jquery/3.4.0/jquery.min.js'),
        ('bootstrap',
          f'{STATIC_URL}/js/bootstrap/3.2.0/js/bootstrap.min.js'),
        ('awesome_markers',
          f'{STATIC_URL}/js/leaflet/leaflet.awesome-markers.js'),  # noqa
        ]

def get_bor_css():
    
    return [
        ('leaflet_css',
          f'{STATIC_URL}/css/leaflet/leaflet.css'),
        ('bootstrap_css',
          f'{STATIC_URL}/css/bootstrap/3.2.0/css/bootstrap.min.css'),
        ('bootstrap_theme_css',
          f'{STATIC_URL}/css/bootstrap/3.2.0/css/bootstrap-theme.min.css'),  # noqa
        ('awesome_markers_font_css',
          f'{STATIC_URL}/css/font-awesome.min.css'),  # noqa
        ('awesome_markers_css',
          f'{STATIC_URL}/css/leaflet/leaflet.awesome-markers.css'),  # noqa
        ('awesome_rotate_css',
          f'{STATIC_URL}/css/leaflet/leaflet.awesome.rotate.css'),  # noqa
        ]

def get_default_js():
    
    bootstrap_dict = get_bootstrap()
    return [
        ('leaflet', 
         f'{STATIC_URL}/leaflet/js/leaflet.js'),
        ('jquery', 
         bootstrap_dict['jquery']),
        ('bootstrap', 
         bootstrap_dict['js']),
        ('awesome_markers', 
         f'{STATIC_URL}/leaflet-awesome-markers/leaflet.awesome-markers.min.js'),
        ('popper', 
         bootstrap_dict['popper']),
    ]

def get_default_css():
    
    bootstrap_dict = get_bootstrap()
    return [
        ('leaflet_css', 
         f'{STATIC_URL}/leaflet/css/leaflet.css'),
        ('bootstrap_css', 
         bootstrap_dict['css']),
        ('awesome_markers_font_css', 
          bootstrap_dict['fa']),
        ('awesome_markers_css', 
        f'{STATIC_URL}/leaflet-awesome-markers/leaflet.awesome-markers.css'),
        ('awesome_rotate_css', 
         f'{STATIC_URL}/leaflet-awesome-markers/leaflet.awesome.rotate.css'),
    ]

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

def add_optional_tilesets(folium_map):
    
    tilesets = {
        "Terrain": 'Stamen Terrain',
        'Street Map': 'OpenStreetMap',
        'Toner': 'Stamen Toner',
        'Watercolor': 'Stamen Watercolor',
        'Positron': 'CartoDB positron',
        'Dark Matter': 'CartoDB dark_matter',
    }
    for name, tileset in tilesets.items():
        folium.TileLayer(tileset, name=name).add_to(folium_map)

def add_huc_layer(huc_map, level=2, huc_geojson_path=None, embed=False, 
                  show=True, huc_filter=''):
    try:
        if type(huc_filter) == int:
            huc_filter = str(huc_filter)
        weight = -0.25 * float(level) + 2.5
        if not huc_geojson_path:
            huc_geojson_path = f'{STATIC_URL}/gis/HUC{level}.geojson'
        else:
            embed = True
        if huc_filter:
           huc_style = lambda x: {
            'fillColor': '#ffffff00', 'color': '#1f1f1faa', 
            'weight': weight if x['properties'][f'HUC{level}'].startswith(huc_filter) else 0
        } 
        else:
            huc_style = lambda x: {
                'fillColor': '#ffffff00', 'color': '#1f1f1faa', 'weight': weight
            }
        folium.GeoJson(
            huc_geojson_path,
            name=f'HUC {level}',
            embed=embed,
            style_function=huc_style,
            show=show
        ).add_to(huc_map)
    except Exception as err:
        print(f'Could not add HUC {level} layer to map! - {err}')

def clean_coords(coord_series, force_neg=False):
    
    coord_series = coord_series.apply(
        pd.to_numeric, 
        errors='ignore', 
        downcast='float'
    )
    if not coord_series.apply(type).eq(str).any():
        if force_neg:
            return -1 * coord_series.abs()
        return coord_series
    results = []
    for idx, coord in coord_series.iteritems():
        if not str(coord).replace('.', '').replace('-', '').isnumeric():
            coord_strs = str(coord).split(' ')
            coord_digits = []
            for coord_str in coord_strs:
                coord_digit = ''.join([ch for ch in coord_str if ch.isdigit() or ch == '.'])
                coord_digits.append(float(coord_digit))
            dec = None
            coord_dec = 0
            for i in reversed(range(0, len(coord_digits))):
                if dec:
                    coord_dec = abs(coord_digits[i]) + dec
                dec = coord_digits[i] / 60
            if str(coord)[0] == '-':
                coord_dec = -1 * coord_dec
            results.append(coord_dec)
        else:
            results.append(coord)
    if force_neg:
        results[:] = [-1 * result if result > 0 else result for result  in results]
    clean_series = pd.Series(results, index=coord_series.index)
    return clean_series

def add_huc_chropleth(m, data_type='swe', show=False, huc_level='6', 
                      gis_path='gis', huc_filter='', use_topo=False):
    
    huc_str = f'HUC{huc_level}'
    stat_type_dict = {'swe': 'Median', 'prec': 'Avg.'}
    stat_type = stat_type_dict.get(data_type, '')
    layer_name = f'{huc_str} % {stat_type} {data_type.upper()}'
    if use_topo:
        topo_json_path = path.join(gis_path, f'{huc_str}.topojson')
        with open(topo_json_path, 'r') as tj:
            topo_json = json.load(tj)
        if huc_filter:
            topo_json = filter_topo_json(
                topo_json, huc_level=huc_level, filter_str=huc_filter
            )
    style_function = lambda x: style_chropleth(
        x, data_type=data_type, huc_level=huc_level, huc_filter=huc_filter
    )
    tooltip = folium.features.GeoJsonTooltip(
        ['Name', f'{data_type}_percent', f'{data_type}_updt'],
        aliases=['Basin Name:', f'{layer_name}:', 'Updated:']
    )
    # tooltip = folium.features.GeoJsonTooltip(
    #     ['Name', f'{data_type}_percent', f'HUC{huc_level}'],
    #     aliases=['Basin Name:', f'{layer_name}:', 'ID:']
    # )
    if use_topo:
        folium.TopoJson(
            topo_json,
            f'objects.{huc_str}',
            name=layer_name,
            overlay=True,
            show=show,
            smooth_factor=2.0,
            style_function=style_function,
            tooltip=tooltip
        ).add_to(m)
    else:
        json_path = f'{STATIC_URL}/gis/HUC{huc_level}.geojson'
        folium.GeoJson(
            json_path,
            name=layer_name,
            embed=False,
            overlay=True,
            control=True,
            smooth_factor=2.0,
            style_function=style_function,
            show=show,
            tooltip=tooltip
        ).add_to(m)

def style_chropleth(feature, data_type='swe', huc_level='2', huc_filter=''):
    colormap = get_colormap()
    if type(huc_filter) == int:
        huc_filter = str(huc_filter)
    huc_level = str(huc_level)
    stat_value = feature['properties'].get(f'{data_type}_percent', 'N/A')
    huc_id = str(feature['properties'].get(f'HUC{huc_level}', 'N/A'))
    if not stat_value == 'N/A':
        stat_value = float(stat_value)
    
    return {
        'fillOpacity': 
            0 if stat_value == 'N/A' or 
            not huc_id.startswith(huc_filter) else 
            0.75,
        'weight': 0,
        'fillColor': 
            '#00000000' if stat_value == 'N/A' or 
            not huc_id.startswith(huc_filter) else 
            colormap(stat_value)
    }

def get_colormap(low=50, high=150):
    
    colormap = branca.colormap.LinearColormap(
        colors=[
            (255,51,51,150), 
            (255,255,51,150), 
            (51,255,51,150), 
            (51,153,255,150), 
            (153,51,255,150)
        ], 
        index=[50, 75, 100, 125, 150], 
        vmin=50,
        vmax=150
    )
    colormap.caption = '% of Average Precipitation or % Median Snow Water Equivalent'
    return colormap

def filter_geo_json(geo_json_path, huc_level=2, filter_str=''):
   
    filter_attr = f'HUC{huc_level}'
    f_geo_json = {'type': 'FeatureCollection'}
    with open(geo_json_path, 'r') as gj:
        geo_json = json.load(gj)
    features = [i for i in geo_json['features'] if 
                i['properties'][filter_attr][:len(filter_str)] == filter_str]
    f_geo_json['features'] = features
    
    return f_geo_json

def filter_topo_json(topo_json, huc_level=2, filter_str=''):
    
    geometries = topo_json['objects'][f'HUC{huc_level}']['geometries']
    geometries[:] = [i for i in geometries if 
                i['properties'][f'HUC{huc_level}'][:len(filter_str)] == filter_str]
    topo_json['geometries'] = geometries
    return topo_json
        
def get_obj_type_name(obj_type='default'):
    
    obj_type_dict = {
            'default': 'map-pin',
            0: 'reservoir',
            1: 'basin',
            2: 'climate site (rain)',
            3: 'confluence',
            4: 'diversion',
            5: 'hydro power plant',
            6: 'reach',
            7: 'reservoir',
            8: 'climate site (snow)',
            9: 'stream gage',
            10: 'hydro plant unit',
            11: 'canal',
            12: 'acoustic velocity meter',
            13: 'water quality site',
            14: 'riverware data object',
            300: 'bio eval. site',
            305: 'agg. diversion site',
            'SCAN': 'climate site (rain)',
            'PRCP': 'climate site (rain)',
            'BOR': 'reservoir',
            'SNTL': 'climate site (snow)',
            'SNOW': 'climate site (snow)',
            'SNTLT': 'climate site (snow)',
            'USGS': 'stream gage',
            'MSNT': 'climate site (snow)',
            'MPRC': 'climate site (rain)'
        }
    return obj_type_dict.get(obj_type, 'N/A')

def get_icon_color(row, source='awdb'):
    
    if source.lower() == 'hdb':
        obj_owner = 'BOR'
        if not row.empty:
            if row['site_metadata.scs_id']:
                obj_owner = 'NRCS'
            if row['site_metadata.usgs_id']:
                obj_owner = 'USGS'
    if source.lower() == 'awdb':
        obj_owner = row
    color_dict = {
        'BOR': 'blue',
        'NRCS': 'red',
        'USGS': 'green',
        'COOP': 'gray',
        'SNOW': 'darkred',
        'PRCP': 'lightred',
        'SNTL': 'red',
        'SNTLT': 'lightred',
        'SCAN': 'lightred',
        'MSNT': 'orange',
        'MPRC': 'beige',
        
    }
    icon_color = color_dict.get(obj_owner, 'black')
    return icon_color

def get_fa_icon(obj_type='default', source='hdb'):
    
    if source.lower() == 'hdb':
        fa_dict = {
            'default': 'map-pin',
            0: 'tint',
            1: 'sitemap',
            2: 'umbrella',
            3: 'arrow-down',
            4: 'exchange',
            5: 'plug',
            6: 'arrows-v',
            7: 'tint',
            8: 'snowflake-o',
            9: 'tachometer',
            10: 'cogs',
            11: 'arrows-h',
            12: 'rss',
            13: 'flask',
            14: 'table',
            300: 'info',
            305: 'exchange'
        }
    if source.lower() == 'awdb':
        fa_dict = {
            'default': 'map-pin',
            'SCAN': 'umbrella',
            'PRCP': 'umbrella',
            'BOR': 'tint',
            'SNTL': 'snowflake-o',
            'SNOW': 'snowflake-o',
            'SNTLT': 'snowflake-o',
            'USGS': 'tachometer',
            'MSNT': 'snowflake-o',
            'MPRC': 'umbrella'
        }
    fa_icon = fa_dict.get(obj_type, 'map-pin')
    return fa_icon

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