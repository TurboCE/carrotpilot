import io
from pathlib import Path
import subprocess
import tarfile
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from openpilot.system.tailscale import service as s


@pytest.fixture
def root(tmp_path, monkeypatch):
  monkeypatch.setattr(s, 'ROOT', tmp_path / 'tailscale')
  monkeypatch.setattr(s, 'supported', lambda: True)
  return s.ROOT


def archive(links=False):
  buffer = io.BytesIO()
  with tarfile.open(fileobj=buffer, mode='w:gz') as out:
    for name in ('tailscale', 'tailscaled'):
      member = tarfile.TarInfo(f'tailscale_{s.VERSION}_arm64/{name}')
      member.size = 4
      if links:
        member.type = tarfile.SYMTYPE
        member.linkname = '/tmp/unwanted'
      out.addfile(member, io.BytesIO(b'test'))
  return buffer.getvalue()


def download(monkeypatch, data):
  response = io.BytesIO(data)
  response.url = s.URL
  monkeypatch.setattr(s.urllib.request, 'urlopen', lambda *a, **k: response)


def test_default_off_and_no_cli_before_install(root, monkeypatch):
  cli = Mock(side_effect=AssertionError('must not call'))
  monkeypatch.setattr(s, 'cli', cli)
  assert not s.enabled() and not s.installed()
  assert s.status()['state'] == 'Stopped'
  cli.assert_not_called()


def test_install_verifies_pinned_archive_and_keeps_disabled(root, monkeypatch):
  data = archive()
  monkeypatch.setattr(s, 'SHA256', s.hashlib.sha256(data).hexdigest())
  download(monkeypatch, data)
  guard = Mock()
  s.install(guard)
  assert s.installed() and not s.enabled()
  assert guard.call_count == 2
  assert root.stat().st_mode & 0o777 == 0o700
  assert (s.binaries() / 'tailscale').stat().st_mode & 0o777 == 0o700
  assert not list(root.glob('.install-*'))


def test_checksum_failure_publishes_nothing(root, monkeypatch):
  download(monkeypatch, archive())
  with pytest.raises(RuntimeError, match='checksum'):
    s.install(lambda: None)
  assert not s.installed() and not s.binaries().exists()
  assert not list(root.glob('.install-*'))


def test_archive_symlink_is_rejected(root, monkeypatch):
  data = archive(links=True)
  monkeypatch.setattr(s, 'SHA256', s.hashlib.sha256(data).hexdigest())
  download(monkeypatch, data)
  with pytest.raises(RuntimeError, match='member'):
    s.install(lambda: None)
  assert not s.binaries().exists()


def test_ignition_change_after_download_cancels_publish(root, monkeypatch):
  data = archive()
  monkeypatch.setattr(s, 'SHA256', s.hashlib.sha256(data).hexdigest())
  download(monkeypatch, data)
  guard = Mock(side_effect=[None, PermissionError('onroad')])
  with pytest.raises(PermissionError):
    s.install(guard)
  assert not s.binaries().exists()


def test_download_size_is_bounded(root, monkeypatch):
  monkeypatch.setattr(s, 'MAX_ARCHIVE', 2)
  download(monkeypatch, b'abc')
  with pytest.raises(RuntimeError, match='too large'):
    s.install(lambda: None)


@pytest.mark.parametrize('url', ['http://login.tailscale.com/a/abc', 'https://evil.com/a/a',
                                'https://login.tailscale.com.evil/a/a', 'javascript:alert(1)',
                                'https://login.tailscale.com/a/abc?secret=x', None])
def test_auth_link_rejects_untrusted_targets(url):
  assert s.auth_url(url) == ''


def test_status_redacts_peer_and_node_keys():
  out = s.summarize({'BackendState': 'NeedsLogin', 'TailscaleIPs': ['100.64.0.2', '::1', 'bad'],
                     'AuthURL': 'https://login.tailscale.com/a/abc', 'PrivateKey': 'secret',
                     'Peer': {'private-device': {}}, 'Self': {'Online': True}})
  assert out == {'state': 'NeedsLogin', 'ips': ['100.64.0.2', '::1'],
                 'login_url': 'https://login.tailscale.com/a/abc', 'online': True}


