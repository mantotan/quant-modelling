"""Shared aiohttp connector with Google DNS to bypass ISP blocks.

The ISP's default DNS resolver blocks Polymarket CLOB endpoints
(clob.polymarket.com, ws-subscriptions-clob.polymarket.com).
Using Google DNS (8.8.8.8) resolves all endpoints successfully.
"""

from __future__ import annotations

from aiohttp import TCPConnector
from aiohttp.resolver import AsyncResolver

# Public DNS servers that don't block Polymarket
_DNS_SERVERS = ["8.8.8.8", "8.8.4.4"]


def create_connector() -> TCPConnector:
    """Create a TCPConnector using Google DNS instead of ISP DNS.

    Returns a new connector each time — aiohttp connectors are
    single-use (one per ClientSession).
    """
    resolver = AsyncResolver(nameservers=_DNS_SERVERS)
    return TCPConnector(resolver=resolver)
