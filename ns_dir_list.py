#!/usr/bin/env python3
import time
import random
import hmac
import hashlib
import base64
import argparse
import urllib.request
from urllib.error import URLError, HTTPError

def main():
    # Set up argument parsing to easily handle parameters from the command line
    parser = argparse.ArgumentParser(description="List directory contents via Akamai NetStorage API.")
    parser.add_argument("cpcode", help="The unique CP code (e.g., 123456)")
    parser.add_argument("path", help="The path to list (e.g., somepath/)")
    parser.add_argument("account_id", help="Upload account ID (e.g., some_account)")
    parser.add_argument("api_key", help="API key")
    parser.add_argument("host", help="NetStorage host (e.g., host-nsu.akamaihd.net)")

    args = parser.parse_args()

    # Format parameters
    cpcode = args.cpcode.strip('/')
    path = args.path.strip('/')
    host = args.host
    
    # Handle protocol in host variable if accidentally provided
    if host.startswith("http://") or host.startswith("https://"):
        host_url = host
        host_domain = host.split("//")[-1].strip('/')
    else:
        host_url = f"https://{host}"
        host_domain = host.strip('/')

    # Form the URL path logic /{cpCode}/{path}
    if path:
        req_path = f"/{cpcode}/{path}"
    else:
        req_path = f"/{cpcode}"

    # Required Netstorage Usage API list action header variable
    acs_action = "version=1&action=list"
    
    # 1. Generate X-Akamai-ACS-Auth-Data
    # Format: [version], [0.0.0.0], [0.0.0.0], [current epoch time], [unique-number-id], [uploadAccountId]
    epoch_time = str(int(time.time()))
    unique_id = str(random.randint(0, 4294967295))
    auth_data = f"5, 0.0.0.0, 0.0.0.0, {epoch_time}, {unique_id}, {args.account_id}"
    
    # 2. Generate X-Akamai-ACS-Auth-Sign
    # Format: Base64(HMAC-SHA256(key, auth_data + [path]\nx-akamai-acs-action:[action]\n))
    sign_string = f"{req_path}\nx-akamai-acs-action:{acs_action}\n"
    data_to_sign = auth_data + sign_string
    
    key_bytes = args.api_key.encode('utf-8')
    msg_bytes = data_to_sign.encode('utf-8')
    
    signature = hmac.new(key_bytes, msg_bytes, hashlib.sha256).digest()
    auth_sign = base64.b64encode(signature).decode('utf-8')

    url = f"{host_url}{req_path}"

    headers = {
        "Host": host_domain,
        "X-Akamai-ACS-Action": acs_action,
        "X-Akamai-ACS-Auth-Data": auth_data,
        "X-Akamai-ACS-Auth-Sign": auth_sign,
        "Accept": "application/xml"
    }

    req = urllib.request.Request(url, headers=headers)
    print(f"Making request to: {url}\n")
    
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8')
            print(f"Status Code: {status_code}\n")
            print("Response Data:")
            print(response_body)
    except HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
    except URLError as e:
        print(f"URL Error: {e.reason}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()