def test_action_lock_prevents_concurrent_commands(root):
  with s.action_lock():
    with pytest.raises(RuntimeError, match='Another'):
      with s.action_lock():
        pass


@pytest.mark.parametrize('operation,command', [('disconnect', 'down'), ('logout', 'logout')])
def test_disable_waits_for_cli_and_stays_disabled_on_failure(root, monkeypatch, operation, command):
  s.prepare()
  (root / 'enabled').touch()
  (root / 'tailscaled.sock').touch()
  monkeypatch.setattr(s, 'installed', lambda: True)
  def cli(*args):
    assert s.enabled()  # manager must not stop the daemon before logout finishes
    assert args == (command,)
    return NS(returncode=1)
  monkeypatch.setattr(s, 'cli', cli)
  with pytest.raises(RuntimeError):
    s.act(operation, lambda: None)
  assert not s.enabled()


def test_cli_uses_fixed_argv_and_socket(root, monkeypatch):
  run = Mock(return_value=NS(returncode=0))
  monkeypatch.setattr(s.subprocess, 'run', run)
  s.cli('status', '--json')
  args, kwargs = run.call_args
  assert args[0] == ['sudo', '-n', str(s.binaries() / 'tailscale'), f'--socket={root / "tailscaled.sock"}', 'status', '--json']
  assert kwargs['timeout'] == 8 and 'shell' not in kwargs


def test_connect_does_not_replace_dns_routes_or_ssh(root, monkeypatch):
  s.prepare()
  (root / 'tailscaled.sock').touch()
  monkeypatch.setattr(s, 'installed', lambda: True)
  # Device-specific TUN prerequisite; do not touch the host /dev.
  original = Path.exists
  monkeypatch.setattr(Path, 'exists', lambda p: True if str(p) == '/dev/net/tun' else original(p))
  monkeypatch.setattr(s.subprocess, 'run', Mock(return_value=NS(returncode=0)))
  cli = Mock(return_value=NS(returncode=1))
  monkeypatch.setattr(s, 'cli', cli)
  monkeypatch.setattr(s, 'status', lambda: {'state': 'NeedsLogin', 'login_url': 'https://login.tailscale.com/a/test'})
  result = s.act('connect', lambda: None)
  assert s.enabled() and result['state'] == 'NeedsLogin'
  argv = cli.call_args.args
  for flag in ('--accept-dns=false', '--accept-routes=false', '--ssh=false', '--advertise-routes=',
               '--advertise-exit-node=false', '--exit-node=', '--timeout=5s'):
    assert flag in argv


@pytest.mark.parametrize('operation', ['install', 'connect', 'disconnect', 'logout'])
def test_stationary_guard_runs_before_actions(root, operation):
  with pytest.raises(PermissionError):
    s.act(operation, Mock(side_effect=PermissionError('stale')))
  assert not s.enabled()


@pytest.mark.parametrize('state,expected', [({}, False),
    ({'alive': True, 'stationary': True, 'started': False}, False),
    ({'alive': False, 'stationary': True, 'offroad': True}, False),
    ({'alive': True, 'stationary': True, 'offroad': False}, False),
    ({'alive': True, 'stationary': True, 'offroad': True}, True)])
def test_setup_requires_explicit_fresh_offroad_telemetry(state, expected):
  assert s.setup_allowed(state) is expected


def test_failed_connect_clears_autostart(root, monkeypatch):
  s.prepare()
  (root / 'tailscaled.sock').touch()
  monkeypatch.setattr(s, 'installed', lambda: True)
  original = Path.exists
  monkeypatch.setattr(Path, 'exists', lambda p: True if str(p) == '/dev/net/tun' else original(p))
  monkeypatch.setattr(s.subprocess, 'run', Mock(return_value=NS(returncode=0)))
  monkeypatch.setattr(s, 'cli', Mock(side_effect=subprocess.TimeoutExpired('tailscale', 8)))
  with pytest.raises(subprocess.TimeoutExpired):
    s.act('connect', lambda: None)
  assert not s.enabled()
