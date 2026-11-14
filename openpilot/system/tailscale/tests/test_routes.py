"""Exercise actual aiohttp routes without native vehicle bindings or a VPN."""
import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

spec = importlib.util.spec_from_file_location('tailscale_routes', Path(__file__).resolve().parents[3] /
                                            'selfdrive/carrot/server/features/tailscale.py')
routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routes)


def test_api_guards_and_fixed_actions(monkeypatch):
  async def run():
    stationary = True
    monkeypatch.setattr(routes, 'stationary_offroad', lambda: stationary)
    monkeypatch.setattr(routes.service, 'status', lambda: {'supported': True, 'state': 'Stopped'})
    act = Mock(return_value={'supported': True, 'state': 'NeedsLogin'})
    monkeypatch.setattr(routes.service, 'act', act)
    app = web.Application()
    routes.register(app)
    async with TestClient(TestServer(app)) as client:
      origin = str(client.make_url('')).rstrip('/')
      headers = {'Origin': origin}
      response = await client.get('/api/tailscale')
      assert response.status == 200 and (await response.json())['can_setup']
      assert response.headers['Cache-Control'] == 'no-store'
      for body in ({'action': 'shell'}, {'action': 'connect', 'auth_key': 'secret'}, [], {'action': 'install'}):
        response = await client.post('/api/tailscale', json=body, headers=headers)
        assert response.status == 400
      for bad_headers in ({}, {'Origin': 'https://evil.example'}, {'Origin': origin, 'Sec-Fetch-Site': 'cross-site'}):
        response = await client.post('/api/tailscale', json={'action': 'connect'}, headers=bad_headers)
        assert response.status == 403
      response = await client.post('/api/tailscale', data='x' * 1025, headers={**headers, 'Content-Type': 'application/json'})
      assert response.status == 413
      stationary = False
      response = await client.post('/api/tailscale', json={'action': 'connect'}, headers=headers)
      assert response.status == 409
      act.assert_not_called()
      stationary = True
      response = await client.post('/api/tailscale', json={'action': 'install', 'accept_terms': True}, headers=headers)
      assert response.status == 200
      assert act.call_args.args[0] == 'install'
  asyncio.run(run())


def test_api_rejects_overlapping_and_hides_errors(monkeypatch):
  async def run():
    monkeypatch.setattr(routes, 'stationary_offroad', lambda: True)
    monkeypatch.setattr(routes.service, 'act', Mock(side_effect=RuntimeError('secret-node-key')))
    app = web.Application()
    routes.register(app)
    async with TestClient(TestServer(app)) as client:
      headers = {'Origin': str(client.make_url('')).rstrip('/')}
      async with app[routes.LOCK]:
        response = await client.post('/api/tailscale', json={'action': 'connect'}, headers=headers)
        assert response.status == 409
      response = await client.post('/api/tailscale', json={'action': 'connect'}, headers=headers)
      assert response.status == 503 and 'secret-node-key' not in await response.text()
  asyncio.run(run())
