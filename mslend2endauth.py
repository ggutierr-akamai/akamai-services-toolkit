#!/usr/bin/env python3
"""
=============================================================================
MSL5 End-to-End Ingestion & Playback Tester
=============================================================================
This script converts a local MP4 file into HLS, ingests it into an Akamai 
MSL5/Harmonic origin, and automatically launches a local web player to verify 
playback through an Akamai Adaptive Media Delivery (AMD) edge hostname.

Prerequisites:
  - FFmpeg installed and in your system PATH
  - Python packages: requests, akamai-edgeauth
    (Run: pip install requests akamai-edgeauth)

Usage:
  python mslend2endauth.py <mp4_file> <streaming_url> <delivery_hostname> [options]

Positional Arguments:
  mp4_file           Path to the input MP4 file.
  streaming_url      MSL5 ingestion endpoint URL (must end with '/').
  delivery_hostname  Akamai AMD edge hostname (e.g., config.akamaized.net).

Optional Arguments:
  -u, --username     Username for MSL5 HTTP Digest Authentication (Ingest).
  -p, --password     Password for MSL5 HTTP Digest Authentication (Ingest).
  -k, --key          Akamai Token Auth primary encryption key (Delivery).
  -v, --validity     Token validity window in hours (Defaults to 24).

Examples:
  1. Standard Unprotected Stream:
     python mslend2endauth.py video.mp4 https://p-epXXXXX.i.mslentrypoint.net/XXXXX/test/ my.akamaized.net
  
  2. Authenticated Ingest Only (MSL4/MSL5 Digest Auth):
     python mslend2endauth.py video.mp4 https://p-epXXXXX.i.mslentrypoint.net/XXXXX/test/ my.akamaized.net -u user -p pass
  
  3. Token Authenticated Delivery Only:
     python mslend2endauth.py video.mp4 https://p-epXXXXX.i.mslentrypoint.net/XXXXX/test/ my.akamaized.net -k SECRETKEY
  
  4. Fully Authenticated (Ingest Digest Auth + Delivery Token Auth):
     python mslend2endauth.py video.mp4 https://p-epXXXXX.i.mslentrypoint.net/XXXXX/test/ my.akamaized.net -u user -p pass -k SECRETKEY
=============================================================================
"""

import argparse
import sys
import os
import subprocess
import requests
from requests.auth import HTTPDigestAuth
import glob
import tempfile
import webbrowser
import time
from urllib.parse import urlparse, urlunparse

try:
    from akamai.edgeauth import EdgeAuth, EdgeAuthError
except ImportError:
    EdgeAuth = None
    EdgeAuthError = Exception


def validate_url(url):
    if not url.startswith('https://'):
        print("Error: Streaming URL must start with 'https://'")
        sys.exit(1)

    if not url.endswith('/'):
        print("Error: Streaming URL must end with '/'")
        sys.exit(1)

    return url


def convert_mp4_to_hls(mp4_file, hls_dir):
    os.makedirs(hls_dir, exist_ok=True)

    media_manifest = os.path.join(hls_dir, 'index.m3u8')

    cmd = [
        'ffmpeg',
        '-y',
        '-i', mp4_file,
        '-c', 'copy',
        '-start_number', '0',
        '-hls_time', '10',
        '-hls_list_size', '0',
        '-hls_segment_filename', os.path.join(hls_dir, 'index%d.ts'),
        '-f', 'hls',
        media_manifest
    ]

    subprocess.run(cmd, check=True)
    return media_manifest


def create_master_manifest(hls_dir):
    master_manifest = os.path.join(hls_dir, 'master.m3u8')

    master_content = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=1128000
