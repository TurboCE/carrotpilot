import signal
import subprocess
from types import SimpleNamespace as NS
from unittest.mock import Mock

from openpilot.system.tailscale import daemon as d


def test_disabled_service_never_launches(monkeypatch):
  monkeypatch.setattr(d.service, 'supported', lambda: True)
  monkeypatch.setattr(d.service, 'installed', lambda: True)
  monkeypatch.setattr(d.service, 'enabled', lambda: False)
  launch = Mock()
  monkeypatch.setattr(d.subprocess, 'Popen', launch)
  d.main()
  launch.assert_not_called()


def test_manager_shutdown_stops_managed_child(tmp_path, monkeypatch):
  monkeypatch.setattr(d.service, 'ROOT', tmp_path)
  for name in ('supported', 'installed', 'enabled'):
    monkeypatch.setattr(d.service, name, lambda: True)
  monkeypatch.setattr(d.signal, 'signal', lambda *_: None)
  monkeypatch.setattr(d.threading, 'Event', lambda: NS(wait=lambda _: True))
  child = Mock()
  child.poll.return_value = None
  launch = Mock(return_value=child)
  monkeypatch.setattr(d.subprocess, 'Popen', launch)
  d.main()
  child.send_signal.assert_called_once_with(signal.SIGINT)
  child.wait.assert_called_once_with(timeout=3)
  args, options = launch.call_args
  assert '--tun=tailscale0' in args[0]
  assert options['stdout'] == subprocess.DEVNULL and options['stderr'] == subprocess.DEVNULL


def test_manager_registration_is_optional_and_not_a_control_dependency():
  # Execute only the policy function: no native Cereal/Params import needed.
  import ast
  from pathlib import Path
  path = Path(__file__).resolve().parents[2] / 'manager/process_config.py'
  tree = ast.parse(path.read_text())
  node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'tailscale_enabled')
  ns = {}
  exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
  assert not ns['tailscale_enabled'](True, None, None)
  registrations = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant)
                   and n.args[0].value == 'tailscaled']
  assert len(registrations) == 1
  registration = registrations[0]
  assert registration.args[2].id == 'tailscale_enabled'
  assert next(k.value.id for k in registration.keywords if k.arg == 'enabled') == 'TICI'
