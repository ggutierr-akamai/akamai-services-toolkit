#!/usr/bin/env python3
import argparse
import sys
import json
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

    # 1. Read input CP codes, sanitize to digits only, & remove duplicates
    try:
        raw_cpcodes = []
        with open(args.file, "r") as f:
            for line in f:
                # Remove whitespace, non-breaking spaces, and strip non-numeric characters
                cleaned_line = "".join(filter(str.isdigit, line))
                if cleaned_line:
                    raw_cpcodes.append(cleaned_line)
            
        # Deduplicate while preserving order
        input_cpcodes = list(dict.fromkeys(raw_cpcodes))
        
        raw_count = len(raw_cpcodes)
        unique_count = len(input_cpcodes)
        duplicates_removed = raw_count - unique_count

    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    if not input_cpcodes:
        print("Input file is empty or contains no valid numeric CP codes. Exiting.")
        sys.exit(0)

    # Inform the user about loaded/sanitized entries
    if duplicates_removed > 0:
        print(f"Loaded {raw_count} total entries ({duplicates_removed} duplicate(s) removed).")
    else:
        print(f"Loaded {unique_count} unique CP code(s) from file.")

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
    print("-" * 45)

    # Initialize counters for the summary
    total_checked = len(input_cpcodes)
    total_found = 0
    total_not_found = 0
    total_errors = 0

    # 3. Query the NetStorage Configuration API for each CP code
    endpoint = f"{base_url}/storage/v1/storage-groups"

    for cpcode in input_cpcodes:
        params = {
            "cpcodeId": cpcode,
            "accountSwitchKey": args.switch_key
        }

        try:
            response = session.get(endpoint, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # The API returns a list of storage groups matching the filter
            ns_exists = False
            
            if isinstance(data, list) and len(data) > 0:
                ns_exists = True
            elif isinstance(data, dict):
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
                # Extract Akamai's detailed error message if available
                error_detail = ""
                try:
                    err_json = response.json()
                    error_detail = err_json.get("detail") or err_json.get("title") or response.text
                except Exception:
                    error_detail = response.text.strip()
                
                print(f"{cpcode:<15} | ⚠️ HTTP ERROR {response.status_code}: {error_detail}")
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