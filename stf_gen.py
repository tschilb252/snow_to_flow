# -*- coding: utf-8 -*-
"""
Created on Fri Feb 16 07:40:44 2018

@author: Beau.Uriona
"""

import json
import time
import random
import asyncio
import logging
import decimal
import warnings
import datetime
from datetime import datetime as dt
from datetime import date as date
from os import path, makedirs
from itertools import chain
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import TimedRotatingFileHandler
import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.offline as py
from requests import get as r_get
from zeep.helpers import serialize_object as serialize
from stf_utils import padMissingData, get_plot_config, get_bor_seal
from stf_utils import get_favicon, get_plotly_js, getSWEsites
from stf_utils import isActive, create_awdb, getUpstreamUSGS, get_log_scale_dd
from stf_nav import create_nav
from stf_site_map import create_map

NRCS_DATA_URL = r'https://www.nrcs.usda.gov/Internet/WCIS/sitedata'

def create_log(path='stf_charts.log'):
    logger = logging.getLogger('stf_charts rotating log')
    logger.setLevel(logging.INFO)

    handler = TimedRotatingFileHandler(
        path,
        when="W6",
        backupCount=1
    )

    logger.addHandler(handler)

    return logger

def print_and_log(log_str, logger=None):
    print(log_str)
    if logger:
        logger.info(log_str)
                  
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

async def async_get_equations(frcsts_meta, workers=8, indent=None):
    this_dir = path.dirname(path.abspath(__file__))
    frcst_eq_dir = path.join(this_dir, 'frcst_eq')
    def get_frcst_eq(frcst_meta):
        print_and_log(
            f'    Updating {frcst_meta["name"]} equation.', 
            logger
        )
        frcst_triplet = frcst_meta['stationTriplet']
        frcst_filename = f'{frcst_triplet.replace(":", "_")}.frcst'
        frcst_path = path.join(frcst_eq_dir, frcst_filename)
        try:
            equation = serialize(awdb.getForecastEquations(frcst_triplet))
        except Exception as err:            
            print_and_log(
                f'    Could not get equation for {frcst_triplet} - {err}',
                logger
            )
            return frcst_meta
        with open(frcst_path, 'w') as j:
            json.dump(equation, j, indent=indent, cls=DecimalEncoder)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        loop = asyncio.get_event_loop()
        futures = [
            loop.run_in_executor(
                executor, 
                get_frcst_eq,
                frcst_meta
            )
            for frcst_meta in frcsts_meta
        ]
        
        result = await asyncio.gather(*futures)
        return [i for i in result if i]

def get_equations(frcsts_meta, logger=None, indent=None):
    this_dir = path.dirname(path.abspath(__file__))
    frcst_eq_dir = path.join(this_dir, 'frcst_eq')
    for frcst_meta in frcsts_meta:
        print_and_log(
            f'    Updating {frcst_meta["name"]} equation.', 
            logger
        )
        frcst_triplet = frcst_meta['stationTriplet']
        frcst_filename = f'{frcst_triplet.replace(":", "_")}.frcst'
        frcst_path = path.join(frcst_eq_dir, frcst_filename)
        equation = serialize(awdb.getForecastEquations(frcst_triplet))
        with open(frcst_path, 'w') as j:
            json.dump(equation, j, indent=indent, cls=DecimalEncoder)
            
