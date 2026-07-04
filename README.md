# AIDLC-MRI 2D Viewer

DICOM MRI volume을 불러와 기본 화면에서 axial 2D slice를 grayscale로 보여주는 Streamlit MVP입니다.

## 핵심 기능

- DICOM 폴더 경로 입력
- `.dcm` 파일 재귀 탐색
- `PixelData`가 있는 DICOM만 로딩
- `InstanceNumber` 기준 정렬, 없으면 `ImagePositionPatient`와 파일명 fallback
- `pixel_array`를 numpy 3D volume으로 변환
- 기본 화면에서 `volume[z]` axial slice 표시
- `matplotlib.imshow(cmap="gray")` 기반 2D grayscale 표시
- Window Level / Window Width 적용
- scatter, mesh, surface plot 사용 안 함
- ROI 입력: `x, y, width, height`
- `PixelSpacing` 기반 ROI 면적 계산
- `SliceThickness` 기반 단일 slice 추정 부피 계산
- PDF report 생성
- PatientID 화면 비표시

## Advanced 기능

- 표시용 뇌만 보기
- 밝기 기반 종양 의심 후보 표시

이 기능들은 진단이나 자동 판독이 아니라 화면 확인을 돕는 보조 기능입니다.

## 실행

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## 주의

진단 목적의 프로그램이 아닙니다. MRI 이미지를 확인하기 위한 보조 뷰어이며, 최종 의학적 판단은 반드시 의료진 판독을 따라야 합니다.

