#!/usr/bin/env python3
"""A local MCP server over HTTP that needs a sign-in, for the real-CLI facts script: every MCP request gets 401 with the
OAuth metadata a real server advertises, and no sign-in can succeed. It listens on 127.0.0.1, prints its port, and writes
each request it gets (method and path) to the file given as its only argument. Standard library only."""
import http.server
import json
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # requests go to the log file only
        pass

    def base(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def reply(self, code, body=None, headers=()):
        data = json.dumps(body).encode() if body is not None else b''
        self.send_response(code)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self):
        with open(sys.argv[1], 'a') as fh:
            fh.write(f'{self.command} {self.path}\n')
        if self.path.startswith('/.well-known/oauth-protected-resource'):
            return self.reply(200, {'resource': self.base() + '/mcp', 'authorization_servers': [self.base()]})
        if self.path.startswith('/.well-known/oauth-authorization-server') or self.path.startswith('/.well-known/openid-configuration'):
            return self.reply(200, {'issuer': self.base(), 'authorization_endpoint': self.base() + '/authorize',
                                    'token_endpoint': self.base() + '/token', 'registration_endpoint': self.base() + '/register',
                                    'response_types_supported': ['code'], 'grant_types_supported': ['authorization_code'],
                                    'code_challenge_methods_supported': ['S256']})
        if self.path.startswith('/mcp'):
            return self.reply(401, {'error': 'invalid_token'}, [(
                'WWW-Authenticate', f'Bearer resource_metadata="{self.base()}/.well-known/oauth-protected-resource"')])
        return self.reply(404, {'error': 'not_found'})

    do_GET = do_POST = do_DELETE = handle_any


if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    print(server.server_port, flush=True)
    server.serve_forever()
