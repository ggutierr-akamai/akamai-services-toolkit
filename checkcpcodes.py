#!/usr/bin/env python3

import os
import argparse
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import urljoin
from akamai.edgegrid import EdgeGridAuth, EdgeRc

# Constants
XML_FILE = "override.xml"

def get_contract_ids(base_url, session, group_id):
    """Fetch all contract IDs associated with the provided group ID."""
    url = urljoin(base_url, '/papi/v1/groups')
    response = session.get(url)
    response.raise_for_status()
    
    groups = response.json().get('groups', {}).get('items', [])
    for group in groups:
        if group['groupId'] == group_id:
            return group.get('contractIds', [])
            
    raise ValueError(f"Group ID {group_id} not found in the target account.")

def extract_cpcodes(rule_tree):
    """Recursively search the rule tree to find all CPCode behaviors."""
    cpcodes = set()
    
    # Check behaviors in the current rule
    for behavior in rule_tree.get('behaviors', []):
        if behavior.get('name') == 'cpCode':
            cpcode_val = behavior.get('options', {}).get('value', {}).get('id')
            if cpcode_val:
                cpcodes.add(str(cpcode_val))
                
    # Check child rules recursively
    for child in rule_tree.get('children', []):
        cpcodes.update(extract_cpcodes(child))
        
    return cpcodes

def main():
    # Setup command-line arguments
    parser = argparse.ArgumentParser(description="Fetch Akamai properties and check CPCode traffic logging status.")
    parser.add_argument("group_id", help="The Akamai Group ID to inspect (e.g., grp_12345)")
    parser.add_argument("account_switch_key", help="The Account Switch Key for the target account")
    args = parser.parse_args()

    # Ensure the group ID has the 'grp_' prefix
    if not args.group_id.startswith("grp_"):
        args.group_id = f"grp_{args.group_id}"

    # Setup EdgeGrid Auth from ~/.edgerc (default section)
    edgerc_path = os.path.expanduser("~/.edgerc")
    edgerc = EdgeRc(edgerc_path)
    section = "default"
    
    base_url = f"https://{edgerc.get(section, 'host')}"
    session = requests.Session()
    session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
    
    # Automatically append the Account Switch Key as a query string to all Akamai API requests
    session.params = {'accountSwitchKey': args.account_switch_key}

    print(f"Fetching Contract IDs for Group: {args.group_id} using ASK: {args.account_switch_key}...")
    contract_ids = get_contract_ids(base_url, session, args.group_id)
    if not contract_ids:
        print(f"Could not determine any Contract IDs for Group {args.group_id}.")
        return

    # Read the local XML document to check CPCodes against
    print(f"Reading local XML file: {XML_FILE}...")
    try:
        with open(XML_FILE, "r", encoding="utf-8") as f:
            xml_content = f.read()
    except FileNotFoundError:
        print(f"Error: Could not find '{XML_FILE}'. Please ensure the file is in the same directory as this script.")
        return

    data = []

    # Loop through every contract tied to the group
    for contract_id in contract_ids:
        print(f"\nFetching properties for Group: {args.group_id}, Contract: {contract_id}...")
        props_url = urljoin(base_url, f'/papi/v1/properties?contractId={contract_id}&groupId={args.group_id}')
        props_response = session.get(props_url)
        props_response.raise_for_status()
        properties = props_response.json().get('properties', {}).get('items', [])

        if not properties:
            print(f"  No properties found under Contract {contract_id}.")
            continue

        for prop in properties:
            prop_id = prop['propertyId']
            prop_name = prop['propertyName']
            
            # Determine active version (prefer production, fallback to staging)
            active_version = prop.get('productionVersion')
            if not active_version:
                active_version = prop.get('stagingVersion')
                
            if not active_version:
                print(f"  Skipping '{prop_name}' - No active production or staging version.")
                continue

            print(f"  Processing '{prop_name}' (Version {active_version})...")

            # Fetch hostnames
            host_url = urljoin(base_url, f'/papi/v1/properties/{prop_id}/versions/{active_version}/hostnames?contractId={contract_id}&groupId={args.group_id}')
            host_resp = session.get(host_url)
            host_resp.raise_for_status()
            hostnames_data = host_resp.json().get('hostnames', {}).get('items', [])
            hostnames = [h['cnameFrom'] for h in hostnames_data]

            # Fetch rule tree to get CPCodes
            rules_url = urljoin(base_url, f'/papi/v1/properties/{prop_id}/versions/{active_version}/rules?contractId={contract_id}&groupId={args.group_id}')
            rules_resp = session.get(rules_url)
            rules_resp.raise_for_status()
            rule_tree = rules_resp.json().get('rules', {})
            cpcodes = list(extract_cpcodes(rule_tree))

            # Check traffic logging status for each CPCode found
            for cpcode in cpcodes:
                traffic_logging = "DISABLED" if str(cpcode) in xml_content else "ENABLED"
                
                data.append({
                    "Property Name": prop_name,
                    "Contract ID": contract_id,
                    "Active Version": active_version,
                    "Associated Hostnames": ", ".join(hostnames),
                    "CPCode": cpcode,
                    "Traffic Logging": traffic_logging
                })

    # Build Pandas DataFrame
    df = pd.DataFrame(data)
    
    print("\n--- Final DataFrame ---")
    if df.empty:
        print("No data found across any contracts for this group.")
    else:
        print(df.to_string(index=False))
        
        # Format the current date as MMDDYY and export to Excel using the group ID in the filename
        date_str = datetime.now().strftime("%m%d%y")
        excel_filename = f"cpcodes_{date_str}_{args.group_id}.xlsx"
        df.to_excel(excel_filename, index=False)
        print(f"\nExcel report successfully saved to {excel_filename}")

if __name__ == "__main__":
    main()