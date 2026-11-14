import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function runtime(state = {}) {
  const context = vm.createContext({
    getUIText: (_, fallback) => fallback,
    escapeHtml: (x) => String(x).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    renderDeviceInfoRow: (name, value) => `<div>${name}: ${value}</div>`,
  });
  vm.runInContext(fs.readFileSync(new URL('../js/pages/setting_device_network.js', import.meta.url), 'utf8'), context);
  context.state = state;
  vm.runInContext('deviceTailscaleStatus = state', context);
  return context;
}

test('uninstalled or offroad-unverified device cannot start setup', () => {
  const html = vm.runInContext('renderTailscalePanel()', runtime({ supported: true, can_setup: false }));
  assert.match(html, /data-tailscale-action="install" disabled/);
  assert.doesNotMatch(html, /data-tailscale-action="connect"/);
});

test('installed connected device offers disconnect and logout, not a duplicate connect', () => {
  const html = vm.runInContext('renderTailscalePanel()', runtime({ installed: true, enabled: true, tun: true, can_setup: true, state: 'Running', ips: ['100.64.0.2'] }));
  assert.match(html, /data-tailscale-action="connect" disabled/);
  assert.match(html, /data-tailscale-action="disconnect" >/);
  assert.match(html, /http:\/\/100.64.0.2:7000/);
});

test('missing TUN disables connection and displays the prerequisite', () => {
  const html = vm.runInContext('renderTailscalePanel()', runtime({ installed: true, can_setup: true, tun: false }));
  assert.match(html, /data-tailscale-action="connect" disabled/);
  assert.match(html, /TUN is unavailable/);
});

test('only Tailscale HTTPS approval links can be rendered', () => {
  for (const url of ['javascript:alert(1)', 'https://evil.com/a/a', 'https://login.tailscale.com.evil/a/a', 'https://login.tailscale.com/a/x?key=secret']) {
    const ctx = runtime({ login_url: url });
    assert.equal(ctx.tailscaleLoginUrl(url), '');
    assert.doesNotMatch(vm.runInContext('renderTailscalePanel()', ctx), /<a /);
  }
  const good = 'https://login.tailscale.com/a/abc';
  assert.match(vm.runInContext('renderTailscalePanel()', runtime({ login_url: good })), /rel="noopener noreferrer"/);
});

test('busy operations keep all setup buttons disabled', () => {
  const ctx = runtime({ installed: true, enabled: true, tun: true, can_setup: true });
  vm.runInContext('deviceTailscaleBusy = true', ctx);
  const html = vm.runInContext('renderTailscalePanel()', ctx);
  assert.equal((html.match(/data-tailscale-action="\w+" disabled/g) || []).length, 3);
});
