#!/usr/bin/env python3
import sys
import re
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

try:
    import dns.resolver
    import dns.reversename
    import dns.message
    import dns.query
    from dns.exception import DNSException
except ImportError:
    print("Error: The 'dnspython' module is required but not installed.")
    print("Please install it by running: pip install dnspython")
    sys.exit(1)

def get_known_provider(target_string):
    """Identifies KNOWN providers based on domain names. Returns None if unknown."""
    t = target_string.lower()
    if 'akamai' in t or 'edgekey.net' in t or 'edgesuite.net' in t:
        return 'Akamai'
    if 'cloudfront' in t:
        return 'CloudFront'
    if 'cloudflare' in t:
        return 'Cloudflare'
    if 'amazonaws' in t or 'aws' in t:
        return 'AWS'
    if 'fastly' in t:
        return 'Fastly'
    if 'google' in t or '1e100' in t:
        return 'Google'
    if 'azure' in t or 'trafficmanager' in t:
        return 'Azure'
    return None

def get_fallback_provider(target_string):
    """Extracts the base domain as a fallback provider name for unknown hosts."""
    t = target_string.lower()
    parts = t.strip('.').split('.')
    if len(parts) >= 2:
        return f"{parts[-2]}.{parts[-1]}"
    return t

def resolve_and_validate(hostname):
    """
    Resolves the hostname and categorizes it based on CNAME chain or A/PTR/SOA records.
    Returns a tuple: (hostname, category, provider_name_if_any)
    """
    resolver = dns.resolver.get_default_resolver()
    
    try:
        # Query the A record directly. dnspython will recursively follow CNAMEs.
        a_answers = resolver.resolve(hostname, 'A')
        
        ans_resp = None
        if hasattr(a_answers, 'response'):
            ans_resp = a_answers.response() if callable(a_answers.response) else a_answers.response
            
        last_cname_target = None
        
        # 1. Inspect the resolution chain for known CNAME providers
        if ans_resp and hasattr(ans_resp, 'answer'):
            for rrset in ans_resp.answer:
                if rrset.rdtype == dns.rdatatype.CNAME:
                    target = rrset[0].target.to_text()
                    last_cname_target = target
                    prov = get_known_provider(target)
                    if prov:
                        return (hostname, 'akamai' if prov == 'Akamai' else 'other', prov)

        # 2. If no known provider in the CNAME chain, grab the final IP and reverse resolve it
        ip = a_answers[0].to_text()
        rev_name = dns.reversename.from_address(ip)

        try:
            ptr_answers = resolver.resolve(rev_name, 'PTR')
            ptr_target = ptr_answers[0].target.to_text()
            prov = get_known_provider(ptr_target)
            
            if prov:
                return (hostname, 'akamai' if prov == 'Akamai' else 'other', prov)
            # If PTR succeeds but provider is unknown, use the PTR base domain as fallback
            return (hostname, 'other', get_fallback_provider(ptr_target))
            
        except dns.resolver.NXDOMAIN:
            # 3. If PTR fails, check the SOA record in the authority section
            try:
                q = dns.message.make_query(rev_name, dns.rdatatype.PTR)
                r = dns.query.udp(q, resolver.nameservers[0], timeout=2)
                
                if r.authority:
                    for rrset in r.authority:
                        if rrset.rdtype == dns.rdatatype.SOA:
                            soa_target = rrset[0].mname.to_text()
                            prov = get_known_provider(soa_target)
                            
                            if prov:
                                return (hostname, 'akamai' if prov == 'Akamai' else 'other', prov)
                            return (hostname, 'other', get_fallback_provider(soa_target))
            except Exception:
                pass
                
            # If PTR and SOA fail, but we had a CNAME earlier, use the CNAME fallback
            if last_cname_target:
                return (hostname, 'other', get_fallback_provider(last_cname_target))
                
            return (hostname, 'unassociated', None)
            
        except DNSException:
            if last_cname_target:
                return (hostname, 'other', get_fallback_provider(last_cname_target))
            return (hostname, 'unassociated', None)
            
    except dns.resolver.NoAnswer as e:
        # Catch dangling CNAMEs safely (no A record at the end of the chain)
        err_resp = None
        if hasattr(e, 'kwargs') and e.kwargs:
            err_resp = e.kwargs.get('response')
            
        if err_resp is None and hasattr(e, 'response'):
            err_resp = e.response() if callable(e.response) else e.response
            
        if err_resp and hasattr(err_resp, 'answer'):
            for rrset in err_resp.answer:
                if rrset.rdtype == dns.rdatatype.CNAME:
                    target = rrset[0].target.to_text()
                    prov = get_known_provider(target)
                    if prov:
                        return (hostname, 'akamai' if prov == 'Akamai' else 'other', prov)
                    return (hostname, 'other', get_fallback_provider(target))
        return (hostname, 'unassociated', None)
        
    except (dns.resolver.NXDOMAIN, DNSException):
        return (hostname, 'unassociated', None)

def parse_hostnames(filepath):
    """Reads the file and parses hostnames, treating any non-hostname character as a separator."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        raw_strings = re.split(r'[^\w.-]+', content)
        hostnames = [h for h in raw_strings if h and '.' in h]
        
        seen = set()
        unique_hostnames = []
        for h in hostnames:
            if h not in seen:
                unique_hostnames.append(h)
                seen.add(h)
                
        return unique_hostnames
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Parse hostnames and identify if they resolve to Akamai or other providers in parallel.")
    parser.add_argument("file", help="Text file containing the list of hostnames")
    parser.add_argument("-t", "--threads", type=int, default=10, help="Number of concurrent threads (default: 10)")
    args = parser.parse_args()

    hostnames = parse_hostnames(args.file)
    total = len(hostnames)
    
    if total == 0:
        print("No valid hostnames found in the provided file.")
        sys.exit(0)

    list_akamai = []
    list_other = []
    list_unassociated = []

    print_lock = Lock()
    completed_count = 0

    print(f"Starting resolution using {args.threads} parallel workers...\n")

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(resolve_and_validate, hostname): hostname for hostname in hostnames}
        
        for future in as_completed(futures):
            hostname, category, provider = future.result()
            
            if category == 'akamai':
                list_akamai.append(hostname)
            elif category == 'other':
                list_other.append((hostname, provider))
            else:
                list_unassociated.append(hostname)
            
            with print_lock:
                completed_count += 1
                print(f"\rProgress: {completed_count} out of {total} hostnames processed...", end="", flush=True)

    print("\r" + " " * 80 + "\r", end="")

    # --- Print the Results ---
    print("="*50)
    print(" 1. HOSTNAMES ASSOCIATED WITH AKAMAI")
    print("="*50)
    if list_akamai:
        for h in sorted(list_akamai):
            print(f"   {h}")
    else:
        print("   (None found)")

    print("\n" + "="*50)
    print(" 2. HOSTNAMES ASSOCIATED WITH OTHER PROVIDERS")
    print("="*50)
    if list_other:
        for h, prov in sorted(list_other):
            print(f"   {h} -> [{prov}]")
    else:
        print("   (None found)")

    print("\n" + "="*50)
    print(" 3. UNASSOCIATED / RESOLUTION FAILED")
    print("="*50)
    if list_unassociated:
        for h in sorted(list_unassociated):
            print(f"   {h}")
    else:
        print("   (None found)")
    print()

if __name__ == "__main__":
    main()