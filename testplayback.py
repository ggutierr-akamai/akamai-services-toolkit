import argparse
import json
import os
import webbrowser

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stream Player - DASH / HLS</title>
    <style>
        body { font-family: Arial, sans-serif; display: flex; flex-direction: column; align-items: center; background: #121212; color: #ffffff; margin: 0; padding: 20px; }
        .container { width: 90%; max-width: 1000px; display: flex; flex-direction: column; gap: 20px; }
        
        .manifest-info { background: #1e1e1e; padding: 15px; border-radius: 6px; border-left: 4px solid #4af626; word-break: break-all; }
        .manifest-info strong { color: #aaa; margin-right: 8px; }
        .manifest-info span { font-family: monospace; color: #fff; font-size: 1.1em; }
        
        video { width: 100%; background: #000; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
        
        .log-section { display: flex; flex-direction: column; gap: 10px; }
        textarea { width: 100%; height: 350px; background: #1a1a1a; color: #4af626; font-family: monospace; padding: 12px; box-sizing: border-box; border: 1px solid #333; border-radius: 6px; resize: vertical; line-height: 1.4; }
        h3 { margin: 0; color: #bbb; }
    </style>
    <!-- Player Libraries -->
    <script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
</head>
<body>

<div class="container">
    <h2>Streaming Player</h2>
    
    <!-- Manifest URL Display -->
    <div class="manifest-info">
        <strong>Playing Manifest:</strong> <span id="manifestUrlDisplay"></span>
    </div>

    <video id="videoPlayer" controls autoplay></video>
    
    <div class="log-section">
        <h3>Network Requests Log</h3>
        <textarea id="logArea" readonly></textarea>
    </div>
</div>

<script>
    const streamUrl = {STREAM_URL};
    const headers = {HEADERS_JSON};
    
    const video = document.getElementById('videoPlayer');
    const logArea = document.getElementById('logArea');
    document.getElementById('manifestUrlDisplay').textContent = streamUrl;

    // Helper to write to the textarea
    function logSegment(method, url, status) {
        const timestamp = new Date().toISOString().split('T')[1].slice(0, -1);
        const statusStr = status ? `[HTTP ${status}]` : '[ERR]';
        logArea.value += `[${timestamp}] ${method} ${statusStr} ${url}\\n`;
        logArea.scrollTop = logArea.scrollHeight; 
    }

    // --- NETWORK INTERCEPTORS FOR EXACT LOGGING ---
    // Intercept XHR
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {
        this._requestMethod = method;
        this._requestUrl = url;
        return originalOpen.call(this, method, url, ...args);
    };
    XMLHttpRequest.prototype.send = function(...args) {
        this.addEventListener('loadend', function() {
            logSegment(this._requestMethod, this._requestUrl, this.status);
        });
        this.addEventListener('error', function() {
            logSegment(this._requestMethod, this._requestUrl, 'FAILED');
        });
        return originalSend.call(this, ...args);
    };

    // Intercept Fetch (just in case the player uses fetch API instead of XHR)
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const requestUrl = typeof args[0] === 'string' ? args[0] : (args[0]?.url || 'unknown');
        const method = (args[1] && args[1].method) || (args[0] && args[0].method) || 'GET';
        try {
            const response = await originalFetch(...args);
            logSegment(method, requestUrl, response.status);
            return response;
        } catch (error) {
            logSegment(method, requestUrl, 'FAILED');
            throw error;
        }
    };
    // ----------------------------------------------

    const urlLower = streamUrl.toLowerCase();
    const isDash = urlLower.includes('.mpd');
    const isHls = urlLower.includes('.m3u8');

    if (isDash) {
        // --- DASH.JS SETUP ---
        const player = dashjs.MediaPlayer().create();
        
        // Inject Custom Headers
        player.updateSettings({
            streaming: {
                network: {
                    RequestModifier: {
                        modifyRequestHeader: function (xhr) {
                            for (const [key, value] of Object.entries(headers)) {
                                xhr.setRequestHeader(key, value);
                            }
                            return xhr;
                        }
                    }
                }
            }
        });

        player.initialize(video, streamUrl, true);

    } else if (isHls) {
        // --- HLS.JS SETUP ---
        if (Hls.isSupported()) {
            const hls = new Hls({
                xhrSetup: function(xhr, url) {
                    // Inject Custom Headers
                    for (const [key, value] of Object.entries(headers)) {
                        xhr.setRequestHeader(key, value);
                    }
                }
            });

            hls.loadSource(streamUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, function() {
                video.play();
            });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            // Safari Native HLS Fallback (Custom headers not supported via native <video>)
            logArea.value += "Warning: Using Native Safari HLS. Custom headers cannot be applied.\\n";
            video.src = streamUrl;
            video.addEventListener('loadedmetadata', function() {
                video.play();
            });
        }
    } else {
        logArea.value = "Error: Unsupported URL format. The URL must contain .mpd or .m3u8\\n";
    }
</script>

</body>
</html>
"""

def main():
    parser = argparse.ArgumentParser(description="Generate an HTML player for DASH/HLS streams.")
    parser.add_argument("url", help="The streaming URL (.mpd or .m3u8)")
    parser.add_argument("-H", "--header", action="append", default=[], 
                        help='Header to add to every request. Format: "Name: Value". Can be used multiple times.')

    args = parser.parse_args()

    # Parse headers into a dictionary
    headers_dict = {}
    for header in args.header:
        if ":" in header:
            key, value = header.split(":", 1)
            headers_dict[key.strip()] = value.strip()
        else:
            print(f"Warning: Ignoring invalid header format '{header}'. Expected 'Name: Value'")

    # Inject variables into the HTML template
    html_content = HTML_TEMPLATE.replace("{STREAM_URL}", json.dumps(args.url))
    html_content = html_content.replace("{HEADERS_JSON}", json.dumps(headers_dict))

    # Save the HTML file
    output_filename = "stream_player.html"
    output_path = os.path.abspath(output_filename)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Player created successfully.")
    print(f"URL: {args.url}")
    print(f"Headers applied: {headers_dict}")
    
    # Open in the default web browser
    file_url = f"file://{output_path}"
    print(f"Opening browser to {file_url} ...")
    webbrowser.open(file_url)

if __name__ == "__main__":
    main()