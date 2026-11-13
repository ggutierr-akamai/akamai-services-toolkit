#!/usr/bin/env python3
import ssl
import socket
import argparse
import sys
import time
import concurrent.futures

def get_certificate_details(hostname, port=443, timeout=10, max_retries=3):
    """Connects to the hostname and retrieves the SSL certificate, with retries."""
    context = ssl.create_default_context()
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            with socket.create_connection((hostname, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    return ssock.getpeercert(), None
        except Exception as e:
            last_error = str(e)
            # Wait 1 second before trying again (unless it's the last attempt)
            if attempt < max_retries - 1:
                time.sleep(1)
                
    # If all retries fail, return the last error encountered
    return None, f"Failed after {max_retries} attempts. Last error: {last_error}"

def extract_name(field_tuple):
    """Helper to extract common names from the nested tuple structure."""
    return dict(x[0] for x in field_tuple).get('commonName', 'N/A')

def process_host(host):
    """Worker function to fetch certs and format output strings safely."""
    cert, error = get_certificate_details(host)
    
    output_lines = [f"\n[{host}]", "-" * 40]
    subject_cn = "ERROR / NO CERT"
    
    if error:
        output_lines.append(f"Error retrieving certificate: {error}")
    elif cert:
        subject_cn = extract_name(cert.get('subject', ()))
        issuer_cn = extract_name(cert.get('issuer', ()))
        valid_from = cert.get('notBefore', 'N/A')
        valid_to = cert.get('notAfter', 'N/A')
        
        sans = []
        if 'subjectAltName' in cert:
            sans = [item[1] for item in cert['subjectAltName']]
        
        output_lines.append(f"Subject CN : {subject_cn}")
        output_lines.append(f"Issuer CN  : {issuer_cn}")
        output_lines.append(f"Valid From : {valid_from}")
        output_lines.append(f"Valid To   : {valid_to}")
        
        if sans:
            san_display = ", ".join(sans[:5])
            if len(sans) > 5:
                san_display += f" ... (+{len(sans) - 5} more)"
            output_lines.append(f"SANs       : {san_display}")
            
    return host, subject_cn, "\n".join(output_lines)

def main():
    parser = argparse.ArgumentParser(description="Capture SSL/TLS certificate details concurrently.")
    parser.add_argument("filename", help="Path to the text file containing one hostname per line")
    parser.add_argument("-w", "--workers", type=int, default=10, 
                        help="Number of concurrent workers (default: 10)")
    args = parser.parse_args()

    try:
        with open(args.filename, 'r') as file:
            hostnames = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print(f"Error: The file '{args.filename}' was not found.")
        sys.exit(1)

    if not hostnames:
        print("The provided file is empty.")
        sys.exit(1)

    summary_data = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = executor.map(process_host, hostnames)
        
        for host, subject_cn, output_str in results:
            print(output_str)
            summary_data.append((host, subject_cn))

    # ---------------------------------------------------------
    # PRINT SUMMARY TABLE
    # ---------------------------------------------------------
    print("\n\n" + "=" * 60)
    print(" SUMMARY")
    print("=" * 60)
    
    max_host_len = max([len(h) for h in hostnames] + [20])
    
    print(f"{'Hostname':<{max_host_len}} | Cert Common Name")
    print("-" * max_host_len + "-+-" + "-" * 30)
    
    for host, cn in summary_data:
        print(f"{host:<{max_host_len}} | {cn}")
    
    print()

if __name__ == "__main__":
    main()