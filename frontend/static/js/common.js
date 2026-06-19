const API = window.location.origin;

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
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function formatValue(value, suffix = '') {
  if (value === null || value === undefined) return '-';
  return `${value}${suffix}`;
}
