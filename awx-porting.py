#!/usr/bin/python3

import argparse
import requests
from urllib.parse import quote
import yaml, json


src_tower = { 'url': 'old-tower.example.com', 'usr': 'username', 'pwd': 'password', 'verifyssl': True }
dst_tower = { 'url': 'new-tower.example.com', 'usr': 'username', 'pwd': 'password', 'verifyssl': True }

standard_headers = { "Content-Type": "application/json" }

baseurls = {
    "inventory": "/api/v2/inventories/",
    "inventory_sources": "/api/v2/inventory_sources/",
    "groups": "/api/v2/groups/",
    "hosts": "/api/v2/hosts/",
    "job_template": "/api/v2/job_templates/",
    "project": "/api/v2/projects/",
    "credentials": "/api/v2/credentials/",
    "organization": "/api/v2/organizations/",
    "workflow_job_templates": "/api/v2/workflow_job_templates/",
    "workflow_job_template_nodes": "/api/v2/workflow_job_template_nodes/",
}

keys_to_keep = {
    "inventory": [
        'name', 'kind', 'description',
        'host_filter', 'variables', 'input_inventories', 'instance_groups', 
        'prevent_instance_group_fallback', 'request_timeout', 
    ],
    "inventory_sources": [
        'description', 'enabled_value', 'enabled_var', 'host_filter',
        'limit', 'name', 'overwrite', 'overwrite_vars', 'request_timeout',
        'scm_branch', 'source', 'source_path', 'source_vars', 'timeout',
        'update_cache_timeout', 'update_on_launch', 'verbosity'
    ],
    "groups": [
        'name', 'description',
        'preserve_existing_children', 'preserve_existing_hosts', 'request_timeout'
    ],
    "hosts": [
        'name', 'description', 'enabled', 'request_timeout'
    ],
    "job_template": [
        'name', 'description', 'job_type', 'playbook', 'scm_branch', 'forks', 'limit',
        'verbosity', '_extra_vars', 'job_tags', 'force_handlers',
        'skip_tags', 'start_at_task', 'timeout', 'use_fact_cache',
        'host_config_key', 'ask_scm_branch_on_launch',
        'ask_diff_mode_on_launch', 'ask_variables_on_launch', 'ask_limit_on_launch',
        'ask_tags_on_launch', 'ask_skip_tags_on_launch', 'ask_job_type_on_launch',
        'ask_verbosity_on_launch', 'ask_inventory_on_launch', 'ask_credential_on_launch',
        'survey_enabled', 'become_enabled', 'diff_mode', 'allow_simultaneous',
        'job_slice_count', 'webhook_service', 'webhook_credential', 'request_timeout'
    ],
    "workflow_job_templates": [
        'name', 'description', 'scm_branch', 'limit', 'survey_enabled', 
        '_extra_vars', 'ask_scm_branch_on_launch', 'ask_variables_on_launch', 'ask_limit_on_launch',
        'ask_skip_tags_on_launch', 'ask_tags_on_launch', 'ask_variables_on_launch', 
        'ask_inventory_on_launch', 'allow_simultaneous',
        'job_tags', 'request_timeout', 'skip_tags'
    ],
    "workflow_job_template_node": [
        'all_parents_must_converge', 'identifier'
    ],
    "credentials": [
        'name', 'description', 'credential_type', 'organization'
    ]
}

keys_to_map = {
    "inventory": [ ],
    "groups": [ 'inventory' ],
    "hosts": [ 'inventory' ],
    "job_template": [ 'inventory', 'project' ],
    "workflow_job_templates": [ 'inventory', ],
    "credentials": [ 'inventory' ],
}

keys_not_to_search_for = [
    'extra_vars', 'host_config_key', 'inputs', 'scm_branch'
]

related_asset_types = {
    "job_template": ['credentials', 'survey_spec'],
    "workflow_job_templates": ['workflow_nodes'],
    "hosts": ["groups"]
}

related_asset_query_keys = {
    "hosts": ['inventory'],
    # "groups": ['name', 'inventory']
}

asset_cache = {}

def get_baseurl(tower: dict, type: str) -> str:
    return f"{tower['url']}{baseurls[type]}"

