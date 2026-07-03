# AIDLC-MRI

AIDLC-MRI는 DICOM MRI 데이터를 불러와 axial slice를 확인하고, 수동 사각형 ROI를 입력해 면적과 추정 부피를 계산하며, 이전 검사 대비 변화량과 변화율을 확인하는 Streamlit MVP입니다.

## 의료적 주의사항

본 프로젝트는 진단 프로그램이 아닙니다. MRI 분석 보조 및 추적 관리를 위한 참고 도구이며, 최종 의학적 판단은 반드시 담당 의료진의 공식 판독과 임상 판단을 따라야 합니다.

## 주요 기능

- DICOM 폴더 경로 입력
- 폴더 내부 `.dcm` 파일 재귀 탐색
- `PixelData`가 있는 DICOM만 로딩
- `InstanceNumber` 기준 slice 정렬
- numpy 3D volume 변환
- Streamlit axial slice slider
- Window Level / Window Width 조절
- `x, y, width, height` 방식 사각형 ROI 입력
- DICOM `PixelSpacing` 기반 ROI 면적(mm²) 계산
- 여러 slice ROI 면적 합산 기반 추정 부피(mm³/ml) 계산
- 이전 검사 대비 변화량, 변화율, 증가/감소/유지 판정
- reportlab 기반 PDF 리포트 생성
- 앱과 PDF에 의료적 주의사항 표시
- PatientID 화면 비표시

## 프로젝트 구조

```text
aidlc-mri/
├── app.py
├── requirements.txt
├── Dockerfile
├── README.md
├── data/
│   ├── raw/
│   ├── processed/
│   └── reports/
└── utils/
    ├── dicom_loader.py
    ├── roi.py
    ├── report.py
    └── change_analysis.py
```

## 기본 기술 스택

- Python
- Streamlit
- pydicom
- numpy
- matplotlib
- reportlab
- Docker

## AI 추가 기술 스택

향후 AI 기반 분석 보조 기능을 확장할 때 사용할 수 있는 기술 스택입니다. 이 기능들은 자동 진단 목적이 아니라 ROI 후보 제안, 영상 전처리, 변화 추적 보조, 연구용 모델 실험을 위한 확장 후보입니다.

- PyTorch: 딥러닝 모델 학습 및 추론
- MONAI: 의료영상 AI 파이프라인, 전처리, segmentation 모델 구성
- SimpleITK: 의료영상 resampling, registration, spacing 처리
- scikit-image: 영상 필터링, morphology, contour 처리
- OpenCV: 이미지 전처리 및 시각화 보조
- nibabel: NIfTI 형식 연동
- ONNX Runtime: 학습된 모델의 경량 추론
- MLflow: 실험 기록 및 모델 버전 관리
- DVC: 의료영상 데이터셋 버전 관리

## 실행 방법

```powershell
pip install -r requirements.txt
streamlit run app.py
```

Docker:

```powershell
docker build -t aidlc-mri .
docker run --rm -p 8501:8501 -v ${PWD}/data:/app/data aidlc-mri
```

## DICOM 데이터 준비

한 번의 MRI 검사에 해당하는 DICOM 파일을 하나의 폴더에 모읍니다. 앱에는 해당 폴더 경로를 입력합니다.

```text
data/
  raw/
    study_20260703/
      IM0001.dcm
      IM0002.dcm
      IM0003.dcm
```

필수 DICOM 정보:

- `PixelData`
- `InstanceNumber`
- `PixelSpacing`
- `SliceThickness`
- `StudyDate`
- `SeriesDescription`

`PatientID`는 개인정보가 될 수 있으므로 앱 화면에 직접 표시하지 않습니다.

## 향후 개발 계획

- Coronal / Sagittal viewer 추가
- 여러 slice별 ROI 저장 기능
- 검사 회차 관리 데이터베이스
- DICOM 익명화 워크플로우
- 이미지가 포함된 PDF 리포트
- 실제 drawing canvas 기반 ROI 입력
- 검사 간 registration 및 자동 비교
- AI 기반 ROI 후보 제안 기능
- MONAI 기반 segmentation 연구 모듈
- ONNX Runtime 기반 모델 추론 API

