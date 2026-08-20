import argparse
import socket
import sys
from datetime import datetime

try:
    import openpyxl
except ImportError:
    print("Error: The 'openpyxl' library is required to write Excel files.")
    print("Install it using: pip install openpyxl")
    sys.exit(1)

def resolve_hostname(hostname):
    try:
        # gethostbyname_ex provides the primary hostname, aliases (like CNAMEs), and IPs
        primary_hostname, aliaslist, ipaddrlist = socket.gethostbyname_ex(hostname)
        
        result = []
        if aliaslist:
            result.append(f"Aliases/CNAMEs: {', '.join(aliaslist)}")
        if ipaddrlist:
            result.append(f"IPs: {', '.join(ipaddrlist)}")
            
        return " | ".join(result) if result else "No IPs or aliases found"
    except socket.gaierror:
        return "Resolution failed: Name or service not known"
    except Exception as e:
        return f"Resolution failed: {e}"

def main():
    parser = argparse.ArgumentParser(description="Resolve a list of hostnames and output the results to an Excel file.")
    parser.add_argument("input_file", help="Path to the text file containing hostnames (one per line).")
    args = parser.parse_args()

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            # Read lines, strip whitespace, and ignore empty lines
            hostnames = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: The file '{args.input_file}' was not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    if not hostnames:
        print("The provided file is empty. Exiting.")
        sys.exit(0)

    print(f"Loaded {len(hostnames)} hostnames. Starting resolution...")

    # Create Excel workbook and setup header
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hostname Resolutions"
    ws.append(["Hostname", "Resolution Result"])

    # Make the header bold
    for cell in ws[1]:
        cell.font = openpyxl.styles.Font(bold=True)

    # Resolve each hostname and append to the worksheet
    for h in hostnames:
        res = resolve_hostname(h)
        ws.append([h, res])
        print(f"Checked {h} -> {res}")

    # Auto-adjust column widths for better readability
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[column].width = max_length + 2

    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"cname_check_{timestamp}.xlsx"

    # Save the Excel file
    try:
        wb.save(output_file)
        print(f"\nSuccess! Results saved to '{output_file}'")
    except Exception as e:
        print(f"\nError saving Excel file: {e}")

if __name__ == "__main__":
    main()