def list_asset(tower: dict, type: str, query: str = None, start_from: int = 0, limit: int = -1) -> list:

    page_size = 200

    baseurl = f"{get_baseurl(tower, type)}?page_size={page_size}"
    if query is not None:
        baseurl = f"{baseurl}&{query}"

    asset_list = []
    while True:
        print(f"Listing assets of type {type} from {baseurl}")
        response = requests.get(
            url=baseurl,
            headers=standard_headers,
            auth=(tower['usr'], tower['pwd']),
            verify=tower['verifyssl']
        )
        response.raise_for_status()
        response_data = response.json()

        if 'results' in response_data:
            asset_list.extend(response_data['results'])

        if 'next' in response_data and response_data['next'] is not None and ((len(asset_list) - start_from) < limit or limit <= 0):
            baseurl = f"{tower['url']}{response_data['next']}"
        else:
            break

    if limit > 0:
        return asset_list[start_from:limit+start_from]
    return asset_list[start_from:]

def get_asset(tower: dict, relative_url: str = None) -> dict:

    baseurl = tower['url']
    asset = {}

    url = f"{baseurl}{relative_url}"
    if url in asset_cache:
        print(f"Getting asset from cached {url}")
        asset = asset_cache[url]
    else:
        while True:
            print(f"Getting asset from {url}")
            response = requests.get(
                url=url,
                headers=standard_headers,
                auth=(tower['usr'], tower['pwd']),
                verify=tower['verifyssl']
            )
            response.raise_for_status()
            response_data = response.json()

            if 'results' in asset:
                asset['results'].extend(response_data['results'])
            else:
                asset = response_data

            asset_cache.update({url: response_data})

            if 'next' in response_data and response_data['next'] is not None:
                url = f"{tower['url']}{response_data['next']}"
            else:
                break

    return asset

def search_asset(tower: dict, type: str, **kwargs : dict) -> list:

    baseurl = get_baseurl(tower, type)
    results = []

    query = "&".join([
        f"{k}={quote(str(v))}"
        for k,v in kwargs.items()
        if k not in keys_not_to_search_for
    ])

    url = f"{baseurl}?{query}"
    if url in asset_cache:
        print(f"Searching cached asset type {type} url {url}")
        results = asset_cache[url]
    else:
        print(f"Searching asset type {type} url {url}")
        response = requests.get(
            url=f"{url}", 
            headers=standard_headers,
            auth=(tower['usr'], tower['pwd']),
            verify=tower['verifyssl']
        )
        response_data = response.json()
        if response.status_code != 200:
            print(response_data)
            response.raise_for_status()
        results = response_data['results']
        asset_cache.update({url: results})

    return results


def write_asset(tower: dict, type: str, asset: dict, dry_run: bool = False) -> dict:

    baseurl = get_baseurl(tower, type)
    response_data = {}

    print(f"Creating asset of type {type}, name {asset['name']} from {baseurl}")
    if dry_run:
        print(f"Dry-run: POST {baseurl} -- {asset}")
    else:
        response = requests.post(
            url=baseurl,
            headers=standard_headers,
            auth=(tower['usr'], tower['pwd']),
            verify=tower['verifyssl'],
            json=asset
        )
        response_data = response.json()
        if response.status_code != 201:
            print(response_data)
            # response.raise_for_status()
    
    return response_data

def write_related_assets(type: str, ported_asset: dict, original_asset: dict , dry_run: bool = False):

    if type in related_asset_types:
        for related_type in related_asset_types[type]:
            print(f"related_type : {related_type}")
            print(f"original_asset['related'][related_type] : {original_asset['related'][related_type]}")
            related_original_assets = get_asset(tower=src_tower, url=original_asset['related'][related_type])
            
            print(f"related_original_assets: {related_original_assets}")
            # related_ported_assets = [
            #     (search_asset(tower=dst_tower, type=related_type, **{
            #         key: related_original_asset[key]
            #         for key in related_asset_query_keys[type]
            #     }))[0]
            #     for related_original_asset in related_original_assets['results']
            # ]
            if type in ['hosts', 'groups']:
                related_ported_assets = [
                    (search_asset(tower=dst_tower, type=related_type, name=related_original_asset['name'], inventory=ported_asset['inventory']))[0]
                    for related_original_asset in related_original_assets['results']
                ]
            elif type in ['job_templates']:
                related_ported_assets = [
                    (search_asset(tower=dst_tower, type=related_type, name=related_original_asset['name'], inventory=ported_asset['inventory']))[0]
                    for related_original_asset in related_original_assets['results']
                ]
            else:
                related_ported_assets = []
            print(f"related_ported_assets: {related_ported_assets}")
            for related_ported_asset in related_ported_assets:
                url = f"{dst_tower['url']}{ported_asset['related'][related_type]}"
                print(f"url: {url}")
                payload = {'id': related_ported_asset['id']}
                print(f"Linking to related asset type {related_type} -- {url}")
                response = requests.post(
                    url=url,
                    headers=standard_headers,
                    auth=(dst_tower['usr'], dst_tower['pwd']),
                    verify=dst_tower['verifyssl'],
                    json=payload
                )
                print(f"response_content: {response.status_code}")
                if response.status_code != 204:
                    print(f"response_data : {response.json()}")
                    response.raise_for_status()


