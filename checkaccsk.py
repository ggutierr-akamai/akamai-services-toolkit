#!/usr/bin/env python3
import sys
import os
import argparse
import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc

def get_accounts(edgerc_path, section, search_term):
    """Fetches available account switch keys using Akamai Identity Management API v3."""
    edgerc = EdgeRc(os.path.expanduser(edgerc_path))
    base_url = f"https://{edgerc.get(section, 'host')}"
    
    session = requests.Session()
    session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
    
    # Correct IAM API endpoint to list account switch keys for the current API client
    endpoint = f"{base_url}/identity-management/v3/api-clients/self/account-switch-keys"
    
    params = {}
    # The API natively supports filtering with the 'search' param for strings >= 3 characters
    if len(search_term) >= 3:
        params['search'] = search_term

    try:
        response = session.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()
        
        # The IAM endpoint typically returns a direct JSON array of account objects
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Fallback in case the array is wrapped in an object
            for key in ["accountSwitchKeys", "accounts", "items"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
        return []
        
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response Body: {e.response.text}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Search Akamai Account Switch Keys using IAM API v3."
    )
    parser.add_argument(
        "query", 
        type=str, 
        help="Search string to match account name, account ID, or switch key"
    )
    parser.add_argument(
        "--edgerc", 
        default="~/.edgerc", 
        help="Path to .edgerc file (default: ~/.edgerc)"
    )
    parser.add_argument(
        "--section", 
        default="default", 
        help="Section in .edgerc file (default: default)"
    )

    args = parser.parse_args()
    search_term = args.query.lower()

    # Fetch accounts from the IAM API
    accounts = get_accounts(args.edgerc, args.section, search_term)
    
    matches = []
    for account in accounts:
        account_name = account.get("accountName", "")
        account_id = account.get("accountId", "")
        switch_key = account.get("accountSwitchKey", "")
        
        # Local filter as a fallback (especially if the search term was < 3 characters)
        if (search_term in account_name.lower() or 
            search_term in account_id.lower() or 
            search_term in switch_key.lower()):
            matches.append((account_name, switch_key, account_id))

    if not matches:
        print(f"No accounts matching '{args.query}' were found.")
        sys.exit(0)

    # Output results
    for name, key, acc_id in matches:
        display_name = name if name else f"Account ID: {acc_id}"
        print(f"Account Name: {display_name} | Account Switch Key: {key}")

if __name__ == "__main__":
    main()