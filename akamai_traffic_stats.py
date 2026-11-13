import argparse
import os
import sys
import requests
from datetime import datetime
import pandas as pd
from akamai.edgegrid import EdgeGridAuth, EdgeRc
from urllib.parse import urljoin
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font

def auto_adjust_columns(worksheet):
    """
    Iterates through all cells in an openpyxl worksheet and adjusts 
    the column width to fit the longest string in each column.
    """
    for col in worksheet.columns:
        max_length = 0
        column_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                # Format check specifically so floats don't artificially shrink the width
                val_to_measure = str(cell.value)
                max_length = max(max_length, len(val_to_measure))
            except:
                pass
        # Add a little extra padding
        adjusted_width = max_length + 2
        worksheet.column_dimensions[column_letter].width = adjusted_width

def fetch_cpcode_names(session, base_url, account_key, cpcodes):
    """
    Retrieves the actual names for a list of CPCodes using the CP Codes API.
    Returns a dictionary mapping CPCode (as string) -> Name.
    """
    cpcode_names = {}
    unique_cpcodes = set(cpcodes)
    print(f"Fetching actual names for {len(unique_cpcodes)} unique CPCodes...")
    
    params = {}
    if account_key:
        params['accountSwitchKey'] = account_key
    
    for cpcode in unique_cpcodes:
        cpcode_id = ''.join(filter(str.isdigit, str(cpcode)))
        if not cpcode_id:
            cpcode_names[str(cpcode)] = "Invalid Format"
            continue
            
        endpoint = f'/cprg/v1/cpcodes/{cpcode_id}'
        url = urljoin(base_url, endpoint)
        
        try:
            response = session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                cpcode_names[str(cpcode)] = data.get('cpcodeName', 'Name not found')
            else:
                cpcode_names[str(cpcode)] = f"Error HTTP {response.status_code}"
        except requests.exceptions.RequestException:
            cpcode_names[str(cpcode)] = "Connection Error"
            
    return cpcode_names

def fetch_report_data(session, url, params, cpcodes, dimensions):
    """Helper function to fetch data for a specific set of dimensions."""
    payload = {
        "dimensions": dimensions,
        "metrics": [
            "edgeBytesSum",
            "edgeHitsSum",
            "edgeResponseBytesSum",
            "edgeRequestBytesSum",
            "originBytesSum",
            "originHitsSum",
            "midgressBytesSum",
            "midgressHitsSum",
            "offloadedHitsPercentage",
            "offloadedBytesPercentage"
        ],
        "filters": [
            {
                "dimensionName": "cpcode",
                "operator": "IN_LIST",
                "expressions": cpcodes
            }
        ]
    }
    
    response = session.post(url, params=params, json=payload)
    if response.status_code == 200:
        return response.json().get('data', [])
    else:
        print(f"\n[Error] Failed to retrieve data for dimensions {dimensions}. HTTP Status: {response.status_code}")
        print("Response body:", response.text)
        sys.exit(1)

def insert_cpcode_name_column(df, cpcode_names_map):
    """Inserts the cpcodeName column safely right after cpcode."""
    if not df.empty and 'cpcode' in df.columns:
        idx = df.columns.get_loc('cpcode')
        mapped_names = df['cpcode'].astype(str).map(cpcode_names_map)
        mapped_names = mapped_names.fillna("Unknown")
        df.insert(idx + 1, 'cpcodeName', mapped_names)
    return df

