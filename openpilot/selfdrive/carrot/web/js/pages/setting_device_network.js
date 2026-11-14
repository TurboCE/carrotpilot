"use strict";

let deviceNetworkRefreshTimer = null;
let deviceNetworkRefreshInFlight = false;

function shouldRefreshDeviceNetwork() {
  const deviceItems = document.getElementById("deviceItems");
  return (
    CURRENT_PAGE === "setting" &&
    CURRENT_SETTING_TAB === "device" &&
    CURRENT_DEVICE_GROUP === "Network" &&
    !document.hidden &&
    deviceItems &&
    !deviceItems.hidden &&
    deviceItems.style.display !== "none"
  );
}

function stopDeviceNetworkRefresh() {
  if (!deviceNetworkRefreshTimer) return;
  window.clearTimeout(deviceNetworkRefreshTimer);
  deviceNetworkRefreshTimer = null;
}

function scheduleDeviceNetworkRefresh(delay = DEVICE_NETWORK_REFRESH_MS) {
  stopDeviceNetworkRefresh();
  if (!shouldRefreshDeviceNetwork()) return;
  deviceNetworkRefreshTimer = window.setTimeout(() => {
    deviceNetworkRefreshTimer = null;
    refreshDeviceNetworkPanel().catch((err) => console.error("[DeviceTab]", err));
  }, delay);
}

function syncDeviceNetworkRefresh() {
  if (shouldRefreshDeviceNetwork()) scheduleDeviceNetworkRefresh();
  else stopDeviceNetworkRefresh();
}

async function refreshDeviceNetworkPanel() {
  if (!shouldRefreshDeviceNetwork() || deviceNetworkRefreshInFlight) {
    syncDeviceNetworkRefresh();
    return;
  }

  deviceNetworkRefreshInFlight = true;
  try {
    await renderDeviceItems("Network", false, { silentRefresh: true });
  } finally {
    deviceNetworkRefreshInFlight = false;
    syncDeviceNetworkRefresh();
  }
}

let deviceTailscaleStatus = null;
let deviceTailscaleBusy = false;

async function loadDeviceTailscale() {
  try {
    deviceTailscaleStatus = await requestJson('/api/tailscale', { cache: 'no-store' });
  } catch (_) {
    deviceTailscaleStatus = { state: 'Unavailable', can_setup: false };
  }
}

function tailscaleLoginUrl(value) {
  return typeof value === 'string' && /^https:\/\/(login|controlplane)\.tailscale\.com\/a\/[A-Za-z0-9_-]+$/.test(value) ? value : '';
}

function renderTailscalePanel() {
  const state = deviceTailscaleStatus || {};
  const label = getUIText(`tailscale_state_${state.state || 'Stopped'}`, state.state || 'Stopped');
  const disabled = !state.can_setup || deviceTailscaleBusy;
  const action = (name, text, blocked = false) => `<button type="button" class="smallBtn" data-tailscale-action="${name}" ${disabled || blocked ? 'disabled' : ''}>${escapeHtml(getUIText(`tailscale_${name}`, text))}</button>`;
  const login = tailscaleLoginUrl(state.login_url);
  let html = renderDeviceInfoRow('Tailscale', label);
  html += `<div class="setting device-setting"><div class="descr">${escapeHtml(getUIText('tailscale_help', 'Optional private remote access. Install and connect with ignition off. Approve this device in your own Tailscale account. Restrict access to trusted devices and ports 7000/22.'))}</div>`;
  html += `<div class="ctrl">${!state.installed ? action('install', 'Install', !state.supported) :
    action('connect', 'Connect / sign in', state.enabled || !state.tun) + action('disconnect', 'Disconnect', !state.enabled) + action('logout', 'Sign out', !state.enabled)}</div>`;
  if (deviceTailscaleBusy) html += `<div class="descr">${escapeHtml(getUIText('tailscale_working', 'Working… Installation may take a few minutes.'))}</div>`;
  if (!state.can_setup) html += `<div class="descr">${escapeHtml(getUIText('tailscale_offroad', 'Setup requires a supported AGNOS device, ignition off and fresh vehicle status.'))}</div>`;
  if (state.installed && !state.tun) html += `<div class="descr">${escapeHtml(getUIText('tailscale_no_tun', 'TUN is unavailable. Connection is disabled.'))}</div>`;
  for (const ip of state.ips || []) {
    html += `<div class="descr">${escapeHtml(ip)}${ip.includes(':') ? '' : ` · http://${escapeHtml(ip)}:7000`}</div>`;
  }
  if (login) {
    html += `<p><a href="${escapeHtml(login)}" target="_blank" rel="noopener noreferrer">${escapeHtml(getUIText('tailscale_approve', 'Open Tailscale device approval'))}</a></p>`;
    if (typeof qrcode === 'function') {
      const qr = qrcode(0, 'L');
      qr.addData(login); qr.make();
      html += `<img width="180" height="180" src="${escapeHtml(qr.createDataURL(4, 8))}" alt="${escapeHtml(getUIText('tailscale_approve', 'Open Tailscale device approval'))}" />`;
    }
  }
  return html + '</div>';
}

function bindDeviceTailscale(container) {
  container.querySelectorAll('[data-tailscale-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (deviceTailscaleBusy) return;
      const action = button.dataset.tailscaleAction;
      if (action === 'install' && !await appConfirm(getUIText('tailscale_terms', 'Download Tailscale from its official server and accept its Terms of Service (https://tailscale.com/terms)?'), { title: 'Tailscale' })) return;
      if (action === 'disconnect' || action === 'logout') {
        if (!await appConfirm(getUIText('tailscale_disconnect_confirm', 'This closes Tailscale access, including this page if opened remotely. Continue?'), { title: 'Tailscale' })) return;
      }
      if (deviceTailscaleBusy) return;
      deviceTailscaleBusy = true;
      await renderDeviceItems('Network', false, { silentRefresh: true });
      try {
        deviceTailscaleStatus = await requestJson('/api/tailscale', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, ...(action === 'install' ? { accept_terms: true } : {}) }),
        });
      } catch (err) {
        showAppToast(err.message || getUIText('tailscale_failed', 'Tailscale action failed.'), { tone: 'error' });
      } finally {
        deviceTailscaleBusy = false;
        await renderDeviceItems('Network', false, { silentRefresh: true });
      }
    });
  });
}
