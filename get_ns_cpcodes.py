import argparse
import sys
import os
import requests
import pandas as pd
import logging
from akamai.edgegrid import EdgeGridAuth, EdgeRc

# Initialize logger
logger = logging.getLogger(__name__)

def setup_logging(verbose):
    logger.setLevel(logging.DEBUG)
    
    # 1. Console handler (Standard output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    
    # 2. File handler (Detailed Request Log for debugging)
    file_handler = logging.FileHandler('akamai_requests.log', mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

def get_netstorage_details(edgerc_path, section, account_switch_key, target_cpcodes, output_file):
    logger.info(f"Initializing Akamai EdgeGrid Auth using edgerc: {edgerc_path} [Section: {section}]")
    
    try:
        edgerc = EdgeRc(os.path.expanduser(edgerc_path))
        base_url = f"https://{edgerc.get(section, 'host')}"
        logger.debug(f"API Base URL resolved to: {base_url}")
    except Exception as e:
        logger.error(f"Error reading .edgerc file. Have you set it up correctly? Error: {e}", exc_info=True)
        sys.exit(1)
        
    session = requests.Session()
    session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
    
    headers = {"Accept": "application/json"}
    params = {"accountSwitchKey": account_switch_key}
    
    # ---------------------------------------------------------
    # NEW STEP: Fetch all CP Codes names using the CPRG API
    # ---------------------------------------------------------
    logger.info("Sending request to Akamai CP Codes API (CPRG) to resolve actual names...")
    cprg_url = f"{base_url}/cprg/v1/cpcodes"
    
    logger.debug(f"--- API REQUEST (CPRG) ---")
    logger.debug(f"URL: {cprg_url}")
    logger.debug(f"Params: {params}")
    
    global_cpcode_names = {}
    try:
        response_cprg = session.get(cprg_url, headers=headers, params=params)
        logger.debug(f"--- API RESPONSE (CPRG) ---")
        logger.debug(f"Status Code: {response_cprg.status_code}")
        
        if response_cprg.status_code == 200:
            cprg_data = response_cprg.json()
            # Handle different list structures commonly found in Akamai APIs
            cprg_list = cprg_data.get('cpcodes', cprg_data.get('items', [])) if isinstance(cprg_data, dict) else cprg_data
            
            if isinstance(cprg_list, list):
                for cp in cprg_list:
                    # Extract the ID and Name flexibly in case of schema variations
                    cp_id = str(cp.get('cpcodeId', cp.get('id')))
                    cp_name = cp.get('cpcodeName', cp.get('name', 'Unknown'))
                    global_cpcode_names[cp_id] = cp_name
            logger.info(f"Successfully retrieved {len(global_cpcode_names)} CP Code names from CPRG API.")
        else:
            logger.error(f"Failed to fetch from CPRG API. Status Code: {response_cprg.status_code}")
            logger.error(f"Response Body (first 500 chars): {response_cprg.text[:500]}")
            logger.info("Will fallback to NetStorage names if available.")
    except Exception as e:
        logger.error(f"Error calling CPRG API: {e}", exc_info=True)
        logger.info("Will fallback to NetStorage names if available.")

    # ---------------------------------------------------------
    # ORIGINAL STEP: Fetch all NetStorage Storage Groups
    # ---------------------------------------------------------
    logger.info("Sending request to Akamai NetStorage Configuration API...")
    sg_url = f"{base_url}/storage/v1/storage-groups"
    
    logger.debug(f"--- API REQUEST (NetStorage) ---")
    logger.debug(f"URL: {sg_url}")
    logger.debug(f"Params: {params}")
    
    try:
        response = session.get(sg_url, headers=headers, params=params)
        logger.debug(f"--- API RESPONSE (NetStorage) ---")
        logger.debug(f"Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network request to Akamai NetStorage failed completely: {e}", exc_info=True)
        sys.exit(1)
    
    if response.status_code != 200:
        logger.error(f"Akamai NetStorage API returned a failure. Status Code: {response.status_code}")
        logger.error("Check 'akamai_requests.log' for details.")
        sys.exit(1)
        
    sg_data = response.json()
    logger.info("Successfully retrieved Storage Group payload from Akamai.")
    
    # Build a mapping of CPCode ID -> (CPCode Name, Storage Group Name)
    groups = sg_data.get('items', sg_data) if isinstance(sg_data, dict) else sg_data
    logger.info(f"Found {len(groups)} Storage Groups in your account.")
    
    cpcode_mapping = {}
    for sg in groups:
        sg_name = sg.get('storageGroupName', 'Unknown')
        cpcodes = sg.get('cpcodes', sg.get('cpCodes', []))
            
        for cp in cpcodes:
            cp_id = str(cp.get('cpcodeId'))
            
            # ---------------------------------------------------------------------
            # CORE FIX: Check our master CPRG list for the real name! 
            # ---------------------------------------------------------------------
            cp_name = global_cpcode_names.get(cp_id, cp.get('cpcodeName', 'Unknown'))
            
            cpcode_mapping[cp_id] = {
                "cpcodeName": cp_name,
                "storageGroupName": sg_name
            }
            
    logger.info(f"Mapped a total of {len(cpcode_mapping)} NetStorage CP Codes across those groups.")
            
    # Match against the provided list
    logger.info(f"Matching your {len(target_cpcodes)} requested CP Codes against Akamai data...")
    results = []
    
    for cp_id in target_cpcodes:
        info = cpcode_mapping.get(cp_id)
        if info:
            logger.debug(f"Match: {cp_id} -> {info['cpcodeName']} ({info['storageGroupName']})")
            results.append({
                "CP Code": cp_id,
                "CP Code Name": info['cpcodeName'],
                "Storage Group Name": info['storageGroupName']
            })
        else:
            logger.debug(f"No NetStorage Match: {cp_id} not found in NetStorage.")
            
            # Even if it's not in NetStorage, provide the real CP Code Name if we found it
            fallback_name = global_cpcode_names.get(cp_id, "Not Found")
            
            results.append({
                "CP Code": cp_id,
                "CP Code Name": fallback_name,
                "Storage Group Name": "N/A (Not assigned to NetStorage)"
            })
            
    # Write dataset to an Excel file
    try:
        logger.info(f"Writing data to Excel file: {output_file} ...")
        df = pd.DataFrame(results)
        df.to_excel(output_file, index=False, engine='openpyxl')
        logger.info(f"SUCCESS! Output completed.")
    except Exception as e:
        logger.error(f"Failed to write to Excel file. Is it open in another program? Error: {e}", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="Get NetStorage CPCode Name and Storage Group Name and output to Excel.")
    parser.add_argument("file", help="Path to the txt file containing NetStorage CPCodes (one per line)")
    parser.add_argument("ask", help="Account Switch Key")
    parser.add_argument("-o", "--output", default="netstorage_cpcodes.xlsx", help="Output Excel filename (default: netstorage_cpcodes.xlsx)")
    parser.add_argument("--edgerc", default="~/.edgerc", help="Path to the .edgerc file (default: ~/.edgerc)")
    parser.add_argument("--section", default="default", help="Section of the .edgerc file to use (default: default)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose console output")
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    logger.info(f"Script started.")
    
    if not os.path.exists(args.file):
        logger.error(f"Input file '{args.file}' does not exist.")
        sys.exit(1)
        
    logger.info(f"Reading CP Codes from '{args.file}'...")
    
    cpcodes = []
    with open(args.file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            clean_line = line.strip().replace('\ufeff', '')
            
            if not clean_line:
                continue
                
            if clean_line.isdigit():
                cpcodes.append(clean_line)
            else:
                logger.warning(f"Skipping line {line_num} ('{clean_line}') - It contains non-numeric characters.")
        
    if not cpcodes:
        logger.error("Failed to find any valid numeric CP Codes in the text file. Check formatting. Exiting.")
        sys.exit(1)
        
    logger.info(f"Loaded {len(cpcodes)} valid CP Codes from the file.")
    
    get_netstorage_details(args.edgerc, args.section, args.ask, cpcodes, args.output)

if __name__ == "__main__":
    main()