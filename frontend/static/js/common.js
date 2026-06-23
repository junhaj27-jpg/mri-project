const API = window.location.origin;
window.MRI_ICON_URL = '/assets/mri-icon.jpg';
window.MRI_BANNER_URL = '/assets/mri-banner.png';

function activeMenu(path) {
  document.querySelectorAll('.menu a').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });
}

async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function apiPost(path, body = {}) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function apiUpload(path, file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API}${path}`, { method: 'POST', body: formData });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

function formatValue(value, suffix = '') {
  if (value === null || value === undefined) return '-';
  return `${value}${suffix}`;
}

function applyImageFallback(root = document) {
  root.querySelectorAll('img').forEach((img) => {
    if (img.dataset.fallbackReady === 'true') return;
    img.dataset.fallbackReady = 'true';
    img.addEventListener('error', () => {
      const fallback = img.dataset.fallback || window.MRI_ICON_URL;
      if (img.getAttribute('src') !== fallback) img.setAttribute('src', fallback);
    });
    if (img.complete && img.naturalWidth === 0) {
      img.dispatchEvent(new Event('error'));
    }
  });
}

window.apiUpload = apiUpload;
window.applyImageFallback = applyImageFallback;
document.addEventListener('DOMContentLoaded', () => applyImageFallback());
