let studies = [];

async function initViewer() {
  studies = await apiGet('/api/studies');
  const select = document.getElementById('studySelect');
  select.innerHTML = studies
    .map((study) => `<option value="${study.study_label}">${study.study_label} - ${study.event_type}</option>`)
    .join('');

  if (studies.length) {
    showImage('preview');
  } else {
    renderFallbackImage('표시할 MRI 샘플 데이터가 없습니다.');
  }
}

function selectedStudy() {
  const label = document.getElementById('studySelect').value;
  return studies.find((study) => study.study_label === label);
}

function renderImage(url, altText) {
  const box = document.getElementById('imageBox');
  box.innerHTML = '';

  const img = document.createElement('img');
  img.src = url;
  img.alt = altText;
  img.dataset.fallback = window.MRI_BANNER_URL;
  box.appendChild(img);
  window.applyImageFallback?.(box);
}

function renderFallbackImage(message) {
  renderImage(window.MRI_BANNER_URL, message);
}

function showImage(kind) {
  const study = selectedStudy();
  const url = kind === 'overlay' ? study?.overlay_url : study?.preview_url;
  if (!url) {
    renderFallbackImage('아직 생성된 MRI 이미지가 없습니다.');
    return;
  }

  renderImage(url, kind === 'overlay' ? 'MRI mask overlay' : 'MRI preview slice');
}

document.getElementById('previewBtn').addEventListener('click', () => showImage('preview'));
document.getElementById('overlayBtn').addEventListener('click', () => showImage('overlay'));

initViewer().catch(() => {
  renderFallbackImage('샘플 데이터를 먼저 생성하세요.');
});
