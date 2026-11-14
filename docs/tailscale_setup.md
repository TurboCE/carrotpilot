# Optional Tailscale setup

The Device → Network panel provides a default-off Tailscale installation and
account connection flow on ARM64 AGNOS comma devices. It uses the existing
Carrot Web port 7000 and ordinary SSH configuration, without enabling Tailscale
SSH, Funnel, subnet advertising, exit nodes, DNS replacement or accepted subnet
routes. The tailnet owner must restrict access to trusted users/devices and the
required ports; this integration does not edit account ACLs.

## Install and state

- Static ARM64 release: Tailscale 1.104.7, downloaded only on explicit installation.
- Official URL: `https://pkgs.tailscale.com/stable/tailscale_1.104.7_arm64.tgz`.
- Pinned archive SHA-256:
  `d6bed2720310b328b861f943d7b4016c5358a9bad60575eb51e8143b79068484`.
- Versioned executable directory: `/data/carrot/tailscale/1.104.7/`.
- Private state/socket directory: `/data/carrot/tailscale/`, mode 0700.
- `enabled` is absent by default. Installing does not create it. Connect enables
  manager startup; disconnect disables startup and retains the login. Sign out
  logs the running daemon out before disabling startup.
- Each device is approved through its own official browser link or QR code.
  No auth key, download URL, arbitrary command or peer map is accepted via HTTP.
  Only sanitized local status and an allowlisted approval URL are returned.
  State is outside the checkout and Params/profile/QR backup payloads.

Installing and changing connection state require same-origin JSON and fresh,
explicit offroad and stationary telemetry. The existing Bluetooth input daemon
publishes an additional `offroad` field only when deviceState is alive, valid
and not started. Its existing input policy is unchanged. Stale or older
publishers without that field cannot authorize setup. Installation checks the
guard again after downloading, before atomically publishing the binaries.

`tailscaled` is an optional manager process. Its supervisor takes an exclusive
lock and uses noninteractive sudo for the TUN daemon and socket CLI. It does not
block control/model startup. Existing system Tailscale sockets are not adopted
or replaced. Daemon output, which may include approval links, is not forwarded
to vehicle logs. Failed connection attempts disable automatic startup. Node
credentials persist across branch updates/reboots; disconnect before switching
to older code if remote access should stop.

## Verification

- 33 Python service, HTTP and lifecycle cases pass without native vehicle I/O.
- The production installer was exercised in a temporary directory against the
  actual official archive. The pinned digest, regular-member extraction, ARM64
  CLI version and all selected `up` flags were verified. No VPN daemon started.
- Web panel tests exercise disabled/offroad states, trusted approval links,
  TUN prerequisites and controls during an in-flight operation.
- Carrot Web build succeeds. Existing control/model behavior and NNFF commits
  are outside this feature.

No real device was installed, logged in, restarted or connected. AGNOS sudo/TUN,
actual shutdown/reboot, account approval/expiry, LTE/Wi-Fi handover and remote
web/video/SSH reachability still require device validation. This feature is not
an alternative internet connection: both the comma and the remote client need
network access.

References: [Linux static installation](https://tailscale.com/docs/install/linux),
[CLI connection flags](https://tailscale.com/docs/reference/tailscale-cli/up),
[official packages and checksums](https://pkgs.tailscale.com/stable/).
