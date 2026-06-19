# mri-project

## Brain MRI 3D Visualization & Volume Measurement Web Service

Brain MRI 기반 3D 병변 시각화 및 부피 계산 웹서비스 프로토타입입니다.

본 프로젝트는 의료 진단 자동화가 아니라, DICOM/NIfTI 기반 의료영상 데이터를 웹서비스에서 조회 가능한 형태로 변환하고, 2D 슬라이스 뷰어, 3D 모델 뷰어, 부피 계산 결과, 시점별 변화 추적 기능을 구현하기 위한 연구용/포트폴리오용 프로젝트입니다.

## 핵심 기능

| 기능 | 설명 |
|---|---|
| MRI 데이터 목록 관리 | T01~T12 비식별 시점 라벨로 MRI 데이터 관리 |
| 2D 슬라이스 뷰어 | MRI preview slice 확인 |
| Mask Overlay | 병변 또는 종양 의심 영역 overlay 확인 |
| 부피 계산 | voxel 개수와 spacing 기반 cm³ 계산 |
| 3D 모델 생성 | segmentation mask를 3D mesh로 변환 |
| PC/모바일 3D 뷰어 | Three.js 기반 회전/확대/축소 |
| 시점별 추적 | MRI 시점별 부피 변화량과 변화율 확인 |
| 데이터 보호 | 원본 MRI는 GitHub에 업로드하지 않음 |

## 실행 방법

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

PC 접속:

```text
http://127.0.0.1:8000
```

같은 와이파이 모바일 접속:

```text
http://내_PC_IP:8000
http://내_PC_IP:8000/three-d
```

## 샘플 데이터 생성

서버 실행 후 대시보드에서 `샘플 데이터 생성` 버튼을 누르거나 아래 API를 호출합니다.

```bash
curl -X POST http://127.0.0.1:8000/api/studies/seed
```

## 부피 계산 API 예시

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/volume ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"T08\",\"voxel_count\":39400,\"spacing_mm\":[1.0,1.0,1.0]}"
```

계산식:

```text
volume_cm3 = voxel_count * spacing_x_mm * spacing_y_mm * spacing_z_mm / 1000
```

## 실제 MRI 데이터 적용 흐름

1. 원본 DICOM CD를 `raw_private/` 또는 `mri_data/`에 보관합니다.
2. 병원명, 촬영일, 환자번호, 이름 등 식별정보는 공개하지 않습니다.
3. DICOM series를 NIfTI로 변환합니다.
4. segmentation mask를 생성하거나 외부 툴에서 가져옵니다.
5. mask voxel 개수와 spacing 정보로 부피를 계산합니다.
6. mask를 marching cubes로 GLB mesh로 변환합니다.
7. `media/models/P001/Txx/lesion_model.glb`에 저장합니다.
8. 웹에서 2D preview, overlay, 3D 모델, 부피 변화를 확인합니다.

## 데이터 분류 예시

| 시점 | 구간 | 설명 |
|---|---|---|
| T01 ~ T04 | surgery_follow_up | 외과적 수술 관련 MRI 추적 구간 |
| T04 ~ T05 | hospital_transition | 병원 또는 촬영 장비 변경 구간 |
| T05 ~ T07 | chemo_period_estimated | 항암제 치료 시점 인접 구간 |
| T08 이후 | gamma_knife_follow_up | 감마나이프 수술 이후 장기 추적 구간 |
| T09 ~ T12 | stable_follow_up | 큰 변화가 없는 안정 추적 예상 구간 |

T04~T05 구간은 병원 또는 장비 변경 가능성이 있으므로 직접적인 치료 효과 판단 구간으로 사용하지 않습니다.

## 데이터 보호 정책

- 원본 DICOM/MRI 파일은 GitHub에 업로드하지 않습니다.
- 실제 환자번호, 이름, 생년월일, 촬영일, 병원명은 공개하지 않습니다.
- MRI 시점은 T01, T02와 같은 비식별 라벨로 관리합니다.
- 병원 정보는 HOSP_A, HOSP_B와 같은 가명으로 관리합니다.
- 원본 파일은 로컬 또는 원격 PC의 private 폴더에만 보관합니다.
- 공개 저장소에는 코드, 샘플 메타데이터, 샘플 결과 JSON만 포함합니다.
- 분석 결과는 의료적 진단이 아닌 연구용 분석 보조 결과로 표시합니다.

## 주의사항

본 시스템의 분석 결과는 의료진의 진단을 대체하지 않으며, 실제 진단, 치료 효과 판정, 완치 또는 재발 여부 판단에 사용할 수 없습니다.
