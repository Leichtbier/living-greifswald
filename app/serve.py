"""Lokaler Webserver fuer die Fischmarkt-App. Wurzel ist der Projektordner (app/ + model/), oeffnet den Browser."""
import http.server, functools, os, sys, webbrowser, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html',
                      '.glb': 'model/gltf-binary', '.png': 'image/png'}

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


url = f'http://localhost:{PORT}/app/'
srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), functools.partial(Handler, directory=ROOT))
print(f'Fischmarkt laeuft auf {url}  (Beenden mit Strg+C)')
if '--no-browser' not in sys.argv:
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
srv.serve_forever()
