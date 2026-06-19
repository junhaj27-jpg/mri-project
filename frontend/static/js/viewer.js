let studies = [];
async function initViewer() {
  studies = await apiGet('/api/studies');
  const select = document.getElementById('studySelect');
  select.innerHTML = studies.map(s => `<option value="${s.study_label}">${s.study_label} - ${s.event_type}</option>`).join('');
}
function selectedStudy() {
  const label = document.getElementById('studySelect').value;
  return studies.find(s => s.study_label === label);
}
function showImage(kind) {
  const study = selectedStudy();
  const url = kind === 'overlay' ? study?.overlay_url : study?.preview_url;
  const box = document.getElementById('imageBox');
  if (!url) {
    box.innerHTML = '아직 생성된 이미지가 없습니다.';
    return;
  }
  box.innerHTML = `<img src="${url}" alt="${kind}">`;
}
document.getElementById('previewBtn').addEventListener('click', () => showImage('preview'));
document.getElementById('overlayBtn').addEventListener('click', () => showImage('overlay'));
initViewer().catch(() => { document.getElementById('imageBox').textContent = '샘플 데이터를 먼저 생성하세요.'; });
