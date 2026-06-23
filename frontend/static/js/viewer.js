const PUBLIC_PREVIEW_URL = '/sample_data/kaggle_2d_demo/brain_mri/tumor/mock_brain_tumor.png';
const PUBLIC_OVERLAY_URL = '/sample_data/kaggle_2d_demo/masks/mock_brain_mri_tumor_overlay.png';

let studies = [];

async function initViewer() {
  studies = await apiGet('/api/studies');
  const select = document.getElementById('studySelect');
  select.innerHTML = studies
    .map((study) => `<option value="${study.study_label}">${study.study_label} - ${study.event_type}</option>`)
    .join('');

  showImage('preview');
}

function selectedStudy() {
  const label = document.getElementById('studySelect').value;
  return studies.find((study) => study.study_label === label);
}

function renderImage(url, altText, fallbackUrl) {
  const box = document.getElementById('imageBox');
  box.innerHTML = '';

  const img = document.createElement('img');
  img.src = url;
  img.alt = altText;
  img.dataset.fallback = fallbackUrl;
  box.appendChild(img);
  window.applyImageFallback?.(box);
}

function renderFallbackImage(kind) {
  const fallbackUrl = kind === 'overlay' ? PUBLIC_OVERLAY_URL : PUBLIC_PREVIEW_URL;
  renderImage(
    fallbackUrl,
    kind === 'overlay' ? 'Public 2D MRI reference overlay' : 'Public 2D MRI reference preview',
    fallbackUrl,
  );
}

function showImage(kind) {
  const study = selectedStudy();
  const fallbackUrl = kind === 'overlay' ? PUBLIC_OVERLAY_URL : PUBLIC_PREVIEW_URL;
  const url = kind === 'overlay' ? study?.overlay_url : study?.preview_url;

  if (!url) {
    renderFallbackImage(kind);
    return;
  }

  renderImage(url, kind === 'overlay' ? 'MRI mask overlay' : 'MRI preview slice', fallbackUrl);
}

document.getElementById('previewBtn').addEventListener('click', () => showImage('preview'));
document.getElementById('overlayBtn').addEventListener('click', () => showImage('overlay'));

initViewer().catch(() => {
  renderFallbackImage('preview');
});
