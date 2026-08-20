import sys
import re
from playwright.sync_api import sync_playwright

def extract_cnames(order_id):
    with sync_playwright() as p:
        # Launch system Chrome to inherit the macOS Keychain client certificate
        browser = p.chromium.launch(
            channel="chrome", 
            headless=False  # Must be visible for human SSO/MFA
        )
        context = browser.new_context()
        page = context.new_page()

        # Step 1: Navigate to the base tool URL to trigger SSO
        print(f"[*] Navigating to Akamai DigiCert tool to authenticate...")
        page.goto("https://tools.gss.akamai.com/monitor/certs/DigiCert/")

        # Step 2: Wait for the user to complete MFA/Push/SSO
        print("[*] Waiting for Human SSO interaction...")
        print("[*] Please complete the authentication in the opened browser window.")
        
        # This pauses the script until the URL indicates a successful login return
        page.wait_for_url("https://tools.gss.akamai.com/monitor/certs/DigiCert/**", timeout=120000)
        print("[+] Authentication successful! Session is active.")

        # Step 3: Construct the POST Request body
        post_body = f"search={order_id}&type=orderid&usage=True&Submit=Submit&.cgifields=usage"

        print(f"[*] Sending POST request natively via browser for Order ID: {order_id}...\n")
        
        # We inject JavaScript to force the authenticated browser window to make the POST request.
        # This guarantees the macOS Keychain mTLS certificate and cookies are used.
        js_fetch_code = """async (bodyData) => {
            const response = await fetch('https://tools.gss.akamai.com/monitor/certs/DigiCert/index.pl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: bodyData
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.text();
        }"""

        try:
            # Execute the JS fetch and capture the returned HTML string
            html_content = page.evaluate(js_fetch_code, post_body)
            
            # Step 4: Parse HTML and extract CNAMEs
            # Regex captures the domain WITH the leading underscore, and the target WITH the leading underscore
            pattern = r"(_dnsauth\.[a-zA-Z0-9.-]+)\s*->\s*(_[a-zA-Z0-9.-]+)"
            matches = re.findall(pattern, html_content)
            
            if matches:
                print("--- EXTRACTED CNAME RECORDS ---")
                for host, target in matches:
                    print(f"{host} {target}")
                print("-------------------------------")
            else:
                print("[-] No CNAME records matching '_dnsauth...' were found on the page.")
                
        except Exception as e:
            print(f"[-] Request failed during JavaScript fetch execution:")
            print(e)

        finally:
            print("\n[*] Closing browser...")
            browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractdigicertcnames.py <order_number>")
        sys.exit(1)
        
    target_order_id = sys.argv[1]
    extract_cnames(target_order_id)