def updt_frcst_eqs(awdb=create_awdb(), logger=None, indent=None, workers=1):
    this_dir = path.dirname(path.abspath(__file__))
    frcst_eq_dir = path.join(this_dir, 'frcst_eq')
    makedirs(frcst_eq_dir, exist_ok=True)
    hucs = [10,11,12,13,14,15,16,17,18]
    all_frcsts = []
    print_and_log('Updating equations for all HUCs.', logger)
    for huc in hucs:
        print_and_log(f'  Updating equations for {huc} HUC.', logger)
        frcsts = serialize(
            awdb.getForecastPoints('*', '*', '*', '*', f'{huc}*', '*', True)
        )
        if not frcsts:
            continue
        frcst_triplets = [x['stationTriplet'] for x in frcsts]
        frcsts_meta = serialize(
            awdb.getStationMetadataMultiple(frcst_triplets)
        )
        frcsts_meta[:] = [i for i in frcsts_meta if isActive(i)]
        all_frcsts.extend(frcsts_meta)
        
        if workers > 1:
            failed_soaps = []
            loop = asyncio.get_event_loop()
            failed_soaps.extend(
                loop.run_until_complete(
                    async_get_equations(frcsts_meta, workers, indent)
                )
            )
            if failed_soaps:
                num_failed = len(failed_soaps)
                print_and_log(
                    f'  Getting {num_failed} sites that failed during async routine',
                    logger
                )
                get_equations(failed_soaps, logger=logger, indent=indent)
        else:
            get_equations(frcsts_meta, logger=logger, indent=indent)
        
    all_frcst_path = path.join(frcst_eq_dir, 'all_frcsts.json')
    with open(all_frcst_path, 'w') as j:
        json.dump(all_frcsts, j, indent=indent, cls=DecimalEncoder)
    print_and_log('\nSuccessfully updated equations for all HUCs.', logger)

def get_frcsts(huc='all', awdb=create_awdb(), logger=None):
    try:
        this_dir = path.dirname(path.abspath(__file__))
        frcst_eq_dir = path.join(this_dir, 'frcst_eq')
        all_frcst_path = path.join(frcst_eq_dir, 'all_frcsts.json')
        with open(all_frcst_path, 'r') as j:
           frcsts =  json.load(j)
        if huc == 'all':
            return frcsts
        frcsts[:] = [i for i in frcsts if str(i['huc'])[:len(str(huc))] == huc]
        return frcsts
    except Exception as err:
        print_and_log(
            f'    Error using local file: {err}.\n'
            f'    Please run an --update to increase performance', 
            logger
        )
        if huc == 'all':
            huc = ''
        return serialize(
            awdb.getForecastPoints('*', '*', '*', '*', f'{huc}*', '*', True)
        )

def get_frcst_eq(frcst_triplet, awdb=create_awdb(), logger=None):
    try:
        this_dir = path.dirname(path.abspath(__file__))
        frcst_eq_dir = path.join(this_dir, 'frcst_eq')
        frcst_filename = f'{frcst_triplet.replace(":", "_")}.frcst'
        frcst_eq_path = path.join(frcst_eq_dir, frcst_filename)
        with open(frcst_eq_path, 'r') as j:
           frcst_eq =  json.load(j)
        return frcst_eq
    except FileNotFoundError as err:
        print_and_log(
            f'    Error using local file: {err}\n'
            f'    Please run an --update to increase performance', 
            logger
        )
        try:
            return serialize(awdb.getForecastEquations(frcst_triplet))
        except Exception as err:
            print_and_log(
                f'    Error using nrcs webservice: {err}', 
                logger
            )
    return None
        
def get_upstream_snotels(terms, swe_trips, frcst_triplets):
    upstream_trips = getUpstreamUSGS(terms)
    for trip in upstream_trips:
        if trip in frcst_triplets:
            equation = get_frcst_eq(trip, awdb=awdb, logger=logger)
            if not equation:
                continue
            terms = [j['equationTerms'] for j in equation]
            swe_trips.extend(getSWEsites(terms))
            upstream_trips.extend(getUpstreamUSGS(terms))
            upstream_trips[:] = set(upstream_trips)
    swe_trips[:] = set(swe_trips)
    return swe_trips

def get_site_anno(meta):
    url_prefix = r"<a href='https://wcc.sc.egov.usda.gov/nwcc/site?sitenum="
    site_anno = []
    for site_meta in meta:
        triplet_split = site_meta['stationTriplet'].split(':')
        nrcs_id = triplet_split[0]
        state = triplet_split[1]
        name = site_meta['name']
        anno = f"{url_prefix}{nrcs_id}'>{name} ({state})</a>"
        site_anno.append(anno)
    site_anno[:] = [
        '<br>' + x if i % 8 == 0 else x for i, x in enumerate(site_anno)
    ]
    return site_anno

