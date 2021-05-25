# -*- coding: utf-8 -*-
"""
Created on Fri May 31 07:43:40 2019

@author: buriona
"""

from os import path
from datetime import datetime as dt
import folium
from folium.plugins import FloatImage, MousePosition
import pandas as pd
from stf_utils import get_fa_icon, get_obj_type_name, create_awdb
from stf_utils import add_optional_tilesets, add_huc_layer
from stf_utils import clean_coords, add_huc_chropleth, get_colormap
from stf_utils import get_bor_seal, get_favicon, get_icon_color
from stf_utils import get_default_js, get_default_css

pd.options.mode.chained_assignment = None

default_js = get_default_js()
default_css = get_default_css()
folium.folium.Map.default_js = default_js
folium.folium.Map.default_css = default_css

def get_bounds(meta):
    meta.drop_duplicates(subset='stationTriplet', inplace=True)
    lats = []
    longs = []
    for index, row in meta.iterrows():
        try:
            lat = float(row['latitude'])
            lon = float(row['longitude'])
            if 0 <= lat <= 180:
                lats.append(lat)
            if -180 <= lon <= 0:
                longs.append(lon)
        except (ValueError, TypeError):
            pass

    max_lat = max(lats)
    max_long = -1 * max([abs(i) for i in longs])
    min_lat = min(lats)
    min_long = -1 * min([abs(i) for i in longs])
    return [(min_lat, max_long), (max_lat, min_long)]

def get_embed(href):
    embed = (
        f'<div class="container embed-responsive embed-responsive-16by9" style="overflow: hidden; height: 622px; width: 1200px;">'
        f'<iframe scrolling="no" class="embed-responsive-item" src="{href}" allowfullscreen></iframe>'
        f'</div>'
    )   
    return embed

def add_markers(sitetype_map, meta, huc_dict, data_dir):
    meta.drop_duplicates(subset='stationTriplet', inplace=True)
    NRCS_PREFIX = r'https://wcc.sc.egov.usda.gov/reportGenerator/view/customMultiTimeSeriesGroupByStationReport/daily/start_of_period'
    NRCS_SUFFIX = r'%7Cid=%22%22%7Cname/0,0/name,stationId,state.name,network.name,elevation,latitude,longitude,huc12.huc,huc12.hucName,reportTimeZone.offset,dco.code,actonId,shefId,inServiceDate,outServiceDate'
    for index, row in meta.iterrows():
        try:
            triplet = row['stationTriplet']
            triplet_arr = triplet.split(':')
            site_id = triplet_arr[0]
            network = triplet_arr[2]
            site_name = row['name']
            obj_type = network
            if 'inflow' in site_name.lower() or ' res' in site_name.lower() or ' dam' in site_name.lower():
                obj_type = 'BOR'
            lat = float(row['latitude'])
            lon = float(row['longitude'])
            lat_long = [lat, lon]
            elev = row.get('elevation', 'N/A').split('.')[0]
            huc = str(row['huc'])[:12]
            huc_folder = huc_dict.get(huc[:4], '')
            
            href = f'./{huc_folder}/{site_name}.html'
            if not path.exists(path.join(data_dir, href[2:])):
                continue
            nrcs_href = f'{NRCS_PREFIX}/{triplet}{NRCS_SUFFIX}'
            embed = f'''<div class="container embed-responsive embed-responsive-16by9">
                  <embed class="embed-responsive-item" src="{href}"></embed>
                </div>'''
            embed = get_embed(href)
            icon = get_fa_icon(obj_type, source='awdb')

            color = get_icon_color(obj_type, source='awdb')
            popup_html = (
                f'<div class="container">'
                f'<div class="row justify-content-center">'
                f'{embed}</div>'
                f'<div class="row justify-content-around">'
                f'<div class="col-5">'
                f'<button class="btn btn-outline-info btn-sm">'
                f'<a target="_blank" href="{href}">'
                f'<i class="fa fa-external-link" aria-hidden="true"></i>'
                f'&nbsp;Expand to new window.</a></button></div>'
                f'<div class="col-5">'
                f'<button class="btn btn-outline-secondary btn-sm">'
                f'<a target="_blank" href="{nrcs_href}"><span>'
                f'<i class="fa fa-external-link" aria-hidden="true"></i>&nbsp;'
                f'Latitude: {round(lat, 3)}, '
                f'Longitude: {round(lon, 3)}, '
                f"Elevation: {elev}'"
                f'</span></a></button></div></div></div>'
            )
            popup = folium.map.Popup(
                html=popup_html,
                max_width='75%'
            )
            folium.Marker(
                location=lat_long,
                popup=popup,
                tooltip=site_name,
                icon=folium.Icon(icon=icon, prefix='fa', color=color)
            ).add_to(sitetype_map)
        except (ValueError, TypeError) as err:
            if site_name:
                print(f'    Could not add {site_name} to site map - {err}')
            else:
                print(f'    Could not add {site_id} to site map, missing site_name')
            pass
        
