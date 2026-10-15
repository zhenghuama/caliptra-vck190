#!/usr/bin/env python3
"""Temporary loopback-only tunnel for official package and Caliptra sources."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import select
import socket
import urllib.request
import urllib.parse

HTTPS_HOSTS = {
    'static.rust-lang.org', 'sh.rustup.rs', 'index.crates.io', 'static.crates.io',
    'crates.io', 'github.com', 'api.github.com', 'codeload.github.com',
    'raw.githubusercontent.com', 'objects.githubusercontent.com',
    'release-assets.githubusercontent.com',
}

class Proxy(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        host, sep, port = self.path.rpartition(':')
        if host not in HTTPS_HOSTS or port != '443':
            self.send_error(403, 'Destination outside dependency allowlist')
            return
        try:
            with socket.create_connection((host, 443), timeout=30) as upstream:
                self.send_response(200, 'Connection established')
                self.end_headers()
                self.wfile.flush()
                peers = [self.connection, upstream]
                while True:
                    ready, _, _ = select.select(peers, [], [], 120)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.connection else self.connection).sendall(data)
        except (OSError, TimeoutError):
            return

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.scheme != 'http' or url.hostname != 'ports.ubuntu.com' or url.port not in (None, 80):
            self.send_error(403, 'HTTP restricted to Ubuntu package server')
            return
        try:
            with urllib.request.urlopen(self.path, timeout=60) as response:
                self.send_response(response.status)
                for key in ('Content-Length', 'Content-Type', 'Last-Modified'):
                    if response.headers.get(key):
                        self.send_header(key, response.headers[key])
                self.end_headers()
                while data := response.read(1048576):
                    self.wfile.write(data)
        except Exception:
            self.close_connection = True

print('Dependency proxy on 127.0.0.1:18080', flush=True)
ThreadingHTTPServer(('127.0.0.1', 18080), Proxy).serve_forever()
