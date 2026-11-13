#!/usr/bin/env python3

import os
import sys
import csv
import json
import argparse
import requests
from urllib.parse import urljoin
from akamai.edgegrid import EdgeGridAuth, EdgeRc

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Fetch contractId, groupId, and cpcodeName for Akamai CP Codes.")
    parser.add_argument("filename", help="Text file containing a list of CPCodes (one per line)")
    parser.add_argument("--account-switch-key", "-ask", dest="ask", help="Account Switch Key to query a different account")
    parser.add_argument("--debug", "-d", action="store_true", help="Save raw JSON responses to debug_responses.json for troubleshooting")
    args = parser.parse_args()

    # Verify input file
    if not os.path.isfile(args.filename):
        print(f"Error: The file '{args.filename}' was not found.")
        sys.exit(1)

    # Read lines and strip duplicates while preserving order
    with open(args.filename, 'r') as f:
        cpcodes = list(dict.fromkeys(line.strip() for line in f if line.strip()))

    if not cpcodes:
        print("Error: The provided file is empty or contains no valid CP Codes.")
        sys.exit(1)

    # Initialize Akamai EdgeGrid Authentication
    try:
        edgerc_path = os.path.expanduser("~/.edgerc")
        edgerc = EdgeRc(edgerc_path)
        section = "default"
        baseurl = "https://%s" % edgerc.get(section, "host")

        session = requests.Session()
        session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
    except Exception as e:
        print(f"Authentication Error: {e}")
        print("Ensure you have a valid ~/.edgerc file with a [default] section.")
        sys.exit(1)

    results = []
    debug_data = {}  # Dictionary to hold raw JSON responses for debugging

    # Print Table Header
    print(f"{'CPCode':<12} | {'Contract ID':<20} | {'Group ID':<15} | {'CPCode Name'}")
    print("-" * 80)

    # Process each CP Code
    for cpcode in cpcodes:
        clean_cpcode = cpcode.replace("cpc_", "")
        url = urljoin(baseurl, f"/cprg/v1/cpcodes/{clean_cpcode}")
        
        # Apply Account Switch Key if provided
        params = {}
        if args.ask:
            params["accountSwitchKey"] = args.ask

        try:
            response = session.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Save to debug dictionary if flag is set
                if args.debug:
                    debug_data[clean_cpcode] = data
                
                # Top-level field
                cpcode_name = data.get("cpcodeName")
                
                # Nested fields based on API schema
                access_group = data.get("accessGroup")
                if access_group is None:
                    access_group = {}
                    
                contract_id = access_group.get("contractId")
                group_id = access_group.get("groupId")

                # Fallback for contract ID if accessGroup is missing but contracts array exists
                if contract_id is None and "contracts" in data and isinstance(data["contracts"], list):
                    extracted_contracts = [
                        str(c.get("contractId", "")) for c in data["contracts"] if isinstance(c, dict)
                    ]
                    extracted_contracts = [c for c in extracted_contracts if c]
                    if extracted_contracts:
                        contract_id = ", ".join(extracted_contracts)
                
                # Strictly handle JSON nulls (Python None)
                contract_id = "N/A" if contract_id is None else str(contract_id)
                group_id = "N/A" if group_id is None else str(group_id)
                cpcode_name = "N/A" if cpcode_name is None else str(cpcode_name)
                
            else:
                contract_id = f"HTTP {response.status_code}"
                group_id = "N/A"
                
                # Try to capture error JSON for debugging and name extraction
                try:
                    error_json = response.json()
                    cpcode_name = error_json.get("title", "Error")
                    if args.debug:
                        debug_data[clean_cpcode] = error_json
                except ValueError:
                    cpcode_name = "N/A"
                    if args.debug:
                        debug_data[clean_cpcode] = {"status_code": response.status_code, "raw_text": response.text}

        except requests.exceptions.RequestException as e:
            contract_id = "Request Failed"
            group_id = "N/A"
            cpcode_name = str(e)
            if args.debug:
                debug_data[clean_cpcode] = {"error": str(e)}

        # Append to results for CSV
        results.append({
            "cpcode": clean_cpcode,
            "contractid": contract_id,
            "groupId": group_id,
            "cpcodeName": cpcode_name
        })

        # Print to screen
        print(f"{clean_cpcode:<12} | {contract_id:<20} | {group_id:<15} | {cpcode_name}")

    print("-" * 80)

    # Write output to CSV
    csv_filename = "cpcode_results.csv"
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['cpcode', 'contractid', 'groupId', 'cpcodeName']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in results:
                writer.writerow(row)
                
        print(f"Processing complete. Data successfully saved to '{csv_filename}'.")
        
    except IOError as e:
        print(f"Error saving to CSV: {e}")

    # Write debug JSON if flag was provided
    if args.debug:
        debug_filename = "debug_responses.json"
        try:
            with open(debug_filename, 'w', encoding='utf-8') as jsonfile:
                json.dump(debug_data, jsonfile, indent=4)
            print(f"Debug mode active. Raw JSON responses saved to '{debug_filename}'.")
        except IOError as e:
            print(f"Error saving debug JSON file: {e}")

if __name__ == "__main__":
    main()