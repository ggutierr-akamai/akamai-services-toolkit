import csv
import sys
import os
import json
import time
from datetime import datetime
import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc
from urllib.parse import urljoin

# 1. Argument and Input Verification
if len(sys.argv) < 3:
    print("Error: Missing required arguments.")
    print("Usage: python delete_msl_configs.py <path_to_csv_file> <account_switch_key>")
    sys.exit(1)

csv_file_path = sys.argv[1]
account_switch_key = sys.argv[2]

if not os.path.exists(csv_file_path):
    print(f"Error: File '{csv_file_path}' not found.")
    sys.exit(1)

# 2. Initialize Akamai Authentication Session
try:
    edgerc_path = os.path.expanduser("~/.edgerc")
    edgerc = EdgeRc(edgerc_path)
    section = "default"
    base_url = f"https://{edgerc.get(section, 'host')}"
    
    session = requests.Session()
    session.auth = EdgeGridAuth.from_edgerc(edgerc, section)
except Exception as e:
    print(f"Failed to initialize Akamai EdgeGrid Authentication: {e}")
    sys.exit(1)

execution_log = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "account_switch_key": account_switch_key,
    "results": []
}

print(f"\n🚀 Starting MSL4 Deletion Job (Account Switch Key: {account_switch_key})")
print("-" * 75)
print(f"{'Stream ID':<15} | {'Contract':<15} | {'Status Code':<12} | {'Operation Status'}")
print("-" * 75)

# 3. Parse CSV and execute deletions
with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
    reader = csv.DictReader(csv_file)
    reader.fieldnames = [field.strip() for field in reader.fieldnames]

    for row in reader:
        stream_id = row.get("Stream ID", "").strip()
        contract_id = (row.get("Contract") or row.get("Contract ID") or "").strip()
        
        if not stream_id or not contract_id:
            continue
        
        endpoint_path = f"/config-media-live/v2/msl-origin/streams/{stream_id}"
        full_url = urljoin(base_url, endpoint_path)
        params = {"accountSwitchKey": account_switch_key}
        
        status_text = "Unknown"
        response_body = ""
        
        # Infinite retry loop specifically for handling rate limiting (429)
        while True:
            try:
                response = session.delete(full_url, params=params, timeout=30)
                status_code = response.status_code
                
                try:
                    response_body = response.json()
                except ValueError:
                    response_body = response.text
                
                if status_code == 429:
                    # Print warning and sleep before retrying this exact same stream row
                    print(f"⚠️ [429] Rate limit hit at stream {stream_id}. Cooling down for 30s...")
                    time.sleep(30)
                    continue 
                
                if status_code in [200, 204]:
                    status_text = "SUCCESS"
                elif status_code == 403:
                    status_text = "FORBIDDEN (Check permissions/switch key)"
                elif status_code == 404:
                    status_text = "NOT FOUND"
                else:
                    status_text = "FAILED"
                
                # Break out of the retry loop if it wasn't a 429
                break
                    
            except requests.exceptions.RequestException as req_err:
                status_code = "ERROR"
                status_text = f"Connection Exception: {str(req_err)}"
                response_body = str(req_err)
                break

        # Print final status step to terminal
        print(f"{stream_id:<15} | {contract_id:<15} | {status_code:<12} | {status_text}")
        
        # Save payload item to execution log array
        execution_log["results"].append({
            "stream_id": stream_id,
            "contract_id": contract_id,
            "status_code": status_code,
            "status_text": status_text,
            "api_endpoint": full_url,
            "response_raw": response_body
        })
        
        # Standard safety delay between clean requests
        time.sleep(1)

print("-" * 75)

# 4. Save detailed log file 
log_filename = f"akamai_msl_deletion_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
try:
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        json.dump(execution_log, log_file, indent=4)
    print(f"✅ Job finished. Detailed log file saved to: {log_filename}\n")
except IOError as io_err:
    print(f"❌ Completed job, but failed writing log file: {io_err}\n")