"""Same-origin, offroad-only Tailscale setup; never accepts credentials or commands."""
import asyncio
import json

from aiohttp import web

from openpilot.system.tailscale import service

LOCK = web.AppKey('tailscale_lock', asyncio.Lock)


def stationary_offroad():
  # Existing Bluetooth publisher tracks fresh device/car/selfdrive telemetry.
  from .bluetooth import runtime
  state = runtime()
  return service.setup_allowed(state)


def require_offroad():
  if not stationary_offroad():
    raise PermissionError('Tailscale setup requires fresh offroad, stationary telemetry')


async def status(request):
  result = await asyncio.to_thread(service.status)
  result['can_setup'] = bool(result['supported'] and stationary_offroad())
  return web.json_response({'ok': True, **result}, headers={'Cache-Control': 'no-store'})


async def mutate(request):
  if (request.headers.get('Origin') != f'{request.scheme}://{request.host}'
      or request.headers.get('Sec-Fetch-Site') == 'cross-site'):
    raise web.HTTPForbidden(text='Same-origin requests only')
  if request.content_type != 'application/json':
    raise web.HTTPUnsupportedMediaType(text='JSON required')
  raw = await request.content.read(1025)
  if len(raw) > 1024:
    raise web.HTTPRequestEntityTooLarge(max_size=1024, actual_size=len(raw))
  try:
    body = json.loads(raw)
    if not isinstance(body, dict) or set(body) - {'action', 'accept_terms'}:
      raise ValueError('Only a fixed action is accepted; credentials are not accepted')
    operation = body.get('action')
    if operation not in ('install', 'connect', 'disconnect', 'logout'):
      raise ValueError('Unknown Tailscale action')
    if operation == 'install' and body.get('accept_terms') is not True:
      raise ValueError('Accept the Tailscale terms before installing')
    require_offroad()
    if request.app[LOCK].locked():
      raise web.HTTPConflict(text='Another Tailscale action is running')
    async with request.app[LOCK]:
      result = await asyncio.to_thread(service.act, operation, require_offroad)
    result['can_setup'] = stationary_offroad()
    return web.json_response({'ok': True, **result}, headers={'Cache-Control': 'no-store'})
  except web.HTTPException:
    raise
  except PermissionError as exc:
    return web.json_response({'ok': False, 'error': str(exc)}, status=409)
  except (ValueError, TypeError) as exc:
    return web.json_response({'ok': False, 'error': str(exc)}, status=400)
  except Exception:
    # Do not include daemon output, node state or a login URL in error logs.
    return web.json_response({'ok': False, 'error': 'Tailscale action failed. Check installation, TUN, sudo and network.'}, status=503)


def register(app):
  app[LOCK] = asyncio.Lock()
  app.router.add_get('/api/tailscale', status)
  app.router.add_post('/api/tailscale', mutate)
