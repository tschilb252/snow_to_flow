# -*- coding: utf-8 -*-
"""
Created on Thu May  2 06:33:43 2019

@author: buriona
"""

import os
from functools import reduce
from datetime import datetime as dt
from pathlib import Path
import pandas as pd
from stf_utils import get_favicon, get_bor_seal, get_bootstrap

BOR_FLAVICON = get_favicon()
BOR_SEAL = get_bor_seal()
bootstrap = get_bootstrap()
BOOTSTRAP_CSS = bootstrap['css']
BOOTSTRAP_JS = bootstrap['js']
JQUERY_JS = bootstrap['jquery']
POPPER_JS = bootstrap['popper']

def get_updt_str():
    return f'<i>Last updated: {dt.now().strftime("%x %X")}</i>'

HEADER_STR = f'''
<!DOCTYPE html>
<html>
    <head>
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <link rel="icon" href="{BOR_FLAVICON}">
          <link rel="stylesheet" href="{BOOTSTRAP_CSS}">
          <script src="{JQUERY_JS}"></script>
          <script src="{BOOTSTRAP_JS}"></script>
          <script src="{POPPER_JS}"></script>''' + '''
    <style>
        .dropdown-submenu {
          position: relative;
        }

        .dropdown-submenu .dropdown-menu {
          top: 0;
          left: 100%;
          margin-top: -1px;
        }
    </style>
    </head>
<body>
<div class="container">
''' + f'''
<img src="{BOR_SEAL}" style="width: 25%" class="img-responsive mx-auto d-block" alt="BOR Logo">
    <h2>Snow to Flow Navigator</h2><h6>{get_updt_str()}<h6>
    <button class="btn btn-outline-info btn-md">
    <a target="_blank" href="./site_map.html">
    <i class="fa fa-external-link" aria-hidden="true"></i>
    Map Based Navigation</a></button><br>
'''

log_btn = '<a href="./ff_gen.log" class="btn btn-success mt-3" role="button">LOG FILE</a>'
FOOTER_STR = '''
</div>
<script>
$(document).ready(function(){
  $('.dropdown-submenu a.test').on("click", function(e){
    $(this).next('ul').toggle();
    e.stopPropagation();
    e.preventDefault();
  });
});

</script>

</body>
</html>
'''

def remove_items(key_list, items_dict):
    for key in key_list:
        items_dict.pop(key, None)
    return items_dict

def write_file(write_dict):
    for filepath, html_str in write_dict.items():
        with open(filepath, 'w') as file:
            file.write(html_str)

def get_folders(rootdir):
    dir_dict = {}
    rootdir = rootdir.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    for walk_path, dirs, files in os.walk(rootdir):
        folders = walk_path[start:].split(os.sep)
        subdir = dict.fromkeys(files)
        parent = reduce(dict.get, folders[:-1], dir_dict)
        parent[folders[-1]] = subdir
    return dir_dict[list(dir_dict.keys())[0]]

def get_button(button_label, dropdown_str):
    nl = '\n'
    drop_down_str = (
        f'    <div class="dropdown">{nl}'
        f'        <button class="btn btn-outline-primary btn-lg '
        f'dropdown-toggle mt-3" type="button" '
        f'data-toggle="dropdown" aria-pressed="false" '
        f'autocomplete="on">{button_label.upper()}'
        f'<span class="caret"></span></button>{nl}'
        f'        <ul class="dropdown-menu">{nl}'
        f'            {dropdown_str}{nl}'
        f'        </ul>{nl}'
        f'    </div>{nl}'
    )

    return drop_down_str

def get_menu_entry(label, href):
    nl = '\n'
    return (
        f'<li><a tabindex="0" href="{href}">'
        f'<b><i>{label}</b></i></a></li>{nl}'
    )

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]
        
def create_nav(data_dir, nav_filename='nav.html'):
    nl = '\n'
    try:
        walk_dict = get_folders(data_dir)
        to_remove = ['.git', 'assets']
        walk_dict = remove_items(to_remove, walk_dict)
        button_str_list = []
        for button_label, dd_items in sorted(walk_dict.items()):
            if dd_items:
                button_path = Path('.', button_label)
                site_menu_list = []
                site_name_dict = {
                    str(k).replace('.html',''): str(k) for k, v in dd_items.items()
                }
                for label, filename in site_name_dict.items():
                    menu_path = Path(button_path, filename)
                    site_menu_list.append(get_menu_entry(label, menu_path))
                
                sites_dd_str = '\n'.join(site_menu_list)
                folder_button = get_button(
                    button_label.replace('_', ' '),
                    sites_dd_str
                )
                button_str_list.append(folder_button)

        buttons_str = '\n'.join([i for i in button_str_list if i])

        nl = '\n'
        nav_html_str = (
            f'{HEADER_STR}{nl}{buttons_str}{nl}{FOOTER_STR}'
        )
        write_nav_dict = {
            Path(data_dir, nav_filename): nav_html_str,
            Path(data_dir, 'index.html'): nav_html_str
        }
        write_file(write_nav_dict)
    
        return f'\nNavigation file(s) created for files in {data_dir}\n'
    
    except Exception as err:
        return f'\nFailed to created navigation file(s) in {data_dir} - {err}'

if __name__ == '__main__':

    import sys
    import argparse
    from os import path
    
    cli_desc = 'Creates HDB data portal flat files using schema defined in ff_config.json'
    parser = argparse.ArgumentParser(description=cli_desc)
    parser.add_argument("-V", "--version", help="show program version", action="store_true")
    parser.add_argument("-p", "--path", help="path to create nav.html for")
    
    
    args = parser.parse_args()
    
    this_dir = os.path.dirname(os.path.realpath(__file__))
        
    if args.version:
        print('stf_nav.py v1.0')
    
    if args.path:
        data_dir = Path(args.path).resolve().as_posix()
        if not path.exists(data_dir):
            print(f'{data_dir} does not exist, can not save files there, try again.')
            sys.exit(0)
    else:      
        data_dir = os.path.join(this_dir, 'charts')

    sys_out = create_nav(data_dir)
    print(sys_out)
