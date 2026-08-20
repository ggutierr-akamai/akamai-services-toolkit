#!/usr/bin/env python3
"""
Akamai Property Behavior Analyzer: Origin IP ACL, Tiered Distribution, & SureRoute

Usage:
    python check_origin_ip_acls.py <input_file> <account_switch_key>

Example:
    python check_origin_ip_acls.py config_list.txt F-AC-123456
"""

import sys
import os
import json
import argparse
import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Download Akamai rule trees and analyze for Origin IP ACL, Tiered Distribution, and SureRoute behaviors."
    )
    parser.add_argument(
        "input_file",
        help="Path to input text file formatted as 'Config Name, Version'"
    )
    parser.add_argument(
        "account_switch_key",
        help="Akamai Account Switch Key (e.g., F-AC-123456)"
    )
    parser.add_argument(
        "--edgerc",
        default="~/.edgerc",
        help="Path to .edgerc file (default: ~/.edgerc)"
    )
    parser.add_argument(
        "--section",
        default="default",
        help="Section name inside .edgerc file (default: default)"
    )
    return parser.parse_args()

def setup_session(edgerc_path, section):
    """Initialize EdgeGrid authentication session."""
    expanded_path = os.path.expanduser(edgerc_path)
    if not os.path.exists(expanded_path):
        sys.exit(f"Error: .edgerc file not found at {expanded_path}")

    edgerc = EdgeRc(expanded_path)
    base_url = f"https://{edgerc.get(section, 'host')}"

    session = requests.Session()
    session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
    return session, base_url

def find_property(session, base_url, property_name, account_switch_key):
    """Look up Property ID using PAPI search."""
    url = f"{base_url}/papi/v1/search/find-by-value"
    params = {"accountSwitchKey": account_switch_key}
    payload = {"propertyName": property_name}
    headers = {"Content-Type": "application/json"}

    response = session.post(url, json=payload, params=params, headers=headers)
    response.raise_for_status()

    data = response.json()
    items = data.get("versions", {}).get("items", [])

    if not items:
        return None

    first_match = items[0]
    return {
        "propertyId": first_match.get("propertyId"),
        "contractId": first_match.get("contractId"),
        "groupId": first_match.get("groupId")
    }

def get_rule_tree(session, base_url, property_id, version, contract_id, group_id, account_switch_key):
    """Fetch complete JSON rule tree for the specified version."""
    url = f"{base_url}/papi/v1/properties/{property_id}/versions/{version}/rules"
    params = {"accountSwitchKey": account_switch_key}

    if contract_id:
        params["contractId"] = contract_id
    if group_id:
        params["groupId"] = group_id

    headers = {"Accept": "application/json"}
    response = session.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()

def search_target_behaviors(rule_node, current_path="default"):
    """Recursively search rule nodes for target behaviors: originIpAcl, tieredDistribution, sureRoute."""
    oip_findings = []
    td_findings = []
    sr_findings = []

    for behavior in rule_node.get("behaviors", []):
        b_name = behavior.get("name", "").lower()
        match_data = {
            "rule_name": rule_node.get("name", "Unnamed Rule"),
            "path": current_path,
            "behavior": behavior
        }
        if b_name == "originipacl":
            oip_findings.append(match_data)
        elif b_name == "tiereddistribution":
            td_findings.append(match_data)
        elif b_name == "sureroute":
            sr_findings.append(match_data)

    for child in rule_node.get("children", []):
        child_name = child.get("name", "Unnamed Rule")
        new_path = f"{current_path} -> {child_name}"
        c_oip, c_td, c_sr = search_target_behaviors(child, new_path)
        oip_findings.extend(c_oip)
        td_findings.extend(c_td)
        sr_findings.extend(c_sr)

    return oip_findings, td_findings, sr_findings

def check_behavior_enabled(findings):
    """
    Checks if a behavior exists and whether 'enabled' option is explicitly true.
    Returns:
      - 'Yes' if present and enabled=True
      - 'No (Disabled)' if present but enabled=False
      - 'No' if not present in rule tree
    """
    if not findings:
        return "No"

    is_any_enabled = False
    is_any_disabled = False

    for item in findings:
        opts = item["behavior"].get("options", {})
        enabled_val = opts.get("enabled", True)

        if enabled_val in [True, "true", "TRUE", "on", "ON"]:
            is_any_enabled = True
        elif enabled_val in [False, "false", "FALSE", "off", "OFF"]:
            is_any_disabled = True

    if is_any_enabled:
        return "Yes"
    elif is_any_disabled:
        return "No (Disabled)"
    else:
        return "No"

def analyze_sureroute(sr_findings):
    """
    Inspects SureRoute configuration for enabled status and type (Performance vs Custom Map).
    """
    if not sr_findings:
        return "No"

    enabled_matches = []
    is_any_disabled = False

    for item in sr_findings:
        opts = item["behavior"].get("options", {})
        enabled_val = opts.get("enabled", True)

        if enabled_val in [True, "true", "TRUE", "on", "ON"]:
            enabled_matches.append(opts)
        elif enabled_val in [False, "false", "FALSE", "off", "OFF"]:
            is_any_disabled = True

    if not enabled_matches:
        return "No (Disabled)" if is_any_disabled else "No"

    modes = []
    for opts in enabled_matches:
        sr_type = str(opts.get("type", "")).upper()
        if sr_type == "PERFORMANCE":
            modes.append("Performance")
        elif sr_type == "CUSTOM_MAP":
            modes.append("Custom Map")
        elif sr_type:
            modes.append(sr_type.title())
        else:
            modes.append("Enabled")

    distinct_modes = ", ".join(sorted(set(modes)))
    return f"Yes ({distinct_modes})"

