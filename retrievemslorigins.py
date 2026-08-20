#!/usr/bin/env python3

import argparse
import sys
import time
import requests
import os
from datetime import datetime
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
except ImportError:
    print("Error: The 'openpyxl' module is not installed. Please run: pip install openpyxl")
    sys.exit(1)

from akamai.edgegrid import EdgeGridAuth, EdgeRc

def get_args():
    parser = argparse.ArgumentParser(description="Retrieve MSL origins from active Production Akamai properties and export to Excel.")
    parser.add_argument("file", help="Path to a text file containing Akamai property names (one per line).")
    parser.add_argument("ask", help="Account Switch Key (ASK).")
    parser.add_argument("--section", default="default", help="Section of the .edgerc file to use (default: 'default').")
    return parser.parse_args()

def setup_session(section):
    try:
        edgerc_path = os.path.expanduser("~/.edgerc")
        edgerc = EdgeRc(edgerc_path)
        baseurl = 'https://%s' % edgerc.get(section, 'host')
        
        session = requests.Session()
        session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
        return session, baseurl
    except Exception as e:
        print(f"Error setting up EdgeGrid authentication: {e}")
        sys.exit(1)

def api_request(session, method, url, params=None, json_data=None):
    """
    Makes an API request and handles 429 Too Many Requests (Rate Limiting).
    Uses exponential backoff for retries.
    """
    max_retries = 6
    base_wait = 2

    for attempt in range(max_retries):
        if method.upper() == "GET":
            response = session.get(url, params=params)
        elif method.upper() == "POST":
            response = session.post(url, params=params, json=json_data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if response.status_code == 429:
            wait_time = base_wait ** attempt
            print(f"    [!] Rate limit hit. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            continue
            
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"    [!] HTTP Error: {e}")
            print(f"    [!] Response Body: {response.text}")
            return None

    print("    [!] Max retries exceeded due to rate limiting.")
    return None

def find_property(session, baseurl, property_name, ask):
    """Finds a property by name to get its IDs and specifically the active version in Production."""
    endpoint = "/papi/v1/search/find-by-value"
    url = f"{baseurl}{endpoint}"
    params = {"accountSwitchKey": ask}
    payload = {"propertyName": property_name}

    data = api_request(session, "POST", url, params=params, json_data=payload)
    if not data or 'versions' not in data or not data['versions']['items']:
        return None
    
    active_prod_version = None
    prop_info = None

    # Iterate through the returned versions to find the one ACTIVE in Production
    for item in data['versions']['items']:
        if item.get('productionStatus') == 'ACTIVE':
            active_prod_version = item.get('propertyVersion')
            prop_info = item
            break
    
    if not active_prod_version:
        return None  # No active version currently deployed in production
        
    return {
        "propertyId": prop_info['propertyId'],
        "contractId": prop_info['contractId'],
        "groupId": prop_info['groupId'],
        "version": active_prod_version
    }

def extract_msl_origins(node, msl_origins):
    """Recursively traverses the rule tree to find MEDIA_SERVICE_LIVE origins."""
    for behavior in node.get('behaviors', []):
        if behavior.get('name') == 'origin':
            options = behavior.get('options', {})
            if options.get('originType') == 'MEDIA_SERVICE_LIVE':
                mslorigin = options.get('mslorigin')
                if mslorigin:
                    msl_origins.append({
                        "originType": "MEDIA_SERVICE_LIVE",
                        "mslorigin": mslorigin
                    })

    for child in node.get('children', []):
        extract_msl_origins(child, msl_origins)

def get_property_rules(session, baseurl, prop_info, ask):
    """Retrieves the rule tree for a specific property version."""
    prop_id = prop_info['propertyId']
    version = prop_info['version']
    contract_id = prop_info['contractId']
    group_id = prop_info['groupId']
    
    endpoint = f"/papi/v1/properties/{prop_id}/versions/{version}/rules"
    url = f"{baseurl}{endpoint}"
    params = {
        "contractId": contract_id,
        "groupId": group_id,
        "accountSwitchKey": ask
    }
    
    return api_request(session, "GET", url, params=params)

def export_to_excel(data, input_filepath):
    """Exports the gathered data to an Excel file with a timestamp."""
    # Create output filename based on input filename and current timestamp
    base_name = os.path.splitext(os.path.basename(input_filepath))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{base_name}_{timestamp}.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MSL Origins Data"

    # Define headers and styling
    headers = ["Property Name", "Property ID", "Active Version", "Origin Type", "MSL Origin"]
    ws.append(headers)
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    # Append data rows
    for row in data:
        ws.append([
            row['property_name'], 
            row['property_id'], 
            row['version'], 
            row['origin_type'], 
            row['msl_origin']
        ])

    # Auto-adjust column widths for readability
    for col in ws.columns:
        max_length = 0
        column_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[column_letter].width = max_length + 2

    wb.save(output_filename)
    print(f"\n[+] Processing complete! Data exported successfully to: {output_filename}")

def main():
    args = get_args()

    if not os.path.isfile(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    with open(args.file, 'r') as f:
        properties = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(properties)} properties from {args.file}")
    print(f"Using Account Switch Key: {args.ask}\n")

    session, baseurl = setup_session(args.section)
    
    all_extracted_data = []

    for prop in properties:
        print(f"Processing property: {prop}")
        
        prop_info = find_property(session, baseurl, prop, args.ask)
        if not prop_info:
            print(f"    [-] Skipped: Could not find property '{prop}' or it has NO active version in Production.\n")
            continue
            
        print(f"    [*] Found ID: {prop_info['propertyId']}, Active Production Version: {prop_info['version']}")
        
        rule_tree_data = get_property_rules(session, baseurl, prop_info, args.ask)
        if not rule_tree_data or 'rules' not in rule_tree_data:
            print(f"    [-] Could not retrieve rule tree.\n")
            continue

        msl_origins = []
        extract_msl_origins(rule_tree_data['rules'], msl_origins)

        if msl_origins:
            print(f"    [+] Found {len(msl_origins)} MSL Origin(s):")
            for origin in msl_origins:
                print(f"        - originType: {origin['originType']}, mslorigin: {origin['mslorigin']}")
                
                # Append to master dataset for Excel export
                all_extracted_data.append({
                    "property_name": prop,
                    "property_id": prop_info['propertyId'],
                    "version": prop_info['version'],
                    "origin_type": origin['originType'],
                    "msl_origin": origin['mslorigin']
                })
        else:
            print("    [-] No MEDIA_SERVICE_LIVE origins found in this property.")
        
        print() 

    # Export to Excel if any valid data was found
    if all_extracted_data:
        export_to_excel(all_extracted_data, args.file)
    else:
        print("\n[-] No MSL origins were found across all processed properties. Excel file was not generated.")

if __name__ == "__main__":
    main()