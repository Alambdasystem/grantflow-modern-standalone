"""Credential-free DNS/TCP/TLS probe from the actual trial host/network.

No HTTP request, login, introspection or revocation is sent. This cannot certify
an application contract. HTTPS verification/hostname verification stay enabled.
"""
import argparse
import json
import socket
import ssl
from urllib.parse import urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('url', nargs='+')
parser.add_argument('--ca')
args = parser.parse_args()
failed = False
for raw in args.url:
    url = urlsplit(raw)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error('Only explicit HTTPS URLs without credentials/query/fragment are allowed')
    try:
        context = ssl.create_default_context(cafile=args.ca)
        with socket.create_connection((url.hostname, url.port or 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=url.hostname) as tls:
                result = {'host':url.hostname,'port':url.port or 443,'tls':tls.version(),'verified':True}
    except Exception as exc:
        failed=True
        result={'host':url.hostname,'port':url.port or 443,'verified':False,'error_type':type(exc).__name__}
    print(json.dumps(result))
raise SystemExit(1 if failed else 0)