index.m3u8
"""

    with open(master_manifest, 'w', newline='\n') as f:
        f.write(master_content)

    return master_manifest


def post_file(url, file_path, content_type=None, auth=None):
    headers = {}

    if content_type:
        headers['Content-Type'] = content_type

    # Read the file completely into memory first.
    # Digest Auth requires making the request twice (the initial attempt + the challenge response).
    # If we pass the raw file pointer, it hits EOF on the first try and uploads 0 bytes on the retry.
    with open(file_path, 'rb') as f:
        file_data = f.read()

    response = requests.post(url, data=file_data, headers=headers, auth=auth)

    print(f'POST {url} ({os.path.basename(file_path)}): HTTP {response.status_code}')

    if response.status_code >= 400:
        print(response.text)

    return response


def generate_authenticated_url(stream_url, primary_key, validity_hours):
    if EdgeAuth is None:
        print("Error: The 'akamai-edgeauth' package is not installed. Run 'pip install akamai-edgeauth'.", file=sys.stderr)
        sys.exit(1)

    parsed_url = urlparse(stream_url)
    
    try:
        window_seconds = int(float(validity_hours) * 3600)
    except ValueError:
        print(f"Error: Invalid validity format '{validity_hours}'. Must be a number.", file=sys.stderr)
        sys.exit(1)

    generator = EdgeAuth(
        key=primary_key,
        token_name="hdnts",
        window_seconds=window_seconds
    )

    try:
        path_dir = os.path.dirname(parsed_url.path)
        stream_acl = f"{path_dir}/*"
        
        print(f"Generating localized short token using ACL: {stream_acl}")
        token = generator.generate_acl_token(stream_acl)
        
        token_query = f"{generator.token_name}={token}"
        
        if parsed_url.query:
            new_query = f"{parsed_url.query}&{token_query}"
        else:
            new_query = token_query
            
        authenticated_url = urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        
        return authenticated_url

    except EdgeAuthError as e:
        print(f"Akamai Token Generation Error: {e}", file=sys.stderr)
        sys.exit(1)


def launch_playback_player(delivery_url):
    print(f"\nGenerating playback environment for: {delivery_url}")
    
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>MSL5 Ingestion Test Player</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        body {{
            font-family: sans-serif;
            background: #121212;
            color: #ffffff;
            text-align: center;
            padding-top: 40px;
        }}
        video {{
            width: 80%;
            max-width: 800px;
            border: 2px solid #333;
            background: #000;
        }}
        .info {{
            margin-top: 20px;
            color: #aaa;
            word-break: break-all;
        }}
        details {{
            width: 80%;
            max-width: 800px;
            margin: 20px auto;
            text-align: left;
        }}
        summary {{
            cursor: pointer;
            color: #4caf50;
            font-weight: bold;
            margin-bottom: 10px;
            user-select: none;
            padding: 5px;
            border-radius: 4px;
        }}
        summary:hover {{
            background: #1e1e1e;
        }}
        #log-container {{
            width: 100%;
            height: 250px;
            background: #1e1e1e;
            border: 1px solid #444;
            border-radius: 4px;
            overflow-y: auto;
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
            box-shadow: inset 0 0 10px #000;
            box-sizing: border-box;
        }}
        .log-entry {{ margin-bottom: 4px; word-break: break-all; }}
        .status-ok {{ color: #4caf50; font-weight: bold; }}
        .status-warn {{ color: #ff9800; font-weight: bold; }}
        .status-err {{ color: #f44336; font-weight: bold; }}
    </style>
</head>
<body>
    <h2>MSL5 Playback Verification</h2>
    <video id="video" controls autoplay muted></video>
    <div class="info">
        <p><strong>Stream URL:</strong> {delivery_url}</p>
    </div>
    
    <!-- Real-time Network Log (Collapsible) -->
    <details>
        <summary>► View Real-Time Network Log</summary>
        <div id="log-container"></div>
    </details>

    <script>
        const logBox = document.getElementById('log-container');
        
        // Logging UI update function
        function logNetworkTraffic(url, status) {{
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            
            let statusClass = 'status-ok';
            if (status >= 400 || status === 'ERROR') {{
                statusClass = 'status-err';
            }} else if (status >= 300) {{
                statusClass = 'status-warn';
            }}

            entry.innerHTML = '<span class="' + statusClass + '">[' + status + ']</span> ' + url;
            logBox.appendChild(entry);
            
            // Only force scroll if the details panel is open
            if (logBox.parentElement.open) {{
                logBox.scrollTop = logBox.scrollHeight;
            }}
        }}

        // Monkey Patch XMLHttpRequest to intercept Hls.js traffic
        const originalOpen = XMLHttpRequest.prototype.open;
        const originalSend = XMLHttpRequest.prototype.send;
        
        XMLHttpRequest.prototype.open = function(method, url) {{
            this._reqUrl = url;
            return originalOpen.apply(this, arguments);
        }};
        
        XMLHttpRequest.prototype.send = function() {{
            this.addEventListener('load', function() {{
                logNetworkTraffic(this._reqUrl, this.status);
            }});
            this.addEventListener('error', function() {{
                logNetworkTraffic(this._reqUrl, 'ERROR');
            }});
            return originalSend.apply(this, arguments);
        }};

        // Player Initialization
        var video = document.getElementById('video');
        var videoSrc = '{delivery_url}';
        
        if (Hls.isSupported()) {{
            var hls = new Hls();
            hls.loadSource(videoSrc);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                video.play();
            }});
        }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
            video.src = videoSrc;
            video.addEventListener('loadedmetadata', function() {{
                video.play();
            }});
        }}
    </script>
</body>
</html>
"""

    temp_dir = tempfile.gettempdir()
    temp_html_path = os.path.join(temp_dir, "msl_verify_player.html")
    
    with open(temp_html_path, 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print("Waiting 2 seconds for edge propagation...")
    time.sleep(2)
    
    print("Launching default browser...")
    webbrowser.open(f"file://{temp_html_path}")


def main():
    parser = argparse.ArgumentParser(description="Ingest stream into MSL5/Harmonic and verify playback.")
    parser.add_argument("mp4_file", help="Path to the input MP4 file")
    parser.add_argument("streaming_url", help="MSL5 streaming ingestion endpoint URL")
    parser.add_argument("delivery_hostname", help="Akamai delivery edge hostname (e.g. something.akamaized.net)")
    parser.add_argument("--username", "-u", help="Ingest username (optional)", default=None)
    parser.add_argument("--password", "-p", help="Ingest password (optional)", default=None)
    parser.add_argument("--key", "-k", help="Akamai Token Auth encryption key (optional)", default=None)
    parser.add_argument("--validity", "-v", help="Token duration window in hours (optional, defaults to 24)", default="24")

    args = parser.parse_args()

    # Validate ingest credentials configuration
    if (args.username and not args.password) or (args.password and not args.username):
        print("Error: Both --username and --password must be provided together.")
        sys.exit(1)
        
    # Use HTTPDigestAuth natively rather than passing a basic tuple
    ingest_auth = HTTPDigestAuth(args.username, args.password) if args.username else None

    streaming_url = validate_url(args.streaming_url)
    delivery_hostname = args.delivery_hostname.replace('https://', '').replace('http://', '').rstrip('/')

    hls_dir = 'hls_output'

    media_manifest = convert_mp4_to_hls(args.mp4_file, hls_dir)
    master_manifest = create_master_manifest(hls_dir)

    ts_files = sorted(glob.glob(os.path.join(hls_dir, '*.ts')))
    for ts_file in ts_files:
        segment_name = os.path.basename(ts_file)
        segment_url = streaming_url + segment_name
        post_file(segment_url, ts_file, 'video/mp2t', auth=ingest_auth)

    media_manifest_url = streaming_url + 'index.m3u8'
    post_file(media_manifest_url, media_manifest, 'application/vnd.apple.mpegurl', auth=ingest_auth)

    master_manifest_url = streaming_url + 'master.m3u8'
    master_post_response = post_file(master_manifest_url, master_manifest, 'application/vnd.apple.mpegurl', auth=ingest_auth)

    if master_post_response.status_code < 400:
        path_segments = streaming_url.split('/', 3)
        uri_path = path_segments[3] if len(path_segments) > 3 else ""
        
        delivery_url = f"https://{delivery_hostname}/hls/live/{uri_path}master.m3u8"
        
        if args.key:
            print(f"\nToken authorization key detected. Generating token with {args.validity}-hour window...")
            delivery_url = generate_authenticated_url(delivery_url, args.key, args.validity)

        launch_playback_player(delivery_url)
    else:
        print("\nSkipping playback generation due to ingestion failure.")


if __name__ == '__main__':
    main()