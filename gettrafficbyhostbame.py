import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
import requests
from akamai.edgegrid import EdgeGridAuth, EdgeRc
import pandas as pd

def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch Akamai traffic hits by hostname and export percentages to Excel."
    )
    parser.add_argument(
        "-f", "--file", required=True, help="Path to txt file with a list of hostnames (one per line)"
    )
    parser.add_argument(
        "-t", "--time", required=True, type=int, help="Number of days for the report (e.g., 7)"
    )
    parser.add_argument(
        "-a", "--account-switch-key", required=False, default=None, help="Akamai Account Switch Key"
    )
    parser.add_argument(
        "-e", "--edgerc", default="~/.edgerc", help="Path to .edgerc file (default: ~/.edgerc)"
    )
    parser.add_argument(
        "-s", "--section", default="default", help="Section in .edgerc (default: default)"
    )
    return parser.parse_args()

def read_hostnames(file_path):
    try:
        with open(file_path, "r") as f:
            hostnames = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return hostnames
    except Exception as e:
        print(f"[ERROR] Failed to read hostname file '{file_path}': {e}")
        sys.exit(1)

def main():
    args = parse_args()

    # Read hostnames
    hostnames = read_hostnames(args.file)
    if not hostnames:
        print("[ERROR] No valid hostnames found in the input file.")
        sys.exit(1)

    # Read EdgeRc config to extract host base URL
    try:
        edgerc = EdgeRc(args.edgerc)
        baseurl = f"https://{edgerc.get(args.section, 'host')}"
    except Exception as e:
        print(f"[ERROR] Failed to read section '{args.section}' from '{args.edgerc}': {e}")
        sys.exit(1)

    # Initialize Akamai EdgeGrid session
    session = requests.Session()
    try:
        session.auth = EdgeGridAuth.from_edgerc(args.edgerc, args.section)
    except Exception as e:
        print(f"[ERROR] Failed to load EdgeGrid credentials: {e}")
        sys.exit(1)

    # Calculate ISO start and end timestamps (UTC)
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=args.time)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # API v2 Endpoint for traffic data
    api_url = f"{baseurl}/reporting-api/v2/reports/delivery/traffic/current/data"

    params = {
        "start": start_time,
        "end": end_time
    }
    if args.account_switch_key:
        params["accountSwitchKey"] = args.account_switch_key

    results = []

    print(f"\n--- Starting Query for {len(hostnames)} Hostname(s) over the last {args.time} days ---")
    print(f"Time Range: {start_time} to {end_time}\n")

    for idx, hostname in enumerate(hostnames, 1):
        print(f"[{idx}/{len(hostnames)}] Querying hostname: {hostname} ...", end=" ", flush=True)

        payload = {
            "dimensions": [
                "responseClass"
            ],
            "metrics": [
                "edgeHitsSum"
            ],
            "filters": [
                {
                    "dimensionName": "hostname",
                    "operator": "EXACT",
                    "expressions": [hostname]
                }
            ],
            "sortBys": [
                {
                    "name": "edgeHitsSum",
                    "sortOrder": "DESCENDING"
                }
            ]
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = session.post(api_url, params=params, json=payload)
                
                if response.status_code == 401:
                    print(f"API Response: 401\n[FATAL ERROR] Authentication failed. Please check your credentials.")
                    sys.exit(1)

                # Handle Rate Limiting
                if response.status_code == 429:
                    sleep_time = 5 * (attempt + 1)
                    print(f"\n  [WARN] Rate limited (429). Retrying in {sleep_time} seconds (Attempt {attempt + 1}/{max_retries})...", end=" ")
                    time.sleep(sleep_time)
                    continue

                if response.status_code == 200:
                    data = response.json()
                    data_rows = data.get("data", [])

                    total_hits = 0
                    hits_2xx = 0
                    hits_3xx = 0
                    hits_4xx = 0
                    hits_5xx = 0

                    for row in data_rows:
                        hits = int(float(row.get("edgeHitsSum", 0)))
                        total_hits += hits
                        
                        r_class = str(row.get("responseClass", "")).lower()
                        if "2xx" in r_class:
                            hits_2xx += hits
                        elif "3xx" in r_class:
                            hits_3xx += hits
                        elif "4xx" in r_class:
                            hits_4xx += hits
                        elif "5xx" in r_class:
                            hits_5xx += hits

                    # Convert to percentages
                    pct_2xx = (hits_2xx / total_hits * 100) if total_hits > 0 else 0.0
                    pct_3xx = (hits_3xx / total_hits * 100) if total_hits > 0 else 0.0
                    pct_4xx = (hits_4xx / total_hits * 100) if total_hits > 0 else 0.0
                    pct_5xx = (hits_5xx / total_hits * 100) if total_hits > 0 else 0.0

                    print(f"API Response: 200 (Found {total_hits} hits)")
                    
                    results.append({
                        "hostname": hostname,
                        f"Hits {args.time}d": total_hits,
                        "2xx": f"{pct_2xx:.2f}%",
                        "3xx": f"{pct_3xx:.2f}%",
                        "4xx": f"{pct_4xx:.2f}%",
                        "5xx": f"{pct_5xx:.2f}%"
                    })
                    break # Break the retry loop on success
                
                else:
                    print(f"API Response: {response.status_code} [WARN]")
                    results.append({
                        "hostname": hostname,
                        f"Hits {args.time}d": "ERROR",
                        "2xx": "ERROR",
                        "3xx": "ERROR",
                        "4xx": "ERROR",
                        "5xx": "ERROR"
                    })
                    break # Break the retry loop on non-429 error

            except Exception as e:
                print(f"API Error: {e}")
                results.append({
                    "hostname": hostname,
                    f"Hits {args.time}d": "ERROR",
                    "2xx": "ERROR",
                    "3xx": "ERROR",
                    "4xx": "ERROR",
                    "5xx": "ERROR"
                })
                break # Break on script/network exception
        
        # Friendly delay between all queries to prevent triggering limits
        time.sleep(1)

    # Save output to Excel
    output_filename = f"traffic_report_{args.time}d_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df = pd.DataFrame(results)
    
    # Force strict column naming
    df.columns = ["hostname", f"Hits {args.time}d", "2xx", "3xx", "4xx", "5xx"]
    
    df.to_excel(output_filename, index=False)
    print(f"\nReport successfully saved to: {output_filename}")

if __name__ == "__main__":
    main()