"""Manager-owned optional VPN. Never blocks model/control process startup."""
import fcntl
import signal
import subprocess
import threading
from pathlib import Path

from openpilot.system.tailscale import service


def main():
  if not service.supported() or not service.installed() or not service.enabled():
    return
  service.prepare()
  stop = threading.Event()
  for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda *_: stop.set())
  with (service.ROOT / 'daemon.lock').open('a') as lock:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      return
    # Do not compete with an independently installed system Tailscale service.
    if Path('/run/tailscale/tailscaled.sock').exists():
      print('Tailscale: existing system daemon detected; managed service not started')
      stop.wait(30)
      return
    command = ['sudo', '-n', str(service.binaries() / 'tailscaled'),
               f'--state={service.ROOT / "tailscaled.state"}', f'--statedir={service.ROOT / "state"}',
               f'--socket={service.ROOT / "tailscaled.sock"}', '--tun=tailscale0', '--port=0']
    child = None
    try:
      # Daemon output may contain login URLs. Do not send it to vehicle logs.
      child = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
      while not stop.wait(0.5) and child.poll() is None:
        pass
      if child.poll() is not None:
        print(f'Tailscale daemon exited ({child.returncode}); retrying later')
        stop.wait(30)
    finally:
      if child is not None and child.poll() is None:
        child.send_signal(signal.SIGINT)
        try:
          child.wait(timeout=3)
        except subprocess.TimeoutExpired:
          child.kill()
          child.wait(timeout=3)


if __name__ == '__main__':
  main()
