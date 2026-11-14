"""Pinned static Tailscale install and fixed, bounded local commands.

No shell commands, auth keys, arbitrary download URLs or route settings come
from HTTP. Private node state lives outside the checkout and Params backups.
"""
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

VERSION = '1.104.7'
SHA256 = 'd6bed2720310b328b861f943d7b4016c5358a9bad60575eb51e8143b79068484'
URL = f'https://pkgs.tailscale.com/stable/tailscale_{VERSION}_arm64.tgz'
ROOT = Path('/data/carrot/tailscale')
MAX_ARCHIVE = 128 * 1024 * 1024


def supported():
  return Path('/TICI').is_file() and Path('/AGNOS').is_file() and platform.machine() in ('aarch64', 'arm64')


def setup_allowed(state):
  return all(state.get(key) is True for key in ('alive', 'stationary', 'offroad'))


def enabled():
  return (ROOT / 'enabled').is_file()


def binaries():
  return ROOT / VERSION


def installed():
  try:
    return (binaries() / 'verified').read_text() == SHA256 and all(
      (binaries() / name).is_file() and os.access(binaries() / name, os.X_OK) for name in ('tailscale', 'tailscaled'))
  except OSError:
    return False


def prepare():
  ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
  ROOT.chmod(0o700)


@contextlib.contextmanager
def action_lock():
  prepare()
  with (ROOT / 'action.lock').open('a') as lock:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      raise RuntimeError('Another Tailscale action is running') from None
    yield


def install(guard):
  if not supported():
    raise RuntimeError('Tailscale setup requires an ARM64 AGNOS device')
  guard()
  prepare()
  if installed():
    return
  with tempfile.TemporaryDirectory(dir=ROOT, prefix='.install-') as stage:
    stage = Path(stage)
    archive = stage / 'download.tgz'
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(URL, timeout=30) as response, archive.open('wb') as output:
      if urlsplit(response.url).scheme != 'https':
        raise RuntimeError('HTTPS download required')
      while chunk := response.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_ARCHIVE:
          raise RuntimeError('Tailscale archive is too large')
        digest.update(chunk)
        output.write(chunk)
    if digest.hexdigest() != SHA256:
      raise RuntimeError('Tailscale checksum mismatch')
    target = stage / 'bin'
    target.mkdir(mode=0o700)
    # Copy only two exact regular members. Never extract paths, links or devices.
    with tarfile.open(archive, 'r:gz') as bundle:
      for name in ('tailscale', 'tailscaled'):
        member = bundle.getmember(f'tailscale_{VERSION}_arm64/{name}')
        if not member.isfile() or not 0 < member.size <= MAX_ARCHIVE:
          raise RuntimeError('Invalid Tailscale archive member')
        with bundle.extractfile(member) as source, (target / name).open('wb') as output:
          while chunk := source.read(1024 * 1024):
            output.write(chunk)
        (target / name).chmod(0o700)
    (target / 'verified').write_text(SHA256)
    guard()  # Download may have taken minutes; do not publish after ignition-on.
    if binaries().exists():
      raise RuntimeError('Incomplete install exists; inspect the Tailscale directory')
    target.rename(binaries())


def cli(*args, timeout=8):
  return subprocess.run(['sudo', '-n', str(binaries() / 'tailscale'),
                         f'--socket={ROOT / "tailscaled.sock"}', *args],
                        capture_output=True, text=True, timeout=timeout, check=False)


def auth_url(value):
  if not isinstance(value, str):
    return ''
  parsed = urlsplit(value)
  return value if (parsed.scheme == 'https' and parsed.netloc in ('login.tailscale.com', 'controlplane.tailscale.com')
                   and re.fullmatch(r'/a/[A-Za-z0-9_-]+', parsed.path) and not parsed.query and not parsed.fragment) else ''


def summarize(data):
  addresses = []
  for value in data.get('TailscaleIPs', []):
    try:
      addresses.append(str(ipaddress.ip_address(value)))
    except ValueError:
      continue
  return {'state': str(data.get('BackendState', 'Unknown')), 'ips': addresses,
          'login_url': auth_url(data.get('AuthURL')), 'online': bool((data.get('Self') or {}).get('Online'))}


def status():
  result = {'supported': supported(), 'installed': installed(), 'enabled': enabled(),
            'version': VERSION, 'tun': Path('/dev/net/tun').exists(), 'state': 'Stopped', 'ips': [], 'login_url': ''}
  if result['installed'] and (ROOT / 'tailscaled.sock').exists():
    try:
      response = cli('status', '--json')
      # NeedsLogin may still produce a valid JSON status with a nonzero exit.
      result.update(summarize(json.loads(response.stdout)))
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
      result['state'] = 'Unavailable'
  return result


def act(operation, guard):
  with action_lock():
    guard()
    if operation == 'install':
      install(guard)
    elif operation == 'connect':
      if not supported() or not installed() or not Path('/dev/net/tun').exists():
        raise RuntimeError('Install Tailscale on a supported device with /dev/net/tun first')
      check = subprocess.run(['sudo', '-n', 'true'], capture_output=True, timeout=3, check=False)
      if check.returncode:
        raise RuntimeError('Tailscale requires noninteractive sudo')
      try:
        (ROOT / 'enabled').touch(mode=0o600)
        deadline = time.monotonic() + 10
        while not (ROOT / 'tailscaled.sock').exists():
          guard()
          if time.monotonic() >= deadline:
            (ROOT / 'enabled').unlink(missing_ok=True)
            raise RuntimeError('Tailscale daemon did not start; check manager logs')
          time.sleep(0.2)
        guard()
        response = cli('up', '--accept-dns=false', '--accept-routes=false', '--ssh=false',
                       '--advertise-routes=', '--advertise-exit-node=false', '--exit-node=', '--timeout=5s')
        # A pending browser approval is expected. Never expose raw stdout/stderr.
        current = status()
        if response.returncode and not current.get('login_url') and current['state'] != 'Running':
          raise RuntimeError('Tailscale could not connect; check network and daemon logs')
      except Exception:
        (ROOT / 'enabled').unlink(missing_ok=True)
        raise
    elif operation in ('disconnect', 'logout'):
      try:
        if installed() and (ROOT / 'tailscaled.sock').exists():
          response = cli('down' if operation == 'disconnect' else 'logout')
          if response.returncode:
            raise RuntimeError('Tailscale command failed; automatic restart is disabled')
        elif operation == 'logout' and (ROOT / 'tailscaled.state').exists():
          raise RuntimeError('Connect the daemon before removing its saved login')
      finally:
        # Let logout complete before manager stops the daemon; disable even on errors.
        (ROOT / 'enabled').unlink(missing_ok=True)
    else:
      raise ValueError('Unknown Tailscale action')
  return status()