def get_site_list_link(meta):
    site_list_link = {
        'prefix': f'https://wcc.sc.egov.usda.gov/reportGenerator'
        f'/view/customMultipleStationReport/daily/start_of_period/', 
        'suffix': f'id=%22%22%7Cname/0,0/stationId,state.code,'
        f'network.code,name,elevation,latitude,longitude,'
        f'county.name,huc8.huc,huc8.hucName,inServiceDate'
        f',outServiceDate?fitToScreen=false',
        'delim': f'%7C',
        'text': 'Station List'
    }
    site_triplets = [i['stationTriplet'] for i in meta]
    site_list_triplets = [f"{triplet}{site_list_link['delim']}" for triplet 
                          in site_triplets]
    sites_link = (
            f"<a href='{site_list_link['prefix']}"
            f"{''.join(site_list_triplets)}{site_list_link['suffix']}'>"
            f"{site_list_link['text']}</a>"
        )
    return sites_link

def get_swe_data_soap(swe_trips, sDate, eDate, awdb=create_awdb()):
    swe_data = awdb.getData(
        swe_trips,'WTEQ', 1, None, 'DAILY', False, sDate, eDate, True
    )
    return serialize(swe_data)

def get_frcst_element(frcstTriplet, awdb=create_awdb(), logger=None):
    elements = serialize(awdb.getStationElements(frcstTriplet))
    has_srdoo = False
    for element in elements:
        if element['elementCd'].upper() == 'SRDOX':
            if element['duration'] == 'DAILY':
                return 'SRDOX'
        if element['elementCd'].upper() == 'SRDOO':
            if element['duration'] == 'DAILY':
                has_srdoo = True
    if has_srdoo:
        return 'SRDOO'
    return None

def get_swe_data(swe_trips, sDate, eDate, awdb=create_awdb()):
    swe_data = []
    for swe_trip in swe_trips:
        swe_trip_url = swe_trip.replace(":", "_")
        swe_url = f'{NRCS_DATA_URL}/DAILY/WTEQ/{swe_trip_url}.json'
        swe_results = r_get(swe_url)
        if swe_results.status_code == 200:
            swe_data.append(swe_results.json())
        else:
            return get_swe_data_soap(swe_trips, sDate, eDate, awdb)
    return swe_data

def get_flow_data(triplet, sDate, eDate, element):
    if element in ['SRDOO', 'SRDOX']:
        flow_url = f'{NRCS_DATA_URL}/{element}/{triplet.replace(":", "_")}.json'
        flow_results = r_get(flow_url)
        if flow_results.status_code == 200:
            flowData = flow_results.json()
            return flowData
    flowData = serialize(awdb.getData(
        triplet, element, 1, None, 'DAILY', False, sDate, eDate, 
        True)
    )
    return flowData[0]
            
        
