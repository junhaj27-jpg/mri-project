# Brain MRI Viewer

DICOM 뇌 MRI 폴더를 불러와 axial slice를 확인하는 최소 Streamlit 앱입니다.

## 기능

- DICOM 폴더 경로 입력
- 하위 폴더의 `.dcm` 파일 재귀 탐색
- `PixelData`가 있는 DICOM만 로딩
- `InstanceNumber` 기준 정렬
- 3D numpy volume 생성
- axial slice slider
- window level / window width 조절
- 표시용 뇌만 보기 옵션
- 밝기 기반 종양 의심 후보 표시
- `data/reports` 경로에 PDF 리포트 생성
- PatientID 화면 비표시

## 실행

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Docker

```powershell
docker build -t brain-mri-viewer .
docker run --rm -p 8501:8501 brain-mri-viewer
```

## 주의

진단 목적의 프로그램이 아닙니다. MRI 이미지를 간단히 확인하기 위한 뷰어입니다.
두개골 제거는 표시용 자동 마스크이며 의료용 segmentation이 아닙니다.
종양 의심 후보 표시는 밝기 기반 보조 표시이며 종양 진단이나 자동 판독이 아닙니다.
