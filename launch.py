"""Open the local app and serve until the user closes the console or presses Ctrl+C."""
from pathlib import Path
import os
import socket
import threading
import time
import webbrowser

if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent)
    port = int(os.environ.get('PORT', 8765))
    address = f'http://127.0.0.1:{port}'
    with socket.socket() as probe:
        running = probe.connect_ex(('127.0.0.1', port)) == 0
    if running:
        import urllib.request
        import json
        try:
            with urllib.request.urlopen(address + '/api/state', timeout=3) as response:
                state = json.load(response)
            if 'local_photos' not in state or 'people' not in state:
                raise ValueError('Different service')
        except Exception:
            raise SystemExit('Port 8765 is used by another application. Set PORT to another value.')
        webbrowser.open(address)
    else:
        from server import app, warmup
        warmup()
        def open_browser():
            for _ in range(50):
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1', port)) == 0:
                        webbrowser.open(address)
                        return
                time.sleep(.2)
        threading.Thread(target=open_browser, daemon=True).start()
        app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
