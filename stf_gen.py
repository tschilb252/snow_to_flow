# -*- coding: utf-8 -*-
"""
Created on Fri Feb 16 07:40:44 2018

@author: Beau.Uriona
"""

import time
from os import path, makedirs
from zeep import Client
from zeep.transports import Transport
from zeep.cache import InMemoryCache
from zeep import helpers
from requests import get as r_get
import datetime
import plotly.graph_objs as go
import plotly.offline as py
import numpy as np
import pandas as pd
from itertools import chain
import random
import warnings
from sft_utils import padMissingData, get_plot_config, get_bor_seal
from sft_utils import get_favicon, get_plotly_js, getSWEsites, getUpstreamUSGS
from stf_nav import create_nav

this_dir = path.dirname(path.abspath(__file__))

nrcs_data_url = r'https://www.nrcs.usda.gov/Internet/WCIS/sitedata/DAILY'
wsdl = r"https://wcc.sc.egov.usda.gov/awdbWebService/services?WSDL"
transport = Transport(timeout=300,cache=InMemoryCache())
awdb = Client(wsdl=wsdl,transport=transport).service
serialize =  helpers.serialize_object
dt = datetime.datetime
date = datetime.date
today = dt.utcnow() - datetime.timedelta(hours=8)
wsdl = r'https://wcc.sc.egov.usda.gov/awdbWebService/services?WSDL'

