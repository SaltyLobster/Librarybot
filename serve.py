#!/usr/bin/env python3
"""
Local development server for Librarybot webapp.
Serves:
  /              → webapp/
  /covers/       → Bookcovers/
  
Usage:
  python3 serve.py
  
Then open: http://localhost:8080
"""

import http.server
import socketserver
import os
from pathlib import Path
from urllib.parse import urlparse

PORT = 8080
BASE_DIR = Path(__file__).parent

class LocalHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler to serve multiple directories."""
    
    def translate_path(self, path):
        """Map /covers/* to Bookcovers/ directory."""
        parsed = urlparse(path)
        request_path = parsed.path
        
        # Map /covers/ to Bookcovers/
        if request_path.startswith("/covers/"):
            relative_path = request_path[8:].lstrip("/")  # Remove "/covers/" and leading slash
            file_path = BASE_DIR / "Bookcovers" / relative_path
            return str(file_path)
        
        # Everything else maps to webapp/
        if request_path == "/":
            request_path = "/index.html"
        
        file_path = BASE_DIR / "webapp" / request_path.lstrip("/")
        return str(file_path)
    
    def log_message(self, format, *args):
        """Pretty print requests."""
        if isinstance(args[0], str):
            print(f"[{self.client_address[0]}] {args[0]}")
        else:
            print(f"[{self.client_address[0]}] {format % args}")

def main():
    handler = LocalHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"🚀 Librarybot Local Server")
        print(f"📍 http://localhost:{PORT}")
        print(f"📁 Serving: {BASE_DIR}/webapp/")
        print(f"📁 Covers:  {BASE_DIR}/Bookcovers/ (as /covers/)")
        print(f"\nPress Ctrl+C to stop\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n✋ Server stopped")

if __name__ == "__main__":
    main()
