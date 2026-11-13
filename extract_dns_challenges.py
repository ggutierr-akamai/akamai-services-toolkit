#!/usr/bin/env python3
import json
import sys
import argparse
import os
import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def setup_akamai_session(edgerc_path, section='default'):
    """Sets up the Requests session with Akamai EdgeGrid authentication."""
    try:
        edgerc = EdgeRc(os.path.expanduser(edgerc_path))
        base_url = f"https://{edgerc.get(section, 'host')}"
        
        session = requests.Session()
        session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
        return session, base_url
    except Exception as e:
        print(f"Error configuring Akamai authentication: {e}")
        print(f"Ensure your credentials are in {edgerc_path} under [{section}].")
        sys.exit(1)

def get_pending_change_location(session, base_url, enrollment_id, ask):
    """Fetches the enrollment and extracts the location of the pending change."""
    url = f"{base_url}/cps/v2/enrollments/{enrollment_id}"
    params = {'accountSwitchKey': ask} if ask else {}
    
    headers = {'Accept': 'application/vnd.akamai.cps.enrollment.v11+json'}
    
    print(f"Fetching enrollment {enrollment_id}...")
    response = session.get(url, params=params, headers=headers)
    
    if not response.ok:
        print(f"Failed to fetch enrollment: {response.status_code} - {response.text}")
        sys.exit(1)
        
    data = response.json()
    pending_changes = data.get("pendingChanges", [])
    
    if not pending_changes:
        print(f"No pending changes found for enrollment {enrollment_id}.")
        sys.exit(1)
        
    change_location = pending_changes[0].get("location")
    print(f"Found pending change at: {change_location}")
    return change_location

def get_dv_challenges(session, base_url, change_location, ask):
    """Fetches the Let's Encrypt challenges using the change location."""
    url = f"{base_url}{change_location}/input/info/lets-encrypt-challenges"
    params = {'accountSwitchKey': ask} if ask else {}
    
    headers = {'Accept': 'application/vnd.akamai.cps.dv-challenges.v2+json'}
    
    print("Fetching Let's Encrypt challenges...")
    response = session.get(url, params=params, headers=headers)
    
    # Catch the specific 404 error when challenges are not yet generated
    if response.status_code == 404:
        print("\nNotice: The Let's Encrypt challenges are not ready yet.")
        print("Akamai is still negotiating the request with the Let's Encrypt API.")
        print("Please wait 5-10 minutes and try running the script again.\n")
        sys.exit(1)
    elif not response.ok:
        print(f"Failed to fetch challenges: {response.status_code} - {response.text}")
        sys.exit(1)
        
    return response.json()

def extract_dns_challenges(data, enrollment_id, change_id):
    """Parses DNS-01 challenges, prints them, and exports an Excel file."""
    dv_records = data.get("dv", [])
    if not dv_records:
        print("No 'dv' array found in the JSON data.")
        sys.exit(1)

    print("\n" + "=" * 140)
    print(f"{'Domain':<22} | {'TXT Record Name (Host)':<40} | {'TXT Record Value':<45} | {'Expires'}")
    print("-" * 140)

    extracted_data = []
    
    for record in dv_records:
        domain = record.get("domain", "Unknown")
        status = record.get("status", "")
        expires = record.get("expires", "Unknown")
        
        # Skip domains that are already validated
        if status.lower() == "valid":
            continue
            
        challenges = record.get("challenges", [])
        for challenge in challenges:
            if challenge.get("type") == "dns-01":
                txt_name = challenge.get("fullPath", "")
                txt_value = challenge.get("responseBody", "")
                
                print(f"{domain:<22} | {txt_name:<40} | {txt_value:<45} | {expires}")
                extracted_data.append([domain, txt_name, txt_value, expires])

    print("-" * 140)
    print(f"Extracted {len(extracted_data)} pending DNS challenges.\n")
    
    if extracted_data:
        export_to_excel(extracted_data, enrollment_id, change_id)

def export_to_excel(data, enrollment_id, change_id):
    """Creates a styled Excel file containing the extracted records."""
    wb = Workbook()
    ws = wb.active
    ws.title = "DNS Challenges"

    # Write headers
    headers = ["Domain", "TXT Record Name (Host)", "TXT Record Value", "Expires"]
    ws.append(headers)

    # Style headers
    header_fill = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    # Loop over 4 columns now
    for col in range(1, 5):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Add data rows
    for row in data:
        ws.append(row)

    # Auto-adjust column widths
    for i, col in enumerate(ws.columns, 1):
        max_length = 0
        column = get_column_letter(i)
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[column].width = (max_length + 2)

    # Add zebra striping and borders
    thin_border = Border(left=Side(style='thin', color='DDDDDD'),
                         right=Side(style='thin', color='DDDDDD'),
                         top=Side(style='thin', color='DDDDDD'),
                         bottom=Side(style='thin', color='DDDDDD'))
    fill_light = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    # Loop over 4 columns for styling
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=4), start=2):
        for cell in row:
            cell.border = thin_border
            if row_idx % 2 == 0:
                cell.fill = fill_light

    # Save workbook
    filename = f"enrollment_{enrollment_id}_change_{change_id}.xlsx"
    wb.save(filename)
    print(f"Successfully saved records to: {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and extract DNS TXT challenges from Akamai CPS.")
    parser.add_argument("enrollment_id", help="The CPS Enrollment ID (e.g., 336798)")
    parser.add_argument("account_switch_key", help="The Account Switch Key (e.g., 1-I16LP:1-2RBL)")
    parser.add_argument("--edgerc", default="~/.edgerc", help="Path to your .edgerc file (default: ~/.edgerc)")
    parser.add_argument("--section", default="default", help="Section in .edgerc to use (default: default)")
    
    args = parser.parse_args()
    
    # 1. Setup Auth Session
    session, base_url = setup_akamai_session(args.edgerc, args.section)
    
    # 2. Get the change location from the enrollment
    change_location = get_pending_change_location(session, base_url, args.enrollment_id, args.account_switch_key)
    
    # Extract change_id from the location path
    change_id = change_location.rstrip('/').split('/')[-1]
    
    # 3. Pull the challenges for that change
    challenges_data = get_dv_challenges(session, base_url, change_location, args.account_switch_key)
    
    # 4. Extract records, print to console, and generate Excel file
    extract_dns_challenges(challenges_data, args.enrollment_id, change_id)