def get_legend(obj_types=[], data_sources=[]):
    default_obj_types = [2,3,4,6,7,8,9,11]
    obj_types = list(set(obj_types + default_obj_types))
    update_date = dt.now().strftime('%B %d, %Y')
    obj_types_html = []
    for obj_type in obj_types:
        obj_name = get_obj_type_name(obj_type).title()
        obj_icon = get_fa_icon(obj_type).lower()
        obj_types_html.append(
            f'    <a class="dropdown-item" href="#">'
            f'      <i class="fa fa-{obj_icon}"></i>&nbsp {obj_name}'
            f'    </a>'
        )
    obj_types_html = '\n'.join(list(set(obj_types_html)))
    # default_data_sources = [
    #     'BOR', 'NRCS', 'USGS', 'COOP', 'CASS', 'CDEC', 'ACIS'
    # ]
    # data_sources = list(set(data_sources + default_data_sources))
    # data_sources_html = []
    # for data_source in data_sources:
    #     data_source_html.append(
    #         f'<i class="fa fa-map-marker" style="color:blue;"></i>&nbsp '
    #         f'<a href="https://www.usbr.gov/">BOR</a><br>'
    #     )
    # obj_types_html = '\n'.join(list(set(data_source_html)))
    legend_items = f'''
      <a class="dropdown-item" href="#">
        <b>Site Types</b>
      </a>
{obj_types_html}
      <div class="dropdown-divider"></div>
      <a class="dropdown-item" href="#">
        <b>Data Sources</b>
      </a>
      <a class="dropdown-item" href="https://www.usbr.gov/" target="_blank">
        <i class="fa fa-map-marker" style="color:blue;"></i>&nbsp BOR
      </a>
      <a class="dropdown-item" href="https://www.usgs.gov/" target="_blank">
        <span><i class="fa fa-map-marker" style="color:green;"></i>&nbsp USGS
      </a>
      <a class="dropdown-item" href="https://www.wcc.nrcs.usda.gov/" target="_blank">
        <i class="fa fa-map-marker" style="color:red"></i>&nbsp NRCS
      </a>
      <a class="dropdown-item" href="https://cdec.water.ca.gov/" target="_blank">
        <i class="fa fa-map-marker" style="color:orange;"></i>&nbsp CDEC
      <a class="dropdown-item" href="https://www2.gov.bc.ca" target="_blank">
        <i class="fa fa-map-marker" style="color:orange;"></i>&nbsp CASS
      </a>
      <a class="dropdown-item" href="https://www.weather.gov/coop/" target="_blank">
        <i class="fa fa-map-marker" style="color:grey"></i>&nbsp COOP
      </a>
      <a class="dropdown-item" href="https://www.rcc-acis.org/" target="_blank">
        <i class="fa fa-map-marker" style="color:beige"></i>&nbsp ACIS
      </a>
      <div class="dropdown-divider"></div>
      <a class="dropdown-item" href="#">
        Updated: {update_date}<br>
      </a>
    '''
    legend_dd = f'''
    <div class="dropdown show" style="position: fixed; top: 10px; left: 50px; z-index:9999;">
      <a class="btn btn-warning btn-lg dropdown-toggle" href="#" role="button" id="dropdownMenuLink" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
        Legend
      </a>
      <div class="dropdown-menu" aria-labelledby="dropdownMenuLink">
{legend_items}   
      </div>   
    </div>
  
  '''
    return legend_dd

