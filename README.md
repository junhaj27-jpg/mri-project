# AIDLC-MRI

## 목적

AIDLC-MRI는 MRI 영상을 진단하기 위한 프로그램이 아니라, DICOM MRI 데이터를 불러와 슬라이스를 확인하고 ROI를 수동 표시하며 검사 간 변화를 추적하기 위한 의료영상 분석 보조 MVP입니다.

## 주요 기능

- DICOM 폴더 경로 입력 기반 MRI volume 로딩
- `.dcm` 파일 자동 탐색 및 `InstanceNumber` 기준 정렬
- 3D numpy volume 변환
- Axial slice 뷰어
- Window level / window width 조절
- 사각형 ROI 수동 입력
- DICOM `PixelSpacing` 기반 ROI 면적 계산
- 여러 slice ROI 면적 기반 추정 부피 계산
- 이전 검사 대비 부피 변화량, 변화율, 증가/감소/유지 판정
- reportlab 기반 PDF 리포트 생성

## 기술 스택

- Python 3.11
- Streamlit
- pydicom
- SimpleITK
- numpy
- matplotlib
- scikit-image
- reportlab
- Docker

## 실행 방법

로컬 실행:

```powershell
pip install -r requirements.txt
streamlit run app.py
```

Docker 실행:

```powershell
docker build -t aidlc-mri .
docker run --rm -p 8501:8501 -v ${PWD}/data:/app/data aidlc-mri
```

실행 후 브라우저에서 `http://localhost:8501`로 접속합니다.

## DICOM 데이터 준비 방법

1. 한 번의 MRI 검사에 해당하는 DICOM 파일을 하나의 폴더에 모읍니다.
2. 파일 확장자는 `.dcm`이어야 합니다.
3. 각 DICOM 파일에는 `PixelData`와 `InstanceNumber`가 포함되어 있어야 합니다.
4. ROI 면적 계산에는 첫 번째 slice의 `PixelSpacing` 값을 사용합니다.
5. 환자 개인정보 보호를 위해 앱 화면에는 `PatientID`를 직접 표시하지 않습니다.

예시:

```text
data/
  raw/
    study_2026_07_03/
      IM0001.dcm
      IM0002.dcm
      IM0003.dcm
```

앱의 `DICOM 폴더 경로` 입력란에는 위 예시 기준 `data/raw/study_2026_07_03`을 입력합니다.

## 의료적 주의사항

본 프로그램은 진단 목적이 아닌 MRI 분석 보조 및 추적 관리를 위한 참고 도구입니다. 최종 의학적 판단은 반드시 담당 의료진의 공식 판독과 임상 판단을 따라야 합니다.

## 향후 개발 계획

- Coronal / Sagittal 뷰어 추가
- 여러 slice ROI 저장 및 부피 추적 UI 개선
- DICOM 익명화 워크플로우 강화
- 검사 회차별 데이터베이스 저장
- 이전 검사와 현재 검사의 정합 registration
- ROI drawing canvas 기반 직접 드로잉
- PDF 리포트에 이미지 캡처 및 변화 그래프 추가
- 테스트 데이터와 자동화 테스트 확대