def updtChart(frcstTriplet, siteName, swe_meta, all_frcst_trips,
              awdb=create_awdb(), logger=None):
    print_and_log(f'  Creating Snow to Flow Chart for {siteName}', logger)
    today = dt.utcnow() - datetime.timedelta(hours=8)
    sDate = date(1900, 10, 1).strftime("%Y-%m-%d")
    eDate = today.date().strftime("%Y-%m-%d 00:00:00")
    equation = get_frcst_eq(frcstTriplet, awdb=awdb, logger=logger)
    if not equation:
        return (
            f'No valid forecast equation exists for {siteName} '
            f'- {frcstTriplet}.'
        )
    flow_element = get_frcst_element(frcstTriplet, awdb=awdb, logger=logger)
    if not flow_element:
        return f'No valid flow element exists for {siteName} - {frcstTriplet}.'
    terms = [j['equationTerms'] for j in equation]
    swe_trips = getSWEsites(terms)
    swe_trips = get_upstream_snotels(terms, swe_trips, all_frcst_trips)
    if not swe_trips:
        return (
            f'No snotels used in the forecast equation for '
            f'{siteName} - {frcstTriplet}.'
        )

    meta = [x for x in swe_meta if x['stationTriplet'] in swe_trips] 
    
    sites_link = get_site_list_link(meta)
    # site_anno = get_site_anno(meta)
    sweData = get_swe_data(swe_trips, sDate, eDate, awdb)
    sweData[:] = [x for x in sweData if x]
    if not sweData:
        return (
            f'No snotel data available in forecast equation for '
            f'{siteName} - {frcstTriplet}.'
        )
    
    flowData = get_flow_data(frcstTriplet, sDate, eDate, flow_element)
    if not flowData['values']:
        flowData = get_flow_data(frcstTriplet, sDate, eDate, 'SRDOX')
        if not flowData['values']:
            flowData = get_flow_data(frcstTriplet, sDate, eDate, 'SRDOO')
            if not flowData['values']:
                return (
                    f'No flow data available for '
                    f'{siteName} - {frcstTriplet} - {flow_element}.'
                )
    
    date_series = [date(2015,10,1) + datetime.timedelta(days=x)
                    for x in range(0, 366)]
    
    beginDateDict = {}
    for siteMeta in meta:
        if siteMeta['beginDate']:
            beginDate = dt.strptime(
                str(siteMeta['beginDate']),
                "%Y-%m-%d %H:%M:%S"
            )
            beginDateDict.update({str(siteMeta['stationTriplet']): beginDate}) 
    
    basinBeginDate = min(beginDateDict.values())

    sYear = basinBeginDate.year
    if basinBeginDate.year > sYear:
        if basinBeginDate.month < 10:
            sYear = basinBeginDate.year
        else:
            if basinBeginDate.month == 10 and basinBeginDate.day == 1:
                sYear = basinBeginDate.year
            else:
                sYear = basinBeginDate.year + 1
    
    sDate = date(sYear, 10, 1).strftime("%Y-%m-%d")             
    eDate = today.date().strftime("%Y-%m-%d")

    for dataSite in sweData:
        if dataSite:
            dataSite = padMissingData(dataSite, sDate, eDate)
    
            
    plotData = [np.array(x['values'], dtype=float) for x in sweData if x]
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        basinPlotData = list(np.nanmean(
                np.array([i for i in plotData]), axis=0))
        nonNan = [[0 if np.isnan(x) else 1 for x in i] for i in plotData]
        nonNanSum = [np.nansum(i) for i in zip(*nonNan)]
        dailySitesNum = list([nonNanSum[i:i+366] 
            for i in range(0,len(nonNanSum),366)])
        yearlySitesNum = {
            str(sYear + idx + 1): int(np.nanmedian(i)) for 
            idx, i in enumerate(dailySitesNum)
        }
    lastYearOfData = str(np.max([int(i) for i in yearlySitesNum.keys()]))
    currNumBasinSites = yearlySitesNum[str(lastYearOfData)]
    PORplotData = list([basinPlotData[i:i+366] 
                    for i in range(0,len(basinPlotData),366)])

    allButCurrWY = list(PORplotData)
    del allButCurrWY[-1]
    
    statsData = [
        PORplotData[i] for i, x in enumerate(yearlySitesNum.values()) if 
        int(x) > currNumBasinSites * 0.5
    ]
    del statsData[-1]
    statsData = list(map(list,zip(*statsData)))
    
    if len(statsData[0]) > 1:
        statsData[151] = statsData[150]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            minData = [np.nanmin(a) for a in statsData]
            maxData = [np.nanmax(a) for a in statsData]
            lowestData = [np.nanpercentile(a,10) for a in statsData]
            highestData = [np.nanpercentile(a,90) for a in statsData]
            medianData = [np.nanpercentile(a,50) for a in statsData]
            lowData = [np.nanpercentile(a,30) for a in statsData]
            highData = [np.nanpercentile(a,70) for a in statsData]
        sliderDates = list(chain([(date_series[0])] + 
                                      [date_series[-1]]))
    else:
        sliderDates = list(chain([(date_series[0])] + [date_series[-1]]))
    
    dfSWE ={
        'min': minData,
        '10th': lowestData,
        '30th': lowData,
        '50th': medianData,
        '70th': highData,
        '90th': highestData,
        'max': maxData
    }
    
    for i, eachYear in enumerate(allButCurrWY):
        dfSWE[str(sYear + i + 1)] = eachYear

    PORplotData[-1].extend([np.nan]*(366-len(PORplotData[-1])))
    if int(eDate.split('-')[1]) >= 10:
      dfSWE[str(int(eDate[:4]) + 1)] = PORplotData[-1]
    else:
      dfSWE[str(eDate[:4])] = PORplotData[-1]
    
    dfSWE = pd.DataFrame(dfSWE)
    if dfSWE.empty:
        return (
            f'No snotel data available in forecast equation for '
            f'{siteName} - {frcstTriplet}.'
        )
    jDay = dfSWE[str(eDate[:4])].last_valid_index()
    jDayData = dfSWE.iloc[jDay]
    dropCols = [i for i in dfSWE.columns.tolist() if not i.isdigit()]
    jDayData.drop(dropCols,inplace=True)
    jDayData.sort_values(inplace=True)
    maxData = dfSWE.max(axis=0)
    maxData.drop(dropCols,inplace=True)
    maxData.sort_values(inplace=True)
    
    flowData = padMissingData(flowData, sDate, eDate)
    
    plotData = np.array(flowData['values'], dtype=float)
    
    PORplotData = list([plotData[i:i+366] 
                    for i in range(0,len(plotData),366)])
    PORplotData[:] = [list(x) for x in PORplotData]

    allButCurrWY = list(PORplotData)
    del allButCurrWY[-1]
    statsData = list(map(list,zip(*allButCurrWY)))
    
    if len(statsData[0]) > 1:
        statsData[151] = statsData[150]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            minData = [np.nanmin(a) for a in statsData]
            maxData = [np.nanmax(a) for a in statsData]
            lowestData = [np.nanpercentile(a,10) for a in statsData]
            highestData = [np.nanpercentile(a,90) for a in statsData]
            medianData = [np.nanpercentile(a,50) for a in statsData]
            lowData = [np.nanpercentile(a,30) for a in statsData]
            highData = [np.nanpercentile(a,70) for a in statsData]
   
    dfQ ={
        'min': minData,
        '10th': lowestData,
        '30th': lowData,
        '50th': medianData,
        '70th': highData,
        '90th': highestData,
        'max': maxData
    }
    
    for i, eachYear in enumerate(allButCurrWY):
        if str(sYear + i + 1) in dfSWE.columns:
            dfQ[str(sYear + i + 1)] = eachYear
    
    PORplotData[-1].extend([np.nan]*(366-len(PORplotData[-1])))
    if int(eDate.split('-')[1]) >= 10:
      dfQ[str(int(eDate[:4]) + 1)] = PORplotData[-1]
    else:
      dfQ[str(eDate[:4])] = PORplotData[-1]
    dfQ = pd.DataFrame(dfQ)
    
    
    colScheme = [
        'rgb(41,111,99)',
        'rgb(155,155,79)',
        'rgb(90,86,118)',
        'rgb(151,28,114)',
        'rgb(28,77,111)',
        'rgb(153,80,0)',
        'rgb(79,122,5)',
        'rgb(152,105,129)',
        'rgb(117,117,117)',
        'rgb(88,28,89)'
    ]
    trace = []
    for idx, i in enumerate(dfSWE):
        if i.isdigit() and yearlySitesNum[i]:
            not_used = ''
            if int(yearlySitesNum[i]) < 0.5 * currNumBasinSites:
                not_used = '<sup>*</sup>'
            legend_name = f'{i}{not_used} ({yearlySitesNum[i]} sites)'
            if i == lastYearOfData:
                color = 'rgb(0,0,0)'
                visible=True
            else:
                randCol = int(random.uniform(0,10))
                color = colScheme[randCol]
                visible='legendonly'
            trace.extend(
                [
                    go.Scatter(
                        x=date_series,y=dfSWE[i], showlegend=True,
                        name=legend_name, legendgroup=str(i), hovertext='in. SWE',
                        visible=visible, connectgaps=True,
                        line=dict(color=color)
                    ),
                    go.Scatter(
                        x=date_series, y=dfQ[i], yaxis='y2', 
                        name=legend_name, legendgroup=str(i), hovertext='cfs',
                        visible=visible, connectgaps=True, showlegend=False,
                        line=dict(color=color, dash='dash')
                    )
                ]
            )
            
    trace.extend(
        [
            go.Scatter(
                x=date_series,y=dfSWE['min'],
                    legendgroup='SWEcentiles', name=r'Min',
                    visible=True, line=dict(width=0),connectgaps=True,
                    fillcolor='rgba(237,0,1,0.15)', hoverinfo='none',
                    fill='none', showlegend=False
                ),
            go.Scatter(
                x=date_series, y=dfQ['min'], yaxis='y2',
                legendgroup='Qcentiles', name=r'Min',hoverinfo='none',
                visible=True, connectgaps=True,fill='none',showlegend=False,
                line=dict(width=2, color='rgba(100,100,100,0.25)', dash='dash'),
            ),
        ]
    ) 
    
    trace.extend(
        [
            go.Scatter(
                x=date_series, y=dfSWE['10th'], line=dict(width=0),
                legendgroup='SWEcentiles', name=r'10%', visible=True,
                fillcolor='rgba(237,0,1,0.15)',  connectgaps=True,
                fill='tonexty', showlegend=False, hoverinfo='none'
            ),
            go.Scatter(
                x=date_series, y=dfQ['10th'], yaxis='y2',
                legendgroup='Qcentiles', name=r'10%',
                visible=True, line=dict(width=0), connectgaps=True,
                fillcolor='rgba(100,100,100,0.25)',
                fill='tonexty',showlegend=False,hoverinfo='none'
            )
        ]
    )

    trace.extend(
        [
            go.Scatter(
                x=date_series, y=dfSWE['30th'],
                legendgroup='SWEcentiles', name=r'30%', visible=True,
                line=dict(width=0), connectgaps=True,
                fillcolor='rgba(237,237,0,0.15)',
                fill='tonexty', showlegend=False, hoverinfo='none'
            ),
            go.Scatter(
                x=date_series, y=dfQ['30th'], yaxis='y2',
                    legendgroup='Qcentiles', name=r'30%', visible=True,
                    line=dict(width=0), connectgaps=True,
                    fillcolor='rgba(175,175,175,0.25)',
                    fill='tonexty', showlegend=False, hoverinfo='none'
            )
        ]
    )

    trace.extend(
        [
            go.Scatter(
                x=date_series,y=dfSWE['70th'], connectgaps=True,
                legendgroup='SWEcentiles',name=r'70%',visible=True,
                fillcolor='rgba(115,237,115,0.15)', line=dict(width=0),
                fill='tonexty', showlegend=False,hoverinfo='none'
            ),
            go.Scatter(
                x=date_series, y=dfQ['70th'], yaxis='y2', visible=True,
                legendgroup='Qcentiles', name=r'70%.', line=dict(width=0),
                fillcolor='rgba(250,250,250,0.25)', connectgaps=True,
                fill='tonexty', showlegend=False, hoverinfo='none'
            )
        ]
    )
    
    trace.extend(
        [
            go.Scatter(
                x=date_series, y=dfSWE['90th'], legendgroup='SWEcentiles',
                connectgaps=True ,name=r'90%', visible=True, 
                line=dict(width=0), fillcolor='rgba(0,237,237,0.15)',
                fill='tonexty', showlegend=False, hoverinfo='none'
            ),
            go.Scatter(
                x=date_series, y=dfQ['90th'], yaxis='y2',
                legendgroup='Qcentiles', connectgaps=True,
                name=r'90%', visible=True, line=dict(width=0),
                fillcolor='rgba(175,175,175,0.25)',
                fill='tonexty', showlegend=False, hoverinfo='none'
            )
        ]
    )
    
    trace.extend(
        [
            go.Scatter(
                x=date_series,y=dfSWE['max'],
                legendgroup='SWEcentiles',name=r'SWE Stats',
                visible=True,line=dict(width=0),connectgaps=True,
                fillcolor='rgba(1,0,237,0.15)',
                fill='tonexty',showlegend=True,hoverinfo='none'
            ),
            go.Scatter(
                x=date_series,y=dfQ['max'],yaxis='y2',
                legendgroup='Qcentiles',name=r'Q Stats', visible=True,
                line=dict(width=2, color='rgba(100,100,100,0.25)', dash='dash'),
                connectgaps=True, fillcolor='rgba(100,100,100,0.25)',
                fill='tonexty', showlegend=True, hoverinfo='none'
            )
        ]
    )
    
    trace.extend(
        [
            go.Scatter(
                x=date_series, y=dfSWE['50th'], name=r'Median', 
                visible=True, hovertext='in. SWE', connectgaps=True,
                line=dict(color='rgba(0,237,0,0.4)')
            ),
            go.Scatter(
                x=date_series, y=dfQ['50th'], name=r'Median', yaxis='y2',
                visible=True, hovertext='cfs',connectgaps=True,
                line=dict(color='rgba(0,237,0,0.4)', dash='dash')
            )
        ]
    )
 
    annoSites = (
        f"<sup>*</sup> # of sites does not meet basin threshold. "
        f"Data from this year will not for use in calculation of statistics<br>"
        # f'Sites used in SWE average:{", ".join(site_anno)}'
        f'Updated: {dt.now():"%A, %b %d, %Y @ %H %p PST"}'
    )

    layout = go.Layout(
        template='plotly_white',
        images= [dict(
            source=get_bor_seal(),
            xref="paper",
            yref="paper",
            x= 0,
            y= 0.9,
            xanchor="left", 
            yanchor="bottom",
            sizex= 0.4,
            sizey= 0.1,
            opacity= 0.5,
            layer= "above"
        )],
        annotations=[
            dict(
                font=dict(size=10), text=annoSites, xanchor='left',
                x=0,y=-0.2, yanchor='top', yref='paper', xref='paper',
                align='left', showarrow=False
            ),
            dict(
                font=dict(size=10), text=sites_link, x=1.105, y=1, 
                yref='paper', xref='paper', align='left', xanchor="left", 
                yanchor="bottom", showarrow=False
            ),
        ],    
        legend=dict(
            traceorder='reversed', tracegroupgap=1, bordercolor='#E2E2E2',
            borderwidth=2, x=1.1
        ),
        showlegend = True, title=f'Snow to Flow Relationship for {siteName}',
        autosize=True,
        margin=go.layout.Margin(
            l=50,
            r=50,
            b=50,
            t=50,
            pad=5
        ),
        yaxis=dict(
            title=r'Snow Water Equivalent (in.)', hoverformat='.1f',
            tickformat="0f", range=[0, np.max(dfSWE['max']*2)],
            gridcolor='#e8ece6', linecolor='#e8ece6'
        ),
        yaxis2=dict(
            title=r'Q (cfs)',overlaying='y',hoverformat='0f',
            side='right',anchor='free',rangemode='nonnegative',
            position=1,tickformat="0f",tick0=0
        ),
        xaxis=dict(
            range=sliderDates,
            tickformat="%b %e",
            rangeselector=dict(
                x=1, xanchor='right', y=1, yanchor='top',
                buttons=list(
                    [
                        dict(count=9, label='Jan', step='month', stepmode='todate'),
                        dict(count=6, label='Apr', step='month', stepmode='todate'),
                        dict(count=3, label='July', step='month', stepmode='todate'),
                        dict(label='WY', step='all')
                    ]
                )
            ),
            rangeslider=dict(thickness=0.1),
            type='date'
        )
    )
    updatemenus = get_log_scale_dd()
    layout['updatemenus'] = updatemenus      
    return {
        'data': trace,
        'layout': layout
    }
    
