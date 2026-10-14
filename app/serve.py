"""Lokaler Webserver fuer die Fischmarkt-App. Wurzel ist der Projektordner (app/ + model/), oeffnet den Browser."""
import http.server, functools, os, socket, sys, webbrowser, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8080)


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html',
                      '.glb': 'model/gltf-binary', '.png': 'image/png'}

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


class Server(http.server.ThreadingHTTPServer):
    # Kein SO_REUSEADDR: unter Windows wuerden sich sonst mehrere Server stillschweigend denselben Port teilen
    # und ein alter Server (z.B. aus einem anderen Ordner) beantwortet die Anfragen.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


srv = None
for port in range(PORT, PORT + 20):
    try:
        srv = Server(('127.0.0.1', port), functools.partial(Handler, directory=ROOT))
        break
    except OSError:
        print(f'Port {port} ist belegt (laeuft noch ein anderer Server?) - versuche {port + 1}')
if srv is None:
    sys.exit(f'Kein freier Port zwischen {PORT} und {PORT + 19} gefunden.')
url = f'http://localhost:{port}/app/'
print(f'Fischmarkt laeuft auf {url}  (Beenden mit Strg+C)')
print(f'Ordner: {ROOT}')
if '--no-browser' not in sys.argv:
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
srv.serve_forever()
