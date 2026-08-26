# Akamai Services Toolkit (`akamai-services-toolkit`)

A collection of open-source Python CLI tools, automation utilities, and diagnostic scripts designed to streamline Akamai property analysis, traffic reporting, media operations, and edge infrastructure management.

---

## 📋 Toolkit Inventory

### 1. Web & API Traffic Analyzer (`api_analyzer.py`)
* **Description**: Uses Playwright (Firefox) to load web pages, inspect network traffic, discover API hostnames delivering JSON/XML/GraphQL content, and perform recursive DNS CNAME checks (`edgesuite.net` / `edgekey.net`) to determine if the endpoints are hosted on Akamai[cite: 1].
* **Usage**:
~~~bash
python api_analyzer.py [www.example.com](https://www.example.com)
~~~

### 2. NetStorage Provisioning Verifier (`check_netstorage.py`)
* **Description**: Queries the Akamai NetStorage Configuration API (`/storage/v1/storage-groups`) to verify if NetStorage Storage Groups are provisioned for a bulk list of CP Codes[cite: 2].
* **Usage**:
~~~bash
python check_netstorage.py -f cpcodes.txt -s F-AC-123456
~~~

### 3. Property Behavior Analyzer (`check_origin_ip_acls.py`)
* **Description**: Downloads property rule trees using PAPI (`find-by-value`) and recursively inspects configuration rules for Origin IP ACL (`originIpAcl`), Tiered Distribution (`tiereddistribution`), and SureRoute (`sureroute`) behavior statuses[cite: 3].
* **Usage**:
~~~bash
python check_origin_ip_acls.py config_list.txt F-AC-123456
~~~

### 4. Account Switch Key Search Tool (`checkaccsk.py`)
* **Description**: Queries Akamai IAM API v3 (`/identity-management/v3/api-clients/self/account-switch-keys`) to look up Account Switch Keys matching account names, account IDs, or query strings[cite: 4].
* **Usage**:
~~~bash
python checkaccsk.py "Customer Name"
~~~

### 5. CP Code Traffic Logging Auditor (`checkcpcodes.py`)
* **Description**: Scans properties under a specified Akamai Group ID, extracts active CP Codes from rule trees, checks traffic logging against a local `override.xml` document, and exports an audit report to Excel[cite: 5].
* **Usage**:
~~~bash
python checkcpcodes.py grp_12345 F-AC-123456
~~~

### 6. Hostname DNS & CNAME Resolver (`cname_check.py`)
* **Description**: Bulk resolves hostnames from a text file to primary names, CNAME aliases, and IP addresses via Python `socket`, exporting a timestamped report to Excel[cite: 6].
* **Usage**:
~~~bash
python cname_check.py hostnames.txt
~~~

### 7. MSL4 Bulk Stream Deletion Tool (`delete_msl_configs.py`)
* **Description**: Automates bulk deletion of MSL4 stream configurations via `/config-media-live/v2/msl-origin/streams/{stream_id}` using an input text file containing Stream IDs (one per line). 
The script automatically strips whitespace and removes duplicate Stream IDs before processing. 
Includes built-in handling for HTTP 429 rate limits and generates a detailed timestamped JSON audit log.
* **Usage**:
~~~bash
python delete_msl_configs.py msl_streams.txt F-AC-123456
~~~

### 8. DigiCert CNAME Extractor (`extractdigicertcnames.py`)
* **Description**: Launches Playwright Chromium to allow SSO/MFA authentication and executes authenticated POST requests to extract `_dnsauth` CNAME validation records for DigiCert certificate orders[cite: 8].
* **Usage**:
~~~bash
python extractdigicertcnames.py 12345678
~~~

### 9. NetStorage CP Code & Storage Group Mapper (`get_ns_cpcodes.py`)
* **Description**: Resolves CP Code IDs to CP Code Names using the CPRG API (`/cprg/v1/cpcodes`) and maps them against NetStorage Storage Groups (`/storage/v1/storage-groups`), exporting a consolidated report to Excel[cite: 9].
* **Usage**:
~~~bash
python get_ns_cpcodes.py cpcodes.txt F-AC-123456 -o netstorage_report.xlsx
~~~

### 10. Traffic Hits & Response Class Reporter (`gettrafficbyhostbame.py`)
* **Description**: Queries Akamai Reporting API v2 (`/reporting-api/v2/reports/delivery/traffic/current/data`) for total edge hits and HTTP response status code breakdowns (2xx, 3xx, 4xx, 5xx percentages) over a custom day range, exporting to Excel[cite: 10].
* **Usage**:
~~~bash
python gettrafficbyhostbame.py -f hostnames.txt -t 7 -a F-AC-123456
~~~

---

## 🛠️ Requirements & Installation

### Prerequisites
* **Python 3.8+**
* An active **Akamai EdgeGrid API Client** with permissions matching the API endpoints used by each tool[cite: 2, 3, 4, 5, 7, 9, 10].

### Dependencies
Install the required dependencies via `pip`:

~~~bash
pip install requests edgegrid-python pandas openpyxl playwright dnspython
~~~

For browser-automation scripts (`api_analyzer.py`[cite: 1] and `extractdigicertcnames.py`[cite: 8]), initialize Playwright browser binaries:

~~~bash
playwright install
~~~

---

## 🔑 Authentication Setup

Most scripts require valid Akamai API credentials located in your local `.edgerc` file[cite: 2, 3, 4, 5, 7, 9, 10]:

~~~ini
[default]
host = akab-xxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx.luna.akamaiapis.net
client_token = akab-xxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx
client_secret = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
access_token = akab-xxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx
~~~

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for details.