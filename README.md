# Akamai Services Toolkit (`akamai-services-toolkit`)

A collection of open-source Python CLI tools, automation utilities, and diagnostic scripts designed to streamline Akamai property analysis, traffic reporting, media operations, and edge infrastructure management[cite: 11].

---

## 📋 Toolkit Inventory

### 1. Web & API Traffic Analyzer (`api_analyzer.py`)
* **Description**: Uses Playwright (Firefox) to load web pages, inspect network traffic, discover API hostnames delivering JSON/XML/GraphQL content, and perform recursive DNS CNAME checks (`edgesuite.net` / `edgekey.net`) to determine if the endpoints are hosted on Akamai[cite: 11].
* **Usage**:
~~~bash
python api_analyzer.py [www.example.com](https://www.example.com)
~~~

### 2. NetStorage Provisioning Verifier (`check_netstorage.py`)
* **Description**: Queries the Akamai NetStorage Configuration API (`/storage/v1/storage-groups`) to verify if NetStorage Storage Groups are provisioned for a bulk list of CP Codes[cite: 11].
* **Usage**:
~~~bash
python check_netstorage.py -f cpcodes.txt -s F-AC-123456
~~~

### 3. Property Behavior Analyzer (`check_origin_ip_acls.py`)
* **Description**: Downloads property rule trees using PAPI (`find-by-value`) and recursively inspects configuration rules for Origin IP ACL (`originIpAcl`), Tiered Distribution (`tiereddistribution`), and SureRoute (`sureroute`) behavior statuses[cite: 11].
* **Usage**:
~~~bash
python check_origin_ip_acls.py config_list.txt F-AC-123456
~~~

### 4. Account Switch Key Search Tool (`checkaccsk.py`)
* **Description**: Queries Akamai IAM API v3 (`/identity-management/v3/api-clients/self/account-switch-keys`) to look up Account Switch Keys matching account names, account IDs, or query strings[cite: 11].
* **Usage**:
~~~bash
python checkaccsk.py "Customer Name"
~~~

### 5. CP Code Traffic Logging Auditor (`checkcpcodes.py`)
* **Description**: Scans properties under a specified Akamai Group ID, extracts active CP Codes from rule trees, checks traffic logging against a local `override.xml` document, and exports an audit report to Excel[cite: 11].
* **Usage**:
~~~bash
python checkcpcodes.py grp_12345 F-AC-123456
~~~

### 6. Hostname DNS & CNAME Resolver (`cname_check.py`)
* **Description**: Bulk resolves hostnames from a text file to primary names, CNAME aliases, and IP addresses via Python `socket`, exporting a timestamped report to Excel[cite: 11].
* **Usage**:
~~~bash
python cname_check.py hostnames.txt
~~~

### 7. MSL4 Bulk Stream Deletion Tool (`delete_msl_configs.py`)
* **Description**: Automates bulk deletion of MSL4 stream configurations via `/config-media-live/v2/msl-origin/streams/{stream_id}` using an input text file containing Stream IDs (one per line)[cite: 11]. The script automatically strips whitespace and removes duplicate Stream IDs before processing[cite: 11]. Includes built-in handling for HTTP 429 rate limits and generates a detailed timestamped JSON audit log[cite: 11].
* **Usage**:
~~~bash
python delete_msl_configs.py msl_streams.txt F-AC-123456
~~~

### 8. DigiCert CNAME Extractor (`extractdigicertcnames.py`)
* **Description**: Launches Playwright Chromium to allow SSO/MFA authentication and executes authenticated POST requests to extract `_dnsauth` CNAME validation records for DigiCert certificate orders[cite: 11].
* **Usage**:
~~~bash
python extractdigicertcnames.py 12345678
~~~

### 9. NetStorage CP Code & Storage Group Mapper (`get_ns_cpcodes.py`)
* **Description**: Resolves CP Code IDs to CP Code Names using the CPRG API (`/cprg/v1/cpcodes`) and maps them against NetStorage Storage Groups (`/storage/v1/storage-groups`), exporting a consolidated report to Excel[cite: 11].
* **Usage**:
~~~bash
python get_ns_cpcodes.py cpcodes.txt F-AC-123456 -o netstorage_report.xlsx
~~~

### 10. Traffic Hits & Response Class Reporter (`gettrafficbyhostbame.py`)
* **Description**: Queries Akamai Reporting API v2 (`/reporting-api/v2/reports/delivery/traffic/current/data`) for total edge hits and HTTP response status code breakdowns (2xx, 3xx, 4xx, 5xx percentages) over a custom day range, exporting to Excel[cite: 11].
* **Usage**:
~~~bash
python gettrafficbyhostbame.py -f hostnames.txt -t 7 -a F-AC-123456
~~~

### 11. CP Code Traffic & Offload Statistics Reporter (`akamai_traffic_stats.py`)
* **Description**: Queries Akamai Reporting API v2 (`/reporting-api/v2/reports/delivery/traffic/current/data`) over `LAST_1_WEEK` for edge/origin/midgress hits, bytes, and offload percentages across a list of CP Codes, resolves CP Code names via `/cprg/v1/cpcodes/{cpcode_id}`, and exports a multi-sheet Excel workbook containing an overall summary tab and individual per-CP Code `responseClass` breakdown tabs[cite: 12].
* **Usage**:
~~~bash
python akamai_traffic_stats.py cpcodes.txt --account-key F-AC-123456
~~~

### 12. CPS Let's Encrypt DNS Challenge Extractor (`extract_dns_challenges.py`)
* **Description**: Queries the Certificate Provisioning System (CPS) API (`/cps/v2/enrollments/{enrollment_id}`) to locate pending changes, retrieves pending Let's Encrypt `dns-01` validation challenges, prints the TXT record names, values, and expiration dates, and exports a formatted Excel report[cite: 13].
* **Usage**:
~~~bash
python extract_dns_challenges.py 336798 1-I16LP:1-2RBL
~~~

### 13. Browser DASH / HLS Stream Playback Tester (`testplayback.py`)
* **Description**: Generates a standalone local HTML5 player (`stream_player.html`) powered by `dash.js` and `hls.js` to test `.mpd` or `.m3u8` stream playback in your default browser, supporting custom HTTP request headers (`-H`) and live XHR/Fetch segment request logging[cite: 14].
* **Usage**:
~~~bash
python testplayback.py [https://example.com/live/manifest.m3u8](https://example.com/live/manifest.m3u8) -H "Authorization: Bearer token"
~~~

### 14. Concurrent SSL/TLS Certificate Inspector (`grab_cert.py`)
* **Description**: Concurrently connects to a list of hostnames over port 443 to retrieve peer SSL/TLS certificate details—including Subject CN, Issuer CN, validity period, and Subject Alternative Names (SANs)—with built-in retry handling and a formatted console summary table[cite: 15].
* **Usage**:
~~~bash
python grab_cert.py hostnames.txt -w 10
~~~

### 15. CP Code Metadata Lookup Tool (`cpcodeinfo.py`)
* **Description**: Queries the Akamai CP Codes API (`/cprg/v1/cpcodes/{cpcode}`) for a deduplicated list of CP Codes to retrieve their associated Contract ID, Group ID, and CP Code Name, exporting the results to `cpcode_results.csv` (with optional `--debug` raw JSON output)[cite: 16].
* **Usage**:
~~~bash
python cpcodeinfo.py cpcodes.txt -ask F-AC-123456
~~~

### 16. NetStorage Directory Listing Utility (`ns_dir_list.py`)
* **Description**: Lists directory contents on a NetStorage upload domain using the NetStorage Usage API (`version=1&action=list`) by generating HMAC-SHA256 `X-Akamai-ACS-Auth-Data` and `X-Akamai-ACS-Auth-Sign` authentication headers[cite: 17].
* **Usage**:
~~~bash
python ns_dir_list.py 123456 somepath/ upload_account api_key host-nsu.akamaihd.net
~~~

---

## 🛠️ Requirements & Installation

### Prerequisites
* **Python 3.8+**[cite: 11]
* An active **Akamai EdgeGrid API Client** with permissions matching the API endpoints used by each tool (and NetStorage Upload Account API credentials when using `ns_dir_list.py`)[cite: 11, 17].

### Dependencies
Install the required dependencies via `pip`[cite: 11]:

~~~bash
pip install requests edgegrid-python pandas openpyxl playwright dnspython
~~~

For browser-automation scripts (`api_analyzer.py` and `extractdigicertcnames.py`), initialize Playwright browser binaries[cite: 11]:

~~~bash
playwright install
~~~

---

## 🔑 Authentication Setup

Most scripts require valid Akamai API credentials located in your local `.edgerc` file[cite: 11, 12, 13, 16]:

~~~ini
[default]
host = akab-xxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx.luna.akamaiapis.net
client_token = akab-xxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx
client_secret = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
access_token = akab-xxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx
~~~

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for details[cite: 11].