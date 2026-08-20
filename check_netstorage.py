#!/usr/bin/env python3
import argparse
import sys
import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc

def main():
    parser = argparse.ArgumentParser(
        description="Verify if a NetStorage Storage Group exists for a list of CP Codes."
    )
    parser.add_argument(
        "-f", "--file", 
        required=True, 
        help="Path to text file containing list of CP codes (one per line)."
    )
    parser.add_argument(
        "-s", "--switch-key", 
        required=True, 
        help="Account Switch Key for the target account."
    )
    parser.add_argument(
        "--edgerc", 
        default="~/.edgerc", 
        help="Path to .edgerc credential file."
    )
    parser.add_argument(
        "--section", 
        default="default", 
        help="Section header inside .edgerc."
    )
    args = parser.parse_args()

    # 1. Read input CP codes from the text file
    try:
        with open(args.file, "r") as f:
            # Strip whitespace and ignore empty lines
            input_cpcodes = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    if not input_cpcodes:
        print("Input file is empty. Exiting.")
        sys.exit(0)

    # 2. Setup EdgeGrid Authentication
    try:
        edgerc = EdgeRc(args.edgerc)
        base_url = f"https://{edgerc.get(args.section, 'host')}"
        session = requests.Session()
        session.auth = EdgeGridAuth.from_edgerc(edgerc, args.section)
    except Exception as e:
        print(f"Error initializing EdgeGrid credentials: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Checking NetStorage Configuration API (Account Switch Key: {args.switch_key})...")
    print("\n--- RESULTS ---")
    print(f"{'CP CODE':<15} | {'NETSTORAGE STATUS'}")
    print("-" * 40)

    # Initialize counters for the summary
    total_checked = len(input_cpcodes)
    total_found = 0
    total_not_found = 0
    total_errors = 0

    # 3. Query the NetStorage Configuration API for each CP code
    endpoint = f"{base_url}/storage/v1/storage-groups"

    for cpcode in input_cpcodes:
        # Clean up any potential 'cpc_' prefixes just in case
        clean_cpcode = cpcode.replace("cpc_", "")
        
        params = {
            "cpcodeId": clean_cpcode,
            "accountSwitchKey": args.switch_key
        }

        try:
            response = session.get(endpoint, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # The API returns a list of storage groups matching the filter.
            ns_exists = False
            
            if isinstance(data, list) and len(data) > 0:
                ns_exists = True
            elif isinstance(data, dict):
                # Fallback in case the array is wrapped in an object
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        ns_exists = True
                        break

            if ns_exists:
                print(f"{cpcode:<15} | ✅ PROVISIONED")
                total_found += 1
            else:
                print(f"{cpcode:<15} | ❌ NO NETSTORAGE")
                total_not_found += 1

        except requests.exceptions.HTTPError as err:
            if response.status_code in (403, 404):
                print(f"{cpcode:<15} | ❌ NO NETSTORAGE (or no API access)")
                total_not_found += 1
            else:
                print(f"{cpcode:<15} | ⚠️ HTTP ERROR: {response.status_code}")
                total_errors += 1
        except Exception as err:
             print(f"{cpcode:<15} | ⚠️ ERROR: {err}")
             total_errors += 1

    # 4. Print the final summary
    print("\n--- SUMMARY ---")
    print(f"Total Checked:   {total_checked}")
    print(f"Total Found:     {total_found}")
    print(f"Total Not Found: {total_not_found}")
    if total_errors > 0:
        print(f"Total Errors:    {total_errors}")
    print("-" * 15)

if __name__ == "__main__":
    main()