if __name__ == '__main__':
    
    import sys
    import json
    import argparse
    
    cli_desc = 'Creates snow to flow charts'
    parser = argparse.ArgumentParser(description=cli_desc)
    parser.add_argument("-V", "--version", help="show program version", action="store_true")
    parser.add_argument("-U", "--update", help="Update forecast equations from NRCS webservice.", action="store_true")
    parser.add_argument("-w", "--workers", help="Set how many i/o threads to use when updating forecast equations (max of 8)")
    parser.add_argument("-n", "--nav", help="Create nav.html after creating charts", action="store_true")
    parser.add_argument("-m", "--map", help="Create site_map.html after creating charts", action="store_true")
    parser.add_argument("-e", "--export", help="Export path for charts")
    parser.add_argument("-c", "--config", help="Provide path or name of config file in config folder. Defaults to all_hucs.json")
    
    args = parser.parse_args()
    
    if args.version:
        print('stf_nav.py v1.0')
    this_dir = path.dirname(path.abspath(__file__))
    logger = create_log(path.join(this_dir, 'stf_charts.log'))
    awdb = create_awdb()
    
    if args.update:
        workers = 1
        if args.workers:
            workers = 8
            if str(args.workers).isdigit():
                if int(args.workers) <= 8:
                    workers = int(args.workers)
        updt_frcst_eqs(awdb=awdb, logger=logger, indent=None, workers=workers)
        sys.exit(0)
        
    if args.export:
        if path.isdir(args.export):
            export_path = args.export
        else:
            print(f'\nInvalid export path - {args.export}')
            sys.exit(0)
    else:
        export_path = path.join(this_dir, 'charts')
        
    if args.config:
        if path.exists(args.config) and args.config.lower().endswith('.json'):
            config_path = args.config
        elif path.exists(path.join(this_dir, 'config', args.config)):
            config_path = path.join(this_dir, 'config', args.config)
        else:
            print('Invalid config path/file - {args.config}')
            sys.exit(0)
    else:
        config_path = path.join(this_dir, 'config', 'all_hucs.json')
    
    s_time = dt.now()
    s_time_str = s_time.strftime('%x %X')
    print_and_log(
        f'Starting Snow to Flow Chart generation at {s_time_str}\n'
        f'  Using configuration located: {config_path}\n'
        f'  Exporting charts to: {export_path}\n',
        logger
    )
    with open(config_path, 'r') as config:
        huc_dict = json.load(config)

    hucs = huc_dict.keys()
    swe_meta = r_get(f'{NRCS_DATA_URL}/metadata/WTEQ/metadata.json').json()
    all_frcsts = get_frcsts(huc='all', awdb=awdb, logger=logger)
    all_frcst_trips = [x['stationTriplet'] for x in all_frcsts if isActive(x)]
    for huc in hucs: 
        print_and_log(
            f'Working on forecasts in {huc_dict[huc]} - HUC {huc}',
            logger
        )
        frcsts = get_frcsts(huc=huc, awdb=awdb, logger=logger)
        frcst_triplets = [x['stationTriplet'] for x in frcsts if isActive(x)]
        if not frcst_triplets:
            continue
        for frcst in frcsts:
            bt = time.time()
            site_name = frcst['name']
            frcst_triplet = frcst['stationTriplet']
            huc_folder_dir = path.join(export_path, huc_dict[huc])
            makedirs(huc_folder_dir, exist_ok=True)
            plot_name = path.join(huc_folder_dir, site_name + r'.html')
            img_name = f'{site_name}_swe_Q'
            
            try:
                chart_data = updtChart(
                    frcstTriplet=frcst_triplet, 
                    siteName=site_name, 
                    swe_meta=swe_meta,
                    all_frcst_trips=all_frcst_trips,
                    awdb=awdb,
                    logger=logger
                )

                if not type(chart_data) == str:
                    fig = go.Figure(chart_data)
                    py.plot(
                        fig, 
                        filename=plot_name, 
                        auto_open=False,
                        include_plotlyjs=get_plotly_js(),
                        config=get_plot_config(img_name),
                        validate=False
                    )
                    flavicon = (
                        f'<link rel="shortcut icon" '
                        f'href="{get_favicon()}"></head>'
                    )
                    with open(plot_name, 'r') as html_file:
                        chart_file_str = html_file.read()
            
                    with open(plot_name, 'w') as html_file:
                        html_file.write(
                            chart_file_str.replace(r'</head>', flavicon)
                        )
                else:
                    print_and_log(
                        f'    {chart_data} - No chart created!',
                        logger
                    )
            except Exception as err:
                print_and_log(
                    f'    Something went wrong, no chart created - {err}',
                    logger
                )
            print_and_log(
                f'    chart created in {round(time.time()-bt,2)} seconds', 
                logger
            )
    
    if args.nav:
        nav_out = create_nav(export_path, nav_filename='nav.html')
        print_and_log(nav_out, logger)
    
    if args.map:
        df_meta = pd.DataFrame(all_frcsts)
        print_and_log(create_map(df_meta, export_path, huc_dict))
        
    e_time = dt.now()
    e_time_str = e_time.strftime('%X %x')
    d_time = ':'.join(str(e_time-s_time).split(':')[:2])
    print_and_log(
        f'Finished Snow to Flow Chart generation at {e_time_str}\n'
        f'Elapsed time: {d_time}',
        logger
    )
    