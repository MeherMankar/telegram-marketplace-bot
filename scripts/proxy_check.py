#!/usr/bin/env python3
"""Simple proxy connectivity checker.
Usage: python scripts/proxy_check.py <proxy_url>
Examples:
  python scripts/proxy_check.py "socks5://83.169.255.92:1080"
  python scripts/proxy_check.py "tg://socks?server=83.169.255.92&port=1080"

The script attempts to open a TCP connection to Telegram IPs via the proxy.
"""
import sys
import socket
import time
from urllib.parse import urlparse, parse_qs

try:
    import socks
except Exception as e:
    print("PySocks not installed. Install with: pip install pysocks")
    raise

TELEGRAM_HOSTS = ["149.154.167.50", "149.154.175.50"]
TELEGRAM_PORT = 443


def parse_proxy_url(url: str):
    url = url.strip()
    if url.startswith("tg://") or url.startswith("t.me/"):
        # parse tg://socks?server=host&port=1080&user=...&pass=...
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        host = qs.get('server', [None])[0]
        port = qs.get('port', [None])[0]
        user = qs.get('user', [None])[0] or qs.get('username', [None])[0]
        password = qs.get('pass', [None])[0] or qs.get('password', [None])[0]
        ptype = 'socks5' if parsed.netloc in ('socks', 'socks5') else 'socks5'
        return ptype, host, int(port) if port else None, user, password

    parsed = urlparse(url)
    if parsed.scheme in ('socks5', 'socks4', 'http'):
        host = parsed.hostname
        port = parsed.port
        user = parsed.username
        password = parsed.password
        return parsed.scheme, host, port, user, password

    raise ValueError(f"Unsupported proxy format: {url}")


def try_connect_via_proxy(ptype, host, port, user, password, dest_host, dest_port, timeout=10):
    s = socks.socksocket()
    proxy_type = socks.SOCKS5 if ptype == 'socks5' else socks.SOCKS4 if ptype == 'socks4' else None
    if proxy_type is None:
        # For HTTP proxies, fallback to plain socket (not implemented)
        return False, 'HTTP proxy testing not implemented'

    try:
        s.set_proxy(proxy_type, host, port, username=user, password=password)
        s.settimeout(timeout)
        start = time.time()
        s.connect((dest_host, dest_port))
        elapsed = time.time() - start
        s.close()
        return True, f'Connected in {elapsed:.2f}s'
    except Exception as e:
        return False, str(e)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/proxy_check.py <proxy_url>')
        sys.exit(2)

    proxy_url = sys.argv[1]
    try:
        ptype, host, port, user, password = parse_proxy_url(proxy_url)
    except Exception as e:
        print('Failed to parse proxy URL:', e)
        sys.exit(2)

    print('Proxy:', ptype, host, port, 'user=' + str(bool(user)))

    for tg in TELEGRAM_HOSTS:
        ok, msg = try_connect_via_proxy(ptype, host, port, user, password, tg, TELEGRAM_PORT)
        print(f'Test to {tg}:{TELEGRAM_PORT} ->', 'OK' if ok else 'FAIL', '-', msg)

    # Also try a direct TCP connect to proxy to verify host:port is reachable
    print('\nDirect TCP connect to proxy host:port (no proxy protocol)')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(8)
    try:
        start = time.time()
        sock.connect((host, port))
        print('Direct TCP connect OK in %.2fs' % (time.time() - start))
    except Exception as e:
        print('Direct TCP connect FAILED:', e)
    finally:
        try:
            sock.close()
        except:
            pass