def port_assets(type: str, limit: int = -1, query: str = None, start_from: int = 0, exclude: str = None, dry_run: bool = False):

    credentials_data = dict()
    with open('credentials.json', 'r') as file:
        credentials_data = json.load(file)

    assets = [get_asset(src_tower, asset['url']) for asset in list_asset(tower=src_tower, type=type, start_from=start_from, query=query, limit=limit)]
    for asset in assets:
        if exclude is not None and asset['name'] == exclude:
            print(f"Skipping excluded item {exclude}.")
            continue
        ported_asset = dict()
        ported_asset.update({
            key: asset[key]
            for key in keys_to_keep[type]
            if key in asset
        })
        ported_asset.update({
            key: (search_asset(tower=dst_tower, type=key, name=asset['summary_fields'][key]['name']))[0]['id']
            for key in keys_to_map[type]
            if key in asset and key in asset['summary_fields']
        })
        if type == "credentials":
            ported_asset.update({
                "inputs": credentials_data[ported_asset['name']]['inputs'],
                "organization": 1
            })
        present_assets = search_asset(dst_tower, type, **ported_asset)
        if len(present_assets) == 0:
            written_asset = write_asset(tower=dst_tower, type=type, asset=ported_asset, dry_run=dry_run)
        else:
            print(f"Asset {asset['name']} already exists.")
            written_asset = present_assets[0]

        # print(f"asset : {asset}")
        # print(f"written_asset : {written_asset}")
        write_related_assets(type=type, ported_asset=written_asset, original_asset=asset, dry_run=dry_run)

def main():

    parser = argparse.ArgumentParser(
        prog='porting.py',
        description='Migrates assets from one AWX to another.'
    )
    parser.add_argument('-n', '--dry-run', action='store_true', help='Do not create items on destination')
    parser.add_argument('-t', '--asset-type', type=str, action='store', help=f"Item type to be processed.")
    parser.add_argument('-l', '--limit', type=int, action='store', default=-1, help='Limit number of processed items')
    parser.add_argument('-c', '--config', type=str, action='store', default='./porting.yml', help='Configuration file')
    parser.add_argument('-q', '--query', type=str, action='store', help='Search query')
    parser.add_argument('-x', '--exclude', type=str, action='store', help='Exclude item name from porting')
    parser.add_argument('-s', '--start-from', type=int, action='store', help='Start from item number')
    args = parser.parse_args()
    dry_run = args.dry_run
    asset_type = args.asset_type
    limit = args.limit
    config_file = args.config
    query = args.query
    exclude = args.exclude
    start_from = args.start_from or 0

    config_data = dict()
    with open(config_file, 'r') as file:
        config_data = yaml.safe_load(file)
        if 'src_tower' in config_data:
            src_tower.update(config_data['src_tower'])
        if 'dst_tower' in config_data:
            dst_tower.update(config_data['dst_tower'])
        if 'standard_headers' in config_data:
            standard_headers.update(config_data['standard_headers'])
        if 'baseurls' in config_data:
            baseurls.update(config_data['baseurls'])

    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
    valid_asset_types = baseurls.keys()
    if asset_type in valid_asset_types:
        port_assets(type=asset_type, limit=limit, query=query, start_from=start_from, exclude=exclude, dry_run=dry_run)
    else:
        print(f"Asset type {asset_type} is not valid. Valid types are : {valid_asset_types}")
        parser.print_help()

if __name__ == "__main__":
    main()