def main():
    parser = argparse.ArgumentParser(description="Collect Akamai traffic stats by CPCode and responseClass.")
    parser.add_argument('cpcode_file', help='Path to the text file containing CPCodes (one per line)')
    parser.add_argument('--account-key', dest='account_key', help='Akamai Account Switch Key', default=None)
    parser.add_argument('--edgerc', dest='edgerc', help='Path to .edgerc file', default='~/.edgerc')
    parser.add_argument('--section', dest='section', help='Section of .edgerc to use', default='default')
    
    args = parser.parse_args()
    
    cpcodes = []
    try:
        with open(args.cpcode_file, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    cpcodes.append(stripped)
    except FileNotFoundError:
        print(f"Error: The file '{args.cpcode_file}' was not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{args.cpcode_file}': {e}")
        sys.exit(1)

    if not cpcodes:
        print("No CPCodes found in the provided file.")
        sys.exit(1)

    try:
        edgerc_path = os.path.expanduser(args.edgerc)
        edgerc = EdgeRc(edgerc_path)
        base_url = 'https://%s' % edgerc.get(args.section, 'host')
        session = requests.Session()
        session.auth = EdgeGridAuth.from_edgerc(edgerc, args.section)
    except Exception as e:
        print(f"Error setting up EdgeGrid authentication. Details: {e}")
        sys.exit(1)

    cpcode_names_map = fetch_cpcode_names(session, base_url, args.account_key, cpcodes)

    endpoint = '/reporting-api/v2/reports/delivery/traffic/current/data'
    url = urljoin(base_url, endpoint)
    
    report_params = {'timeRange': 'LAST_1_WEEK'}
    if args.account_key:
        report_params['accountSwitchKey'] = args.account_key

    print(f"\nRequesting reporting data for {len(cpcodes)} CPCodes over LAST_1_WEEK...\n")

    try:
        data_all_traffic = fetch_report_data(session, url, report_params, cpcodes, ["cpcode"])
        data_responses = fetch_report_data(session, url, report_params, cpcodes, ["cpcode", "responseClass"])
    except requests.exceptions.RequestException as e:
        print(f"Network error occurred: {e}")
        sys.exit(1)

    print("=== ALL TRAFFIC REPORT (No Breakdown) ===")
    df_report = pd.DataFrame(data_all_traffic)
    if not df_report.empty:
        df_report = insert_cpcode_name_column(df_report, cpcode_names_map)
        
        # Convert Akamai's raw percentage format (e.g. 99.9) to a fraction (e.g. 0.999) for Excel
        report_formatters = {}
        for col in ['offloadedHitsPercentage', 'offloadedBytesPercentage']:
            if col in df_report.columns:
                df_report[col] = pd.to_numeric(df_report[col], errors='coerce').fillna(0) / 100
                report_formatters[col] = lambda x: f"{x*100:.2f}%"
                
        print(df_report.to_string(index=False, formatters=report_formatters))
    else:
        print("No overall traffic data found.")
        
    print("\n" + "="*100 + "\n")

    print("=== RESPONSE CLASS BREAKDOWN (Preview) ===")
    df_responses = pd.DataFrame(data_responses)
    if not df_responses.empty:
        df_responses = insert_cpcode_name_column(df_responses, cpcode_names_map)
        
        # Sort the data by CPCode and then by Response Class
        if 'responseClass' in df_responses.columns:
            df_responses = df_responses.sort_values(by=['cpcode', 'responseClass']).reset_index(drop=True)

        # Calculate percentage of total hits per CP Code
        if 'edgeHitsSum' in df_responses.columns:
            df_responses['edgeHitsSum'] = pd.to_numeric(df_responses['edgeHitsSum'], errors='coerce').fillna(0)
            total_hits = df_responses.groupby('cpcode')['edgeHitsSum'].transform('sum')
            df_responses['edgeHitsPercentage'] = (df_responses['edgeHitsSum'] / total_hits).fillna(0)
            
        console_formatters = None
        if 'edgeHitsPercentage' in df_responses.columns:
            console_formatters = {'edgeHitsPercentage': lambda x: f"{x*100:.2f}%"}
            
        print(df_responses.head(20).to_string(index=False, formatters=console_formatters)) 
        print("... (See Excel file for full breakdown per CPCode)")
    else:
        print("No response class data found.")

    # Save to Multi-sheet Excel
    if not df_report.empty or not df_responses.empty:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_filename = f"akamai_traffic_stats_{timestamp}.xlsx"
        
        try:
            with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
                # 6a. Main Report Tab
                if not df_report.empty:
                    df_report.to_excel(writer, sheet_name='report', index=False)
                    ws_report = writer.sheets['report']
                    
                    # Apply native Excel percentage formatting to the offloaded columns
                    for col_name in ['offloadedHitsPercentage', 'offloadedBytesPercentage']:
                        if col_name in df_report.columns:
                            col_idx = df_report.columns.get_loc(col_name) + 1
                            col_letter = get_column_letter(col_idx)
                            # Header is in row 1, data starts in row 2
                            for row in range(2, 2 + len(df_report)):
                                ws_report[f'{col_letter}{row}'].number_format = '0.00%'
                    
                    auto_adjust_columns(ws_report)
                    
                # 6b. Individual CPCode Tabs
                if not df_responses.empty:
                    required_cols = [
                        'responseClass', 'edgeBytesSum', 'edgeHitsSum', 'edgeHitsPercentage',
                        'edgeResponseBytesSum', 'edgeRequestBytesSum', 
                        'originBytesSum', 'originHitsSum'
                    ]
                    
                    available_cols = [col for col in required_cols if col in df_responses.columns]
                    unique_cpcodes = df_responses['cpcode'].astype(str).unique()
                    
                    for cp in unique_cpcodes:
                        sheet_name = str(cp)[:31]
                        cp_df = df_responses[df_responses['cpcode'].astype(str) == cp][available_cols]
                        
                        # Write tabular data starting at Row 3 (Excel Row 3 = index 2)
                        cp_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)
                        
                        ws = writer.sheets[sheet_name]
                        
                        # Add CP Code name to Cell A1
                        cp_name = cpcode_names_map.get(str(cp), "Unknown")
                        ws['A1'] = f"{cp_name}"
                        ws['A1'].font = Font(bold=True) 
                        
                        # Apply native Excel percentage formatting to the edgeHitsPercentage column
                        if 'edgeHitsPercentage' in available_cols:
                            perc_col_idx = available_cols.index('edgeHitsPercentage') + 1
                            perc_col_letter = get_column_letter(perc_col_idx)
                            
                            # Header is row 3, data starts at row 4
                            for row in range(4, 4 + len(cp_df)):
                                ws[f'{perc_col_letter}{row}'].number_format = '0.00%'
                        
                        auto_adjust_columns(ws)
                        
            print(f"\n[Success] Data successfully saved to Excel spreadsheet: {excel_filename}")
        except Exception as e:
            print(f"\n[Error] Failed to save Excel file: {e}")
    else:
        print("\n[Info] No data retrieved. Excel file was not created.")

if __name__ == "__main__":
    main()