def updtChart(forecast_triplet, siteName, swe_meta):
    print('Snow-Runoff Chart for ' + siteName)
    sDate = date(1900, 10, 1).strftime("%Y-%m-%d")
    eDate = today.date().strftime("%Y-%m-%d 00:00:00")
    equation = serialize(awdb.getForecastEquations(forecast_triplet))
    terms = [j['equationTerms'] for j in equation]
    swe_trips = getSWEsites(terms)
    upstream_trips = getUpstreamUSGS(terms)
    for trip in upstream_trips:
        equation = serialize(awdb.getForecastEquations(trip))
        terms = [j['equationTerms'] for j in equation]
        swe_trips.extend(getSWEsites(terms))
        upstream_trips.extend(getUpstreamUSGS(terms))
        upstream_trips[:] = set(upstream_trips)
    swe_trips[:] = set(swe_trips)

    if not swe_trips:
        return None

    meta = [x for x in swe_meta if x['stationTriplet'] in swe_trips] 
    url_prefix = r"<a href='https://wcc.sc.egov.usda.gov/nwcc/site?sitenum="
    site_anno = ["{}{}'>{} ({})</a>".format(url_prefix,x['stationTriplet'].split(':')[0],
                 x['name'],
                 x['stationTriplet'].split(':')[1]) for x in meta]
    site_anno[:] = ['<br>' + x if i % 8 == 0 else x for i,x in enumerate(site_anno)]
    sweData = []
    for swe_trip in swe_trips:
        swe_url = f'{nrcs_data_url}/WTEQ/{swe_trip.replace(":", "_")}.json'
        swe_results = r_get(swe_url)
        if swe_results.status_code == 200:
            sweData.append(swe_results.json())
        else:
            sweData = serialize(awdb.getData(
                swe_trips,'WTEQ', 1, None, 'DAILY', False, sDate, eDate, True)
            )
            break

    date_series = [date(2015,10,1) + datetime.timedelta(days=x)
                    for x in range(0, 366)]
    
    beginDateDict = {}
    for siteMeta in meta:
        beginDateDict.update(
                {str(siteMeta['stationTriplet']) : 
                    dt.strptime(str(siteMeta['beginDate']),
                                "%Y-%m-%d %H:%M:%S")}) 
    
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
            padMissingData(dataSite,sDate,eDate)
            
    plotData = [np.array(x['values'], dtype=np.float) for x in sweData]
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        basinPlotData = list(np.nanmean(
                np.array([i for i in plotData]), axis=0))

    PORplotData = list([basinPlotData[i:i+366] 
                    for i in range(0,len(basinPlotData),366)])

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
        sliderDates = list(chain([(date_series[0])] + 
                                      [date_series[-1]]))
    else:
        sliderDates = list(chain([(date_series[0])] + [date_series[-1]]))
    
    dfSWE ={'min': minData,
            '10th': lowestData,
            '30th': lowData,
            '50th': medianData,
            '70th': highData,
            '90th': highestData,
            'max': maxData}
    
    for i, eachYear in enumerate(allButCurrWY):
        dfSWE[str(sYear + i + 1)] = eachYear
    
    PORplotData[-1].extend([np.nan]*(366-len(PORplotData[-1])))
    dfSWE[str(eDate[:4])] = PORplotData[-1]
    dfSWE = pd.DataFrame(dfSWE)
    
    jDay = dfSWE[str(eDate[:4])].last_valid_index()
    jDayData = dfSWE.iloc[jDay]
    dropCols = [i for i in dfSWE.columns.tolist() if not i.isdigit()]
    jDayData.drop(dropCols,inplace=True)
    jDayData.sort_values(inplace=True)
    maxData = dfSWE.max(axis=0)
    maxData.drop(dropCols,inplace=True)
    maxData.sort_values(inplace=True)
    flow_url = f'{nrcs_data_url}/SRDOO/{forecast_triplet.replace(":", "_")}.json'
    flow_results = r_get(flow_url)
    if flow_results.status_code == 200:
        flowData = flow_results.json()
    else:
        flowData = serialize(awdb.getData(
            forecast_triplet, 'SRDOO', 1, None, 'DAILY', False, sDate, eDate, 
            True)
        )[0]
    
    padMissingData(flowData,sDate,eDate)
            
    plotData = np.array(flowData['values'], dtype=np.float)
    
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
   
    dfQ ={'min': minData,
            '10th': lowestData,
            '30th': lowData,
            '50th': medianData,
            '70th': highData,
            '90th': highestData,
            'max': maxData}
    
    for i, eachYear in enumerate(allButCurrWY):
        if str(sYear + i + 1) in dfSWE.columns:
            dfQ[str(sYear + i + 1)] = eachYear
    
    PORplotData[-1].extend([np.nan]*(366-len(PORplotData[-1])))
    dfQ[str(eDate[:4])] = PORplotData[-1]
    dfQ = pd.DataFrame(dfQ)
    
    trace = []
    listOfYears = [int(x) for x in dfSWE.axes[1] if x.isdigit()]
    colScheme = ['rgb(41,111,99)',
                 'rgb(155,155,79)',
                 'rgb(90,86,118)',
                 'rgb(151,28,114)',
                 'rgb(28,77,111)',
                 'rgb(153,80,0)',
                 'rgb(79,122,5)',
                 'rgb(152,105,129)',
                 'rgb(117,117,117)',
                 'rgb(88,28,89)']
    
    if not dfSWE.empty:
        for i in dfSWE:
            if i.isdigit() and int(i) == np.max(listOfYears):
                trace.extend(
                        [go.Scatter(
                                x=date_series,y=dfSWE[i],showlegend=True,
                                name=str(i),legendgroup=str(i),hovertext='SWE',
                                visible=True,connectgaps=True,
                                line=dict(color='rgb(0,0,0)')),
                        go.Scatter(
                                x=date_series,y=dfQ[i],yaxis='y2',hovertext='cfs',
                                name=str(i),legendgroup=str(i),
                                visible=True,connectgaps=True,showlegend=False,
                                line=dict(color='rgb(0,0,0)',dash='dash'))])
            elif i.isdigit():
                randCol = int(random.uniform(0,10))
                trace.extend(
                        [go.Scatter(
                                x=date_series,legendgroup=str(i),
                                line=dict(color=colScheme[randCol]),hovertext='SWE',
                                y=dfSWE[i],name=str(i),showlegend=True,
                                visible='legendonly',connectgaps=True),
                        go.Scatter(
                                x=date_series,legendgroup=str(i),showlegend=False,
                                y=dfQ[i],name=str(i),yaxis='y2',
                                visible='legendonly', connectgaps=True,hovertext='cfs',
                                line=dict(dash='dash',color=colScheme[randCol]))])
        trace.extend(
                [go.Scatter(x=date_series,y=dfSWE['min'],
                            legendgroup='SWEcentiles',name=r'Min',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(237,0,1,0.15)',
                            fill='none',showlegend=False,
                            hoverinfo='none'),
                go.Scatter(x=date_series,y=dfQ['min'],yaxis='y2',
                            legendgroup='Qcentiles',name=r'Min',
                            visible=True,#mode='line',
                            line=dict(width=2,color='rgba(100,100,100,0.25)',
                                      dash='dash'),
                            connectgaps=True,
                            fill='none',showlegend=False,
                            hoverinfo='none'),])       
        trace.extend(
                [go.Scatter(x=date_series,y=dfSWE['10th'],
                            legendgroup='SWEcentiles',name=r'10%',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(237,0,1,0.15)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none'),
                go.Scatter(x=date_series,y=dfQ['10th'],yaxis='y2',
                            legendgroup='Qcentiles',name=r'10%',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(100,100,100,0.25)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none')])

        trace.extend(
                [go.Scatter(x=date_series,y=dfSWE['30th'],
                            legendgroup='SWEcentiles',name=r'30%',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(237,237,0,0.15)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none'),
                go.Scatter(x=date_series,y=dfQ['30th'],yaxis='y2',
                            legendgroup='Qcentiles',name=r'30%',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(175,175,175,0.25)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none')])

        trace.extend(
                [go.Scatter(x=date_series,y=dfSWE['70th'],
                            legendgroup='SWEcentiles',
                            name=r'70%',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(115,237,115,0.15)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none'),
                go.Scatter(x=date_series,y=dfQ['70th'],yaxis='y2',
                            legendgroup='Qcentiles',
                            name=r'70%.',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(250,250,250,0.25)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none')])
        trace.extend(
                [go.Scatter(x=date_series,y=dfSWE['90th'],
                            legendgroup='SWEcentiles',connectgaps=True,
                            name=r'90%',visible=True,
                            #mode='line',
                            line=dict(width=0),
                            fillcolor='rgba(0,237,237,0.15)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none'),
                go.Scatter(x=date_series,y=dfQ['90th'],yaxis='y2',
                            legendgroup='Qcentiles',connectgaps=True,
                            name=r'90%',visible=True,
                            #mode='line',
                            line=dict(width=0),
                            fillcolor='rgba(175,175,175,0.25)',
                            fill='tonexty',showlegend=False,
                            hoverinfo='none')])
        trace.extend(
                [go.Scatter(x=date_series,y=dfSWE['max'],
                            legendgroup='SWEcentiles',name=r'SWE Stats',
                            visible=True,#mode='line',
                            line=dict(width=0),connectgaps=True,
                            fillcolor='rgba(1,0,237,0.15)',
                            fill='tonexty',showlegend=True,
                            hoverinfo='none'),
                go.Scatter(x=date_series,y=dfQ['max'],yaxis='y2',
                            legendgroup='Qcentiles',name=r'Q Stats',
                            visible=True,#mode='line',
                            line=dict(width=2,color='rgba(100,100,100,0.25)',
                                      dash='dash'),
                            connectgaps=True,
                            fillcolor='rgba(100,100,100,0.25)',
                            fill='tonexty',showlegend=True,
                            hoverinfo='none')])
#    if basinPlotNormData:
#        trace.extend(
#                [go.Scatter(x=date_series,
#                            y=basinPlotNormData,
#                            name=r"Normal ('81-'10)",connectgaps=True,
#                            visible=True,hoverinfo='none',
#                            line=dict(color='rgba(0,237,0,0.4)'))])
#    
#    if meanData:
#        if basinPlotNormData:
        trace.extend(
                [go.Scatter(x=date_series,
                            y=dfSWE['50th'],name=r'SWE Norm',
                            visible=True,#'legendonly',
                            hoverinfo='none',connectgaps=True,
                            line=dict(color='rgba(0,237,0,0.4)')),
                go.Scatter(x=date_series,
                            y=dfQ['50th'],name=r'Q Norm',yaxis='y2',
                            visible=True,#'legendonly',
                            hoverinfo='none',connectgaps=True,
                            line=dict(color='rgba(0,237,0,0.4)',
                                      dash='dash'))])
#        else:
#            trace.extend(
#                    [go.Scatter(x=date_series,y=meanData,
#                                name=r'Normal (POR)',connectgaps=True,
#                                visible=True,hoverinfo='none',
#                                line=dict(color='rgba(0,237,0,0.4)'))])
#    
    annoText = ''#str(r"Statistical shading breaks at 10th, 30th, 50th, 70th, and 90th Percentiles<br>Normal ('81-'10) - Official median calculated from 1981 thru 2010 data<br>Normal (POR) - Unofficial mean calculated from Period of Record data <br>For more information visit: <a href='https://www.wcc.nrcs.usda.gov/normals/30year_normals_data.htm'>30 year normals calculation description</a>")
    annoSites = 'Sites used in SWE average:' + ', '.join(site_anno)
#    asterisk = ''
#    if not basinPlotNormData: 
#        basinPlotNormData = meanData
#        annoText = annoText + '<br>*POR data used to calculate Normals since no published 30-year normals available for this basin'
#        asterisk = '*'
#    if basinPlotNormData[jDay] == 0:
#        perNorm = r'N/A'
#    else:
#        perNorm = str('{0:g}'.format(100*round(
#                PORplotData[-1][jDay]/basinPlotNormData[jDay],2)))
#    perPeak = str('{0:g}'.format(100*round(
#            PORplotData[-1][jDay]/max(basinPlotNormData),2)))
#    if not math.isnan(PORplotData[-1][jDay]):
#        centile = ordinal(int(round(
#                stats.percentileofscore(
#                        statsData[jDay],PORplotData[-1][jDay]),0)))
#    else:
#        centile = 'N/A'
#        
#    dayOfPeak = basinPlotNormData.index(max(basinPlotNormData))
#    if jDay > dayOfPeak:
#        tense = r'Since'
#    else:
#        tense = r'Until'
#    daysToPeak = str(abs(jDay-dayOfPeak))
    annoData = ''#str(r"Current" + asterisk + ":<br>% of Normal - " + 
#                   perNorm + r"%<br>" +
#                   r"% Normal Peak - " + perPeak + r"%<br>" +
#                   r"Days " + tense + 
#                   r" Normal Peak - " + daysToPeak + r"<br>"                      
#                   r"Percentile Rank- " + centile)
    
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
        annotations=[dict(
            font=dict(size=10),
            text=annoText,
            x=0,y=-0.2, yanchor='top',
            yref='paper',xref='paper',
            align='left',
            showarrow=False),
            dict(font=dict(size=10),
            text=annoSites,xanchor='left',
            x=0,y=-0.2, yanchor='top',
            yref='paper',xref='paper',
            align='left',
            showarrow=False),
            dict(font=dict(size=10),
            text=annoData,
            x=0,y=0.9, 
            yref='paper',xref='paper',
            align='left',
            xanchor="left", yanchor="top",
            showarrow=False)],    
        legend=dict(traceorder='reversed',tracegroupgap=1,
                    bordercolor='#E2E2E2',borderwidth=2,
                    x=1.15),
        showlegend = True,
        title='SWE-Q Relationship for ' + str(siteName),
        height=622, width=1200, autosize=False,
        yaxis=dict(title=r'Snow Water Equivalent (in.)',hoverformat='.1f',
                   tickformat="0f",range=[0,np.max(dfSWE['max']*2)]),
        yaxis2=dict(title=r'Q (cfs)',overlaying='y',hoverformat='0f',
                    side='right',anchor='free',rangemode='nonnegative',
                    position=1,tickformat="0f",tick0=0),
        xaxis=dict(
            range=sliderDates,
            tickformat="%b %e",
            rangeselector=dict(
                buttons=list([
                    dict(count=9,
                         label='Jan',
                         step='month',
                         stepmode='todate'),
                    dict(count=6,
                         label='Apr',
                         step='month',
                         stepmode='todate'),
                    dict(count=3,
                         label='July',
                         step='month',
                         stepmode='todate'),
                    dict(label='WY', step='all')
                ])
            ),
            rangeslider=dict(thickness=0.1),
            type='date'
        )
    )
    updatemenus= list([
                     dict(
                        buttons=list([
                            dict(args=['yaxis2',dict(type='linear',
                                                    rangemode='nonnegative',
                                                    title=r'Q (cfs)',
                                                    overlaying='y',
                                                    side='right',
                                                    anchor='free',
                                                    position=1,
                                                    tickformat="f",
                                                    tick0=0)],
                                label='linear',
                                method='relayout'
                            ),
                            dict(args=['yaxis2',dict(type='log',
                                                    rangemode='nonnegative',
                                                    title=r'Q (cfs)',
                                                    overlaying='y',
                                                    side='right',
                                                    anchor='free',
                                                    position=1,
                                                    tickformat="f",
                                                    tick0=1,dtick='D2')],
                                label='log',
                                method='relayout'
                            )
                        ]),
                        direction='left',
                        x=0.9,y=1.1,xanchor='left',yanchor='top',
                        showactive = True,
                        type = 'buttons',
                    )
                    ])
    layout['updatemenus'] = updatemenus      
    return {'data': trace,
            'layout': layout}
    
if __name__ == '__main__':
    
    # import sys
    import argparse
    
    cli_desc = 'Creates snow to flow charts'
    parser = argparse.ArgumentParser(description=cli_desc)
    parser.add_argument("-V", "--version", help="show program version", action="store_true")
    parser.add_argument("-n", "--nav", help="path to create nav.html for")
    args = parser.parse_args()
    
    if args.version:
        print('stf_nav.py v1.0')
        
    huc_dict = {
        1405: 'yampa', 1408: 'san_juan', 1404: 'upper_green', 1402: 'gunnison', 
        14070006: 'powell', 1602: 'wasatch_front'
    }

    hucs = huc_dict.keys()
    swe_meta = r_get(r'https://www.nrcs.usda.gov/Internet/WCIS/sitedata/metadata/WTEQ/metadata.json').json()
    for huc in hucs: 
        forecasts = serialize(
            awdb.getForecastPoints('*', '*', '*', '*', f'{huc}*', '*', True)
        )  
        forecast_triplets = [x['stationTriplet'] for x in forecasts]
        for forecast in forecasts:       
            bt = time.time()
            siteName = forecast['name']
            dirPath = path.join(this_dir, 'charts', huc_dict[huc])
            plotName = path.join(dirPath, siteName + r'.html')
            imgName = f'{siteName}_swe_Q.png'
            makedirs(dirPath, exist_ok=True)
            try:

                chartData = updtChart(forecast['stationTriplet'], siteName, swe_meta)
                if chartData:
                    fig = go.Figure(chartData)
                    py.plot(
                        fig, 
                        filename=plotName, 
                        auto_open=False,
                        include_plotlyjs=get_plotly_js(),
                        config=get_plot_config(imgName)
                    )
                    flavicon = (
                        f'<link rel="shortcut icon" '
                        f'href="{get_favicon()}"></head>'
                    )
                    with open(plotName, 'r') as html_file:
                        chart_file_str = html_file.read()
            
                    with open(plotName, 'w') as html_file:
                        html_file.write(chart_file_str.replace(r'</head>', flavicon))
                else:
                    print('  No Snotel sites used in forecast. No chart created!')
            except Exception as err:
                print(f'  Something went wrong, no chart created - {err}')
            print(f'  in {round(time.time()-bt,2)} seconds')
    
    if args.nav:
        create_nav(path.join(this_dir, 'charts'), nav_filename='nav.html')