"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from kantata_assist.client import KantataClient
from kantata_assist.operations import KantataOperations


def operations_with_transport(handler: Callable[[httpx.Request], httpx.Response]) -> KantataOperations:
    """Build KantataOperations backed by MockTransport (no network)."""
    transport = httpx.MockTransport(handler)
    client = KantataClient("test-token", api_base="https://test.invalid/api/v1", transport=transport)
    return KantataOperations(client)