def create_map(meta, data_dir, huc_dict):
    meta = meta.drop_duplicates(subset='stationTriplet')
    meta['latitude'] = clean_coords(meta['latitude'])
    meta['longitude'] = clean_coords(
        meta['longitude'], force_neg=True
    )

    sitetype_dir = path.join(data_dir)
    map_filename = f'site_map.html'
    map_path = path.join(sitetype_dir, map_filename)

    sitetype_map = folium.Map(tiles=None)
    bounds = get_bounds(meta.copy())
    if bounds:
        sitetype_map.fit_bounds(bounds)
        add_markers(sitetype_map, meta.copy(), huc_dict, data_dir)
        
        # for huc_level in ['2', '4', '6', '8']:
        #     show_layer = True if huc_level == '2' else False
        #     add_huc_layer(
        #         sitetype_map, 
        #         level=huc_level, 
        #         show=show_layer
        #     )
            # for data_type in ['swe', 'prec']:
            #     add_huc_chropleth(
            #         sitetype_map, 
            #         data_type=data_type, 
            #         show=False, 
            #         huc_level=huc_level
            #     )
        add_optional_tilesets(sitetype_map)
        folium.LayerControl('topleft').add_to(sitetype_map)
        FloatImage(
            get_bor_seal(orient='horz'),
            bottom=1,
            left=1
        ).add_to(sitetype_map)
        # get_colormap().add_to(sitetype_map)
        # MousePosition(prefix="Location: ").add_to(sitetype_map)
        legend = folium.Element(get_legend())
        sitetype_map.get_root().html.add_child(legend)
        sitetype_map.save(map_path)
        flavicon = (
            f'<link rel="shortcut icon" '
            f'href="{get_favicon()}"></head>'
        )
        with open(map_path, 'r') as html_file:
            chart_file_str = html_file.read()

        with open(map_path, 'w') as html_file:
            chart_file_str = chart_file_str.replace(r'</head>', flavicon)
            find_str = r'left:1%;'
            replace_str = (
                '''left:1%;
                    max-width:15%;
                    max-height:15%;
                    background-color:rgba(255,255,255,0.5);
                    border-radius: 10px;
                    padding: 10px;'''
            )
            chart_file_str = chart_file_str.replace(find_str, replace_str)
            find_str = (
                """.append("svg")
        .attr("id", 'legend')"""
            )
            replace_str = (
                '''.append("svg")
                     .attr("id", "legend")
                     .attr("style", "background-color:rgba(255,255,255,0.75);border-radius: 10px;")'''
            )
            chart_file_str = chart_file_str.replace(find_str, replace_str)
            html_file.write(chart_file_str)

        return f'  Created site map for {data_dir}'
    else:
        return '  Failed to create map for {data_dir}, no sites with coordinates'

if __name__ == '__main__':
    
    import sys
    import json
    import argparse
    from stf_gen import get_frcsts
    
    cli_desc = 'Creates site/folder leaflet map for accessing hydroData'
    parser = argparse.ArgumentParser(description=cli_desc)
    parser.add_argument("-V", "--version", help="show program version", action="store_true")
    parser.add_argument("-c", "--config", help="Path to stf charts config file", default='all_hucs.json')
    parser.add_argument("-p", "--path", help="Path to stf charts folder", default='charts')
    
    args = parser.parse_args()
    
    if args.version:
        print('ff_gen.py v1.0')
    
    this_dir = path.dirname(path.realpath(__file__))
    if path.isdir(path.join(this_dir, args.path)):
        chart_dir = path.join(this_dir, args.path)
    elif path.isdir(args.path):
        chart_dir = args.path
    else:
        print(f'Not a valid path - {args.path}')
        sys.exit(0)
    
    if args.config:
        if path.exists(args.config):
            config_path = args.config
        elif path.exists(path.join(this_dir, 'config', args.config)):
            config_path = path.join(this_dir, 'config', args.config)
        
    meta_json = get_frcsts(huc='all', awdb=create_awdb(), logger=None)
    meta = pd.DataFrame(meta_json)
    with open(config_path, 'r') as config:
        huc_dict = json.load(config)
        
    print(create_map(meta, chart_dir, huc_dict))
    