def process_config(session, base_url, config_name, version, account_switch_key):
    """Analyze a single configuration version. Returns (oip_status, td_status, sr_status)."""
    print("=" * 80)
    print(f" CONFIG: {config_name} | VERSION: {version}")
    print("=" * 80)

    try:
        # Step 1: Search Property Metadata
        prop_info = find_property(session, base_url, config_name, account_switch_key)
        if not prop_info:
            print(f"[-] ERROR: Property '{config_name}' could not be located.\n")
            return "Error (Not Found)", "Error (Not Found)", "Error (Not Found)"

        property_id = prop_info["propertyId"]
        contract_id = prop_info.get("contractId")
        group_id = prop_info.get("groupId")

        print(f"[+] Property ID : {property_id}")

        # Step 2: Retrieve Rule Tree
        rule_data = get_rule_tree(
            session, base_url, property_id, version, contract_id, group_id, account_switch_key
        )

        top_rule = rule_data.get("rules")
        if not top_rule:
            print("[-] ERROR: Rule tree payload is empty.\n")
            return "Error (Empty Rules)", "Error (Empty Rules)", "Error (Empty Rules)"

        # Step 3: Scan Tree for Behaviors
        oip_matches, td_matches, sr_matches = search_target_behaviors(top_rule)

        oip_status = check_behavior_enabled(oip_matches)
        td_status = check_behavior_enabled(td_matches)
        sr_status = analyze_sureroute(sr_matches)

        # Output OIPACL Findings
        print(f"[+] Origin IP ACLs Configured     : {oip_status.upper()}")
        if oip_matches:
            for idx, match in enumerate(oip_matches, 1):
                print(f"    --- OIPACL Instance #{idx} ({match['path']}) ---")
                print(json.dumps(match["behavior"], indent=4))

        # Output Tiered Distribution Findings
        print(f"[+] Tiered Distribution Configured: {td_status.upper()}")
        if td_matches:
            for idx, match in enumerate(td_matches, 1):
                print(f"    --- TD Instance #{idx} ({match['path']}) ---")
                print(json.dumps(match["behavior"], indent=4))

        # Output SureRoute Findings
        print(f"[+] SureRoute Configured          : {sr_status.upper()}")
        if sr_matches:
            for idx, match in enumerate(sr_matches, 1):
                print(f"    --- SureRoute Instance #{idx} ({match['path']}) ---")
                print(json.dumps(match["behavior"], indent=4))

        print()
        return oip_status, td_status, sr_status

    except requests.exceptions.HTTPError as err:
        print(f"[-] API HTTP Error: {err}")
        if err.response is not None:
            print(f"    Details: {err.response.text}")
        print()
        return "Error (API Failed)", "Error (API Failed)", "Error (API Failed)"
    except Exception as ex:
        print(f"[-] Error: {ex}\n")
        return "Error", "Error", "Error"

def main():
    args = parse_arguments()

    if not os.path.exists(args.input_file):
        sys.exit(f"Error: Input file '{args.input_file}' does not exist.")

    session, base_url = setup_session(args.edgerc, args.section)

    # Read config input file
    configs = []
    with open(args.input_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 2:
                print(f"Warning: Skipping invalid line {line_num}: '{line}'")
                continue
            configs.append((parts[0], parts[1]))

    if not configs:
        print("No valid entries found in input file.")
        return

    print(f"Loaded {len(configs)} configuration entry(ies) for analysis.\n")

    summary_results = []

    for config_name, version in configs:
        oip_status, td_status, sr_status = process_config(
            session, base_url, config_name, version, args.account_switch_key
        )
        summary_results.append((config_name, version, oip_status, td_status, sr_status))

    # Output Dynamic Tabular Summary
    col1_w = max(len("Config Name"), max(len(c[0]) for c in summary_results)) + 2
    col2_w = max(len("Version"), max(len(str(c[1])) for c in summary_results)) + 2
    col3_w = max(len("OIPACLs Status"), max(len(c[2]) for c in summary_results)) + 2
    col4_w = max(len("TD Status"), max(len(c[3]) for c in summary_results)) + 2
    col5_w = max(len("SureRoute Status"), max(len(c[4]) for c in summary_results)) + 2

    table_width = col1_w + col2_w + col3_w + col4_w + col5_w + 12

    print("=" * table_width)
    print(" SUMMARY REPORT")
    print("=" * table_width)

    header = f"{'Config Name':<{col1_w}} | {'Version':<{col2_w}} | {'OIPACLs Status':<{col3_w}} | {'TD Status':<{col4_w}} | {'SureRoute Status':<{col5_w}}"
    divider = f"{'-'*col1_w}-+-{'-'*col2_w}-+-{'-'*col3_w}-+-{'-'*col4_w}-+-{'-'*col5_w}"

    print(header)
    print(divider)
    for config_name, version, oip_status, td_status, sr_status in summary_results:
        print(f"{config_name:<{col1_w}} | {version:<{col2_w}} | {oip_status:<{col3_w}} | {td_status:<{col4_w}} | {sr_status:<{col5_w}}")
    print("=" * table_width)

if __name__ == "__main__":
    main()