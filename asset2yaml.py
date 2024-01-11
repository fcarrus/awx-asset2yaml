#!/bin/env python3

import requests
import yaml
import argparse
from awx-porting import get_asset, list_asset, keys_to_keep

src_tower = { 'url': 'old-tower.example.com', 'usr': 'username', 'pwd': 'password', 'verifyssl': True }
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
    "workflow_nodes": "/api/v2/workflow_job_template_nodes/",
}

unified_job_type_mapping = {
    'job': 'job_template',
    'workflow_approval': 'workflow_approval'
}

global_organization = "MyOrg"

def filter_asset(type: str, asset: dict) -> dict:

    new_asset = {
        key: value
        for key, value in asset.items()
        if key in keys_to_keep[type]
    }

    if type == "job_template":
        new_asset.update({
            "organization": global_organization,
            "credentials": [ credential['name'] for credential in asset['summary_fields']['credentials'] ],
            'extra_vars': yaml.safe_load(asset['extra_vars']) if asset['extra_vars'] else None,
            'inventory': asset['summary_fields']['inventory']['name'] if asset['inventory'] else None,
            'project': asset['summary_fields']['project']['name'] if asset['project'] else None,
            'survey_spec': get_asset(src_tower, asset['related']['survey_spec']) if asset['survey_enabled'] else {},
        })
    if type == "workflow_job_templates":
        new_asset.update({
            "organization": global_organization,
            'extra_vars': yaml.safe_load(asset['extra_vars']) if asset['extra_vars'] else None,
            'inventory': asset['summary_fields']['inventory']['name'] if asset['inventory'] else None,
            'survey_spec': get_asset(src_tower, asset['related']['survey_spec']) if asset['survey_enabled'] else {},
            'workflow_nodes': [
                filter_asset('workflow_job_template_node', node)
                for node in get_asset(src_tower, asset['related']['workflow_nodes'])['results']
            ]
        })
        if asset['webhook_service'] in ['github', 'gitlab']:
            new_asset.update({
                'webhook_service': asset['webhook_service'],
                'webhook_credential': asset['webhook_credential'],
            })
    if type == "workflow_job_template_node":
        new_asset.update({
            "organization": global_organization,
            'unified_job_template': {
                'name': asset['summary_fields']['unified_job_template']['name'],
                'description': asset['summary_fields']['unified_job_template']['description'],
                'type': unified_job_type_mapping[asset['summary_fields']['unified_job_template']['unified_job_type']],
                'organization': {'name': global_organization}
            },
            'related': {}
        })

        for node_type in ['always_nodes', 'success_nodes', 'failure_nodes']:
            if asset[node_type]:
                nodes_list = get_asset(src_tower, asset['related'][node_type])['results']
                new_asset['related'].update({
                    node_type: [ { 'identifier': node['identifier'] }  for node in nodes_list ]
                })

        if asset['inventory']:
            new_asset['unified_job_template'].update({
                'inventory': {'name': asset['summary_fields']['inventory']['name']}
            })
    if type == "inventory":
        pass
    if type == "inventory_asset":
        new_asset.update({
            "organization": global_organization,
            'source_project': asset['summary_fields']['source_project']['name'],
            'inventory': asset['summary_fields']['inventory']['name'],
            "credentials": [ credential['name'] for credential in asset['summary_fields']['credentials'] ]
        })
    if type == "hosts":
        new_asset.update({
            'inventory': asset['summary_fields']['inventory']['name'],
            'variables': yaml.safe_load(asset['variables']) if asset['variables'] else None
        })
    if type == "groups":
        new_asset.update({
            "organization": global_organization,
            'inventory': asset['summary_fields']['inventory']['name'],
            'hosts': [ host['name'] for host in get_asset(src_tower, asset['related']['all_hosts'])['results']],
            'variables': yaml.safe_load(asset['variables']) if asset['variables'] else None
        })

    return new_asset


def retrieve_assets(type: str, limit: int = -1, query: str = None, start_from: int = 0, exclude: str = None, dry_run: bool = False) -> []:

    assets = [
        filter_asset(type, asset)
        for asset in list_asset(tower=src_tower, type=type, start_from=start_from, query=query, limit=limit)
    ]

    return assets

def main():

    parser = argparse.ArgumentParser(
        prog='asset2yaml.py',
        description='Exports assets in a format compatible to be used with ansible.controller.* modules.'
    )
    parser.add_argument('-n', '--dry-run', action='store_true', help='Do not create items on destination')
    parser.add_argument('-t', '--asset-type', type=str, action='store', help=f"Item type to be processed.", required=True)
    parser.add_argument('-l', '--limit', type=int, action='store', default=-1, help='Limit number of processed items')
    parser.add_argument('-c', '--config', type=str, action='store', default='./awx-porting.yml', help='Configuration file')
    parser.add_argument('-q', '--query', type=str, action='store', help='Search query')
    parser.add_argument('-x', '--exclude', type=str, action='store', help='Exclude item name from porting')
    parser.add_argument('-s', '--start-from', type=int, action='store', help='Start from item number', default=0)
    parser.add_argument('-o', '--output-file', type=str, action='store', help='Output yaml file', required=False)

    args = parser.parse_args()
    dry_run = args.dry_run
    asset_type = args.asset_type
    limit = args.limit
    config_file = args.config
    query = args.query
    exclude = args.exclude
    start_from = args.start_from
    output_file = args.output_file or f"./{asset_type}.assets.yaml"

    config_data = dict()
    with open(config_file, 'r') as file:
        config_data = yaml.safe_load(file)
        if 'src_tower' in config_data:
            src_tower.update(config_data['src_tower'])
        if 'standard_headers' in config_data:
            standard_headers.update(config_data['standard_headers'])
        if 'baseurls' in config_data:
            baseurls.update(config_data['baseurls'])

    assets = []

    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
    valid_asset_types = baseurls.keys()
    if asset_type in valid_asset_types:
        assets = retrieve_assets(type=asset_type, limit=limit, query=query, start_from=start_from, exclude=exclude, dry_run=dry_run)
        with open(output_file, 'w') as output:
            yaml.safe_dump(assets, output, indent=2, default_flow_style=False)
    else:
        print(f"Asset type {asset_type} is not valid. Valid types are : {valid_asset_types}")
        parser.print_help()

if __name__ == "__main__":
    main()
