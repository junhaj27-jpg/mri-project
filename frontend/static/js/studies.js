async function loadStudies() {
  const tbody = document.getElementById('studyRows');
  try {
    const rows = await apiGet('/api/studies');
    tbody.innerHTML = rows.map((row) => `
      <tr>
        <td><b>${row.study_label}</b></td>
        <td>${row.section || '-'}</td>
        <td>${row.event_type}</td>
        <td>${row.hospital_alias || '-'}</td>
        <td>${formatValue(row.volume_cm3)}</td>
        <td>${row.memo || '-'}</td>
      </tr>`).join('');
  } catch {
    tbody.innerHTML = '<tr><td colspan="6">데이터가 없습니다. 대시보드에서 Mock 데이터를 생성하세요.</td></tr>';
  }
}

loadStudies();
