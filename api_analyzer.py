import argparse
from urllib.parse import urlparse
from collections import Counter, defaultdict
import dns.resolver
from playwright.sync_api import sync_playwright

# Define what content types constitute an API response
API_CONTENT_TYPES = ['application/json', 'text/json', 'application/xml', 'text/xml', 'application/graphql']

# Configure DNS resolver with strict timeouts to prevent hanging on bad hosts
resolver = dns.resolver.Resolver()
resolver.timeout = 2
resolver.lifetime = 2

def is_akamai_host(hostname):
    """
    Performs recursive DNS resolution to check if the hostname is on Akamai 
    by looking for edgesuite.net or edgekey.net in the CNAME chain.
    """
    try:
        # resolve() performs recursive resolution by default
        answer = resolver.resolve(hostname, 'A')
        
        # Look through the answer section for CNAME records
        for rrset in answer.response.answer:
            if rrset.rdtype == dns.rdatatype.CNAME:
                for target in rrset:
                    target_name = target.to_text().lower()
                    if 'edgesuite.net' in target_name or 'edgekey.net' in target_name:
                        return True
    except Exception:
        # Silently catch DNS resolution failures (NXDOMAIN, Timeouts, etc.)
        pass
    
    return False

def analyze_site(site):
    # Ensure the URL is properly formatted
    if not site.startswith('http://') and not site.startswith('https://'):
        site = 'https://' + site

    # In-memory tracking structures
    methods_count = Counter()
    status_categories = Counter()
    api_hosts = defaultdict(set)

    print(f"Loading {site} as Firefox...")
    print("Scope: Analyzing ALL hosts.\n")

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def handle_response(response):
            try:
                request = response.request
                
                # 1. Track HTTP Methods
                methods_count[request.method] += 1
                
                # 2. Track Status Code Categories
                status_cat = f"{str(response.status)[0]}xx"
                status_categories[status_cat] += 1
                
                # 3. Capture all hostnames delivering API content
                parsed_url = urlparse(response.url)
                hostname = parsed_url.hostname
                
                if hostname:
                    content_type = response.headers.get('content-type', '').split(';')[0].lower()
                    
                    if any(api_type in content_type for api_type in API_CONTENT_TYPES):
                        api_hosts[hostname].add(content_type)
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            page.goto(site, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"[!] Page load stopped or timed out: {e}\n")

        browser.close()

    # --- OUTPUT RESULTS ---
    
    print("-" * 40)
    print("🌐 TRAFFIC SUMMARY")
    print("-" * 40)
    
    print("\nRequests by Method:")
    for method, count in methods_count.items():
        print(f"  - {method}: {count}")
        
    print("\nResponses by Status Code:")
    for status, count in sorted(status_categories.items()):
        print(f"  - {status}: {count}")

    print("\n" + "-" * 40)
    print("🔌 ALL API HOSTNAMES DISCOVERED")
    print("-" * 40)
    
    akamai_hosts = {}

    if not api_hosts:
        print("\nNo API hostnames found.")
    else:
        for host, content_types in sorted(api_hosts.items()):
            types_str = ", ".join(content_types)
            print(f"\nHost: {host}")
            print(f"  └─ Triggered by Content-Types: {types_str}")
            
            # Perform DNS check to see if this specific host is on Akamai
            if is_akamai_host(host):
                akamai_hosts[host] = content_types

    print("\n" + "-" * 40)
    print("☁️  AKAMAI API HOSTNAMES")
    print("-" * 40)

    if not akamai_hosts:
        print("\nNo Akamai-hosted API endpoints found.")
    else:
        for host, content_types in sorted(akamai_hosts.items()):
            types_str = ", ".join(content_types)
            print(f"\nHost: {host}")
            print(f"  └─ Content-Types: {types_str}")
            
    print("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze web traffic to identify API hostnames and CDN routing.")
    parser.add_argument("site", help="The target website (e.g., www.cnbc.com)")
    args = parser.parse_args()
    
    analyze_site(args.site)