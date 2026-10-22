"""Ledger DCF - local server.

Serves index.html and relays requests to Yahoo Finance at /proxy, doing the
same job as the Cloudflare Worker in worker/ does for the hosted site.

Run:  python server.py    then open http://localhost:8765
"""
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8765
ROOT = Path(__file__).parent
ALLOWED_HOSTS = {"query1.finance.yahoo.com", "query2.finance.yahoo.com"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path != "/proxy":
            return self._send(404, b'{"error": "Not found"}')

        target = urllib.parse.parse_qs(url.query).get("url", [""])[0]
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            return self._send(403, b'{"error": "Only Yahoo Finance URLs are allowed."}')
        try:
            with urllib.request.urlopen(urllib.request.Request(target, headers=UA), timeout=15) as r:
                self._send(200, r.read())
        except urllib.error.HTTPError as e:
            self._send(e.code, e.read() or b"{}")
        except Exception as e:  # noqa: BLE001
            self._send(502, f'{{"error": "Could not reach Yahoo Finance: {type(e).__name__}"}}'.encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Ledger DCF running at http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
