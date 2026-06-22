# mri-project

## Brain MRI 3D Visualization & Volume Measurement Web Service

이 프로젝트는 **Brain MRI 기반 2D demo viewer, mock longitudinal tracking, private MRI volume 분석, 3D GLB viewer**를 연결한 연구용 웹 프로토타입입니다.

> **중요:** 실제 MRI 데이터는 개인 비공개 데이터이므로 GitHub에 포함하지 않습니다.  
> 공개 저장소에는 코드, 공개 가능한 이미지 asset, Kaggle-style 2D demo 설명, mock longitudinal data만 포함합니다.

---

## 실행 방법

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

접속:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/viewer
http://127.0.0.1:8000/volume
http://127.0.0.1:8000/three-d
```

---

## 운영 모드

### Demo Mode

Demo Mode는 공개 저장소에서 안전하게 보여줄 수 있는 화면 시연용 모드입니다.

- Kaggle-style 2D demo 이미지 또는 공개 가능한 demo 이미지만 사용합니다.
- `sample_data/metadata_sample.csv`, `sample_data/tracking_sample.csv` 같은 mock longitudinal data만 사용합니다.
- 실제 환자 DICOM/NIfTI volume을 사용하지 않습니다.
- Kaggle 2D demo는 2D viewer 시연용이며 실제 3D 부피 계산에 사용하지 않습니다.
- Demo 수치는 실제 환자 결과가 아니며 치료 효과 판단에 사용할 수 없습니다.

### Private Analysis Mode

Private Analysis Mode는 실제 비공개 로컬 MRI 데이터를 처리하는 모드입니다.

- 실제 DICOM/NIfTI volume은 로컬 private 폴더에만 둡니다.
- 실제 3D 분석은 private NIfTI/DICOM volume과 segmentation mask 입력을 기준으로 수행합니다.
- mask, GLB mesh, volume result는 GitHub에 올리지 않습니다.
- 분석 결과는 연구용 보조 지표이며 의료진의 진단을 대체하지 않습니다.

권장 로컬 경로:

```text
data/private/
data/dicom/
data/nifti/
outputs/private/
raw_private/
media/masks/
media/models/
media/reports/
```

위 경로와 주요 의료 데이터 확장자는 `.gitignore` 처리되어 있습니다.

---

## GitHub에 올리지 않는 파일

다음 파일은 실제 환자 정보 또는 분석 산출물일 수 있으므로 업로드하지 않습니다.

```text
DICOM: *.dcm, *.dicom, *.ima
NIfTI: *.nii, *.nii.gz
의료 volume/mask 배열: *.npy, *.npz, *.nrrd, *.mha, *.mhd, *.mgz
3D 산출물: *.glb, *.gltf
mask 이미지/volume result: *mask*, *volume_result*
private 폴더: data/private/, data/dicom/, data/nifti/, outputs/private/, raw_private/
generated media: media/slices/, media/overlays/, media/masks/, media/models/, media/reports/
```

현재 GitHub에 포함되는 데이터는 `sample_data/`의 mock CSV와 설명 파일뿐입니다.

---

## 프로젝트 구조

```text
backend/
  main.py                 FastAPI 앱, 정적 파일 mount, router 연결
  models.py               SQLAlchemy Study 모델
  schemas.py              API request/response schema
  routers/
    studies.py            mock study 목록 및 seed API
    tracking.py           시점별 volume tracking API
    analysis.py           volume, NIfTI volume, GLB mesh, structure mesh API
  services/
    nifti_volume.py       NIfTI mask volume 계산
    mesh_generator.py     mask -> GLB mesh 변환
    structure_masks.py    label map -> 구조별 mask 분리

frontend/
  index.html              Demo/Private mode 안내 대시보드
  viewer.html             2D preview/overlay demo viewer
  volume.html             mock/private volume tracking 화면
  three_d.html            3D GLB viewer
  static/js/              API 호출 및 viewer scripts
  static/css/style.css    화면 스타일

sample_data/
  README.md               sample_data 사용 정책
  metadata_sample.csv     mock metadata
  tracking_sample.csv     mock longitudinal tracking
```

---

## 주요 API

### Mock study seed

```bash
curl -X POST http://127.0.0.1:8000/api/studies/seed
```

이 API는 Demo Mode용 mock metadata와 mock longitudinal values를 생성합니다.  
실제 3D GLB 파일은 seed하지 않습니다.

---

### Voxel count 기반 부피 계산

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/volume ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"T08\",\"voxel_count\":39400,\"spacing_mm\":[1.0,1.0,1.0]}"
```

계산식:

```text
volume_cm3 = voxel_count * spacing_x_mm * spacing_y_mm * spacing_z_mm / 1000
```

---

### Private NIfTI mask 기반 부피 계산

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/volume/nifti ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"T08\",\"mask_nifti_path\":\"data/private/P001/T08/tumor_mask.nii.gz\"}"
```

이 API는 private local NIfTI mask를 읽어 voxel count, spacing, cm³ volume을 계산합니다.  
입력 파일은 GitHub에 올리지 않습니다.

---

### Private mask 기반 GLB 생성

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/mesh ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"T08\",\"patient_code\":\"P001\",\"mask_npy_path\":\"data/private/P001/T08/tumor_mask.npy\",\"spacing_mm\":[1.0,1.0,1.0]}"
```

생성된 GLB는 ignored path인 `media/models/...`에 저장됩니다.

---

### 구조별 3D mesh 생성

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/structure-mesh ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"T08\",\"patient_code\":\"P001\",\"seg_nifti_path\":\"data/private/P001/T08/synthseg_seg.nii.gz\"}"
```

이 API는 SynthSeg/FastSurfer/FreeSurfer 계열 label map을 기준으로 대뇌, 소뇌, 뇌간, 해마 mask와 GLB를 생성합니다.  
결과 파일은 GitHub에 업로드하지 않습니다.

---

## 실제 MRI 데이터 적용 흐름

1. 실제 DICOM CD 또는 NIfTI volume을 `data/private/`, `data/dicom/`, `data/nifti/` 같은 ignored local 폴더에 저장합니다.
2. 환자 이름, 환자번호, 촬영일, 병원명 등 직접 식별자는 코드/README/sample_data에 쓰지 않습니다.
3. DICOM series를 NIfTI volume으로 변환합니다.
4. private segmentation tool로 tumor mask 또는 anatomical label map을 생성합니다.
5. `/api/analysis/volume/nifti`로 private mask volume을 계산합니다.
6. `/api/analysis/mesh` 또는 `/api/analysis/structure-mesh`로 GLB mesh를 생성합니다.
7. generated result는 `outputs/private/` 또는 ignored `media/` 경로에만 저장합니다.
8. 웹 화면에서 Private Analysis Mode로 로컬 결과만 확인합니다.

---

## 데이터 보호 원칙

- 실제 MRI 원본과 산출물은 GitHub에 올리지 않습니다.
- 공개 저장소에는 실제 환자 정보, 병원 정보, 촬영일, 원본 파일 경로를 남기지 않습니다.
- `sample_data`는 demo/mock 전용입니다.
- Kaggle 2D demo는 2D viewer 시연용입니다.
- 실제 3D 부피 계산은 private NIfTI/DICOM volume과 segmentation mask 입력을 기준으로 수행합니다.
- 분석 결과는 연구용이며 실제 진단, 치료 효과 판단, 재발 여부 판단에 사용할 수 없습니다.

