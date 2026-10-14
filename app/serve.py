"""Lokaler Webserver fuer die Fischmarkt-App. Wurzel ist der Projektordner (app/ + model/), oeffnet den Browser."""
import http.server, functools, json, numbers, os, re, socket, sys, urllib.parse, webbrowser, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8080)
EDITS = os.path.join(ROOT, 'model', 'edits.json')
NOTES = os.path.join(ROOT, 'model', 'annotations.json')
SHOTS = os.path.join(ROOT, 'model', 'annotations')


def valid_edits(d):
    """{"Pfad/Teil": {"copyOf": pfad, "offset": [x, y, z], "rotY": grad, "scale": faktor, "deleted": true}, ...} (alles optional)."""
    num = lambda v: isinstance(v, numbers.Real) and not isinstance(v, bool) and abs(v) < 1e4
    return isinstance(d, dict) and all(
        isinstance(k, str) and len(k) < 200 and isinstance(v, dict) and set(v) <= {'copyOf', 'offset', 'rotY', 'scale', 'deleted'}
        and (('offset' not in v) or (isinstance(v['offset'], list) and len(v['offset']) == 3 and all(map(num, v['offset']))))
        and (('rotY' not in v) or num(v['rotY']))
        and (('scale' not in v) or (num(v['scale']) and v['scale'] > 0))
        and (('deleted' not in v) or v['deleted'] is True)
        and (('copyOf' not in v) or (isinstance(v['copyOf'], str) and len(v['copyOf']) < 200))
        for k, v in d.items())


def valid_notes(d):
    """Anmerkungen fuer Claude (app/annotations.js): Liste von Objekten mit id, text, status und Fundstelle."""
    return isinstance(d, list) and all(
        isinstance(a, dict) and isinstance(a.get('id'), str) and re.fullmatch(r'a[0-9a-z]{1,20}', a['id'])
        and isinstance(a.get('text'), str) and len(a['text']) < 10000 and a.get('status') in ('offen', 'erledigt')
        for a in d)


def write_atomic(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, path)


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html',
                      '.glb': 'model/gltf-binary', '.png': 'image/png'}

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_POST(self):
        """Bearbeiten-Modus (app/editor.js): model/edits.json (eine Zeile pro Teil), model/annotations.json und
        Screenshots der Anmerkungen (model/annotations/<id>.jpg)."""
        url = urllib.parse.urlsplit(self.path)
        n = int(self.headers.get('Content-Length') or 0)
        if n > 8_000_000:
            return self.send_error(413)
        body = self.rfile.read(n)
        if url.path == '/api/annotations/shot':
            sid = urllib.parse.parse_qs(url.query).get('id', [''])[0]
            if not re.fullmatch(r'a[0-9a-z]{1,20}', sid) or not body.startswith(b'\xff\xd8'):
                return self.send_error(400, 'Ungueltiges Bild')
            os.makedirs(SHOTS, exist_ok=True)
            with open(os.path.join(SHOTS, sid + '.jpg'), 'wb') as f:
                f.write(body)
            return self.ok()
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if url.path == '/api/edits':
            if not valid_edits(data):
                return self.send_error(400, 'Ungueltige Aenderungen')
            lines = [f'  {json.dumps(k)}: {json.dumps(v)}' for k, v in sorted(data.items())]
            write_atomic(EDITS, '{\n' + ',\n'.join(lines) + ('\n' if lines else '') + '}\n')
            return self.ok()
        if url.path == '/api/annotations':
            if not valid_notes(data):
                return self.send_error(400, 'Ungueltige Anmerkungen')
            write_atomic(NOTES, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
            ids = {a['id'] for a in data}  # Bilder geloeschter Anmerkungen aufraeumen
            for f in os.listdir(SHOTS) if os.path.isdir(SHOTS) else []:
                if f.endswith('.jpg') and f[:-4] not in ids:
                    os.remove(os.path.join(SHOTS, f))
            return self.ok()
        self.send_error(404)

    def ok(self):
        self.send_response(204)
        self.end_headers()


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
