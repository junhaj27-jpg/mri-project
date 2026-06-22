# mri-project

# Brain & Lumbar MRI 3D Visualization and Private DICOM Analysis Web Service

이 프로젝트는 **Brain MRI 기반 2D demo viewer, T01~T14 longitudinal tracking, private MRI volume 분석, 3D GLB viewer, CD/DICOM 자동 분석 파이프라인, Lumbar Spine MRI 확장 구조**를 연결한 연구용 웹 프로토타입입니다.

본 프로젝트는 실제 의료 진단 자동화 서비스가 아닙니다.
목표는 사용자가 로컬 PC에서 MRI CD 또는 DICOM 폴더를 지정하면, 해당 데이터를 비식별화하여 분석 준비를 하고, 2D/3D 시각화와 부피 추적 결과를 확인할 수 있는 연구용/포트폴리오용 시스템을 구현하는 것입니다.

중요:

* 실제 MRI 데이터는 개인 비공개 데이터이므로 GitHub에 포함하지 않습니다.
* 실제 환자번호, 병원명, 촬영일, 병명, 진단명, 판독문 원문은 GitHub에 포함하지 않습니다.
* 공개 저장소에는 코드, 공개 가능한 demo asset, mock CSV, sample 설명만 포함합니다.
* 실제 DICOM/NIfTI/GLB/mask/volume result는 로컬 private 폴더에서만 사용합니다.
* 분석 결과는 연구용 보조 지표이며 의료진의 진단, 치료 효과 판단, 재발 여부 판단을 대체하지 않습니다.

---

# 1. Codex 작업 기준

Codex는 이 `README.md`를 기준 문서로 사용하여 프로젝트를 완성해야 합니다.

README와 실제 코드가 다를 경우, **README 기준으로 코드를 수정**합니다.

Codex는 다음 작업을 수행합니다.

1. 현재 Git 저장소 구조를 확인합니다.
2. 누락된 폴더와 파일을 생성합니다.
3. FastAPI 서버가 실행되도록 수정합니다.
4. `/`, `/viewer`, `/volume`, `/three-d`, `/private` 화면이 접속 가능하도록 만듭니다.
5. Demo Mode는 mock data만 사용하도록 만듭니다.
6. Private Analysis Mode는 로컬 ignored folder의 DICOM/NIfTI/mask만 사용하도록 만듭니다.
7. 실제 환자 식별자, 병원명, 병명, 촬영일, DICOM raw metadata가 화면/API/README/sample_data에 노출되지 않도록 만듭니다.
8. Brain MRI는 `BRAIN_T01~BRAIN_T14` 또는 `T01~T14` 기준 longitudinal tracking 데이터를 완성합니다.
9. Lumbar Spine MRI는 Brain MRI tracking과 섞지 않고 별도 `body_region`과 `study_group`으로 관리합니다.
10. CD/DICOM 폴더 자동 스캔 및 private manifest 생성 기능을 구현합니다.
11. 실행 방법과 테스트 방법을 정리합니다.

---

# 2. 프로젝트 목표

이 프로젝트의 최종 목표는 다음과 같습니다.

```text
MRI CD / DICOM Folder
        ↓
1. DICOM folder scan
        ↓
2. DICOM series grouping
        ↓
3. sensitive metadata sanitization
        ↓
4. body_region 분류
        ↓
5. study_group 분류
        ↓
6. study_label mapping
        ↓
7. DICOM to NIfTI conversion
        ↓
8. segmentation mask based volume calculation
        ↓
9. mask to GLB mesh generation
        ↓
10. private manifest result generation
        ↓
11. web-based 2D / 3D / volume trend review
```

단, 본 프로젝트는 **진단 자동화**가 아닙니다.

사용 가능 표현:

```text
target region tracking
lesion-like region visualization
longitudinal volume tracking
volume trend reference
spine region review
lumbar structure review
private analysis mode
research prototype
```

사용 금지 표현:

```text
cancer diagnosis
recurrence detection
treatment effect judgment
automatic diagnosis
clinical decision
disc herniation diagnosis
stenosis diagnosis
nerve compression diagnosis
확정 진단
재발 판단
치료 효과 확정
디스크 진단
협착 진단
신경 압박 진단
```

---

# 3. 운영 모드

## 3.1 Demo Mode

Demo Mode는 공개 GitHub 저장소에서 안전하게 실행 가능한 시연용 모드입니다.

Demo Mode에서는 실제 MRI 데이터를 사용하지 않습니다.

사용 가능한 데이터:

```text
sample_data/metadata_sample.csv
sample_data/tracking_sample.csv
public demo image asset
mock longitudinal values
placeholder 3D viewer
```

Demo Mode 기능:

* 2D demo viewer 표시
* Brain MRI T01~T14 mock volume tracking 표시
* volume chart 표시
* volume table 표시
* 3D viewer placeholder 표시
* 실제 GLB가 없어도 화면이 깨지지 않도록 처리
* mock data라는 안내문 표시

Demo Mode 금지 사항:

* 실제 DICOM 사용 금지
* 실제 NIfTI 사용 금지
* 실제 환자번호 사용 금지
* 실제 병원명 사용 금지
* 실제 촬영일 사용 금지
* 실제 병명/진단명 사용 금지
* 실제 DICOM metadata 사용 금지
* 실제 Lumbar MRI 원본 사용 금지

---

## 3.2 Private Analysis Mode

Private Analysis Mode는 사용자의 로컬 PC에서만 사용하는 모드입니다.

Private Analysis Mode에서는 실제 MRI CD 또는 DICOM 폴더를 로컬 ignored folder에 저장하고, 해당 폴더를 기반으로 분석 준비를 수행합니다.

Private Analysis Mode 기능:

* MRI CD/DICOM folder scan
* DICOM series grouping
* 민감 metadata 제거
* body region 선택 또는 분류
* Brain MRI study label mapping
* Lumbar Spine MRI study label mapping
* DICOM to NIfTI 변환 구조
* segmentation mask 기반 volume 계산
* segmentation mask 기반 GLB 생성
* 구조별 segmentation label map 기반 GLB 생성
* private manifest JSON 생성
* 웹 화면에서 sanitized result 확인

Private Analysis Mode에서도 화면/API에 직접 노출하면 안 되는 정보:

```text
PatientID
PatientName
PatientBirthDate
PatientSex
InstitutionName
ReferringPhysicianName
StudyDate
SeriesDate
AcquisitionDate
AccessionNumber
StudyInstanceUID
SeriesInstanceUID
SOPInstanceUID
StudyDescription
SeriesDescription
ProtocolName
병명
진단명
병리명
판독문 원문
실제 병원명
실제 촬영일
실제 환자번호
```

---

# 4. 비식별 코드 정책

본 프로젝트는 실제 환자번호를 사용하지 않습니다.

공개 저장소와 화면에서는 다음과 같은 비식별 코드만 사용합니다.

```text
patient_code = P001
body_region = BRAIN 또는 LUMBAR_SPINE
study_group = BRAIN_TARGET_TRACKING 또는 LUMBAR_SPINE_REVIEW
study_label = BRAIN_T01~BRAIN_T14 또는 LUMBAR_T01~
hospital_alias = HOSP_A 또는 HOSP_B 또는 HOSP_PRIVATE
diagnosis_alias = PRIVATE_DIAGNOSIS_REDACTED
finding_group = TARGET_REGION_TRACKING 또는 SPINE_REGION_REVIEW
```

의미:

* `P001`: 동일 환자를 나타내는 내부 비식별 코드
* `BRAIN`: Brain MRI 데이터
* `LUMBAR_SPINE`: Lumbar Spine MRI 데이터
* `BRAIN_TARGET_TRACKING`: Brain MRI target region tracking group
* `LUMBAR_SPINE_REVIEW`: Lumbar Spine MRI private review group
* `BRAIN_T01~BRAIN_T14`: Brain MRI 비식별 시점 라벨
* `LUMBAR_T01~`: Lumbar Spine MRI 비식별 시점 라벨
* `HOSP_A`: 초기 촬영 구간 또는 병원/장비 alias
* `HOSP_B`: 이후 장기 추적 구간 또는 병원/장비 alias
* `HOSP_PRIVATE`: private local review용 병원/장비 alias
* `PRIVATE_DIAGNOSIS_REDACTED`: 실제 병명/진단명을 대체하는 비식별 값
* `TARGET_REGION_TRACKING`: target region 추적 목적을 나타내는 일반화된 분류
* `SPINE_REGION_REVIEW`: spine region 검토 목적을 나타내는 일반화된 분류

절대 사용 금지:

```text
실제 환자번호
실제 병원 등록번호
실제 DICOM PatientID
실제 병원명
실제 촬영일
실제 병명
실제 진단명
실제 병리명
AccessionNumber
StudyInstanceUID
SeriesInstanceUID
SOPInstanceUID
DICOM StudyDescription 원문
DICOM SeriesDescription 원문
DICOM ProtocolName 원문
```

---

# 5. Brain MRI tracking 정책

Brain MRI는 이 프로젝트의 기본 longitudinal tracking 대상입니다.

Brain MRI의 추적 시점은 총 14개입니다.

권장 study label:

```text
BRAIN_T01
BRAIN_T02
BRAIN_T03
BRAIN_T04
BRAIN_T05
BRAIN_T06
BRAIN_T07
BRAIN_T08
BRAIN_T09
BRAIN_T10
BRAIN_T11
BRAIN_T12
BRAIN_T13
BRAIN_T14
```

기존 코드에서 이미 `T01~T14`를 사용하고 있다면 유지해도 됩니다.
단, Lumbar Spine MRI와 섞이지 않도록 `body_region`과 `study_group`을 반드시 함께 사용합니다.

Brain MRI 기본 필드:

```text
patient_code = P001
body_region = BRAIN
study_group = BRAIN_TARGET_TRACKING
study_label = BRAIN_T01~BRAIN_T14 또는 T01~T14
finding_group = TARGET_REGION_TRACKING
diagnosis_alias = PRIVATE_DIAGNOSIS_REDACTED
```

---

# 6. Brain MRI 병원 alias 및 품질 구간 정책

실제 병원명은 사용하지 않습니다.

대신 다음 alias만 사용합니다.

```text
HOSP_A
HOSP_B
```

## Brain T01~T04

```text
hospital_alias = HOSP_A
quality_flag = baseline_reference
comparison_role = reference_only
```

설명:

T01~T04는 초기 촬영 구간입니다.
병원, 장비, 촬영 조건, 해상도, 영상 품질 차이가 있을 수 있으므로 직접적인 정량 비교에는 주의가 필요한 reference 구간으로 처리합니다.

## Brain T05

```text
hospital_alias = HOSP_B
quality_flag = transition_caution
comparison_role = transition_point
```

설명:

T05는 병원 또는 장비 전환 가능성이 있는 시점입니다.
치료 효과 판단이나 직접 비교 기준으로 사용하지 않고 transition point로 표시합니다.

## Brain T06~T14

```text
hospital_alias = HOSP_B
quality_flag = longitudinal_tracking
comparison_role = tracking_target
```

설명:

T06~T14는 장기 추적 비교 중심 구간입니다.
volume trend와 longitudinal change review 중심으로 사용합니다.

---

# 7. Lumbar Spine MRI 확장 정책

Lumbar Spine MRI는 Brain MRI tracking과 섞지 않습니다.

Lumbar Spine MRI는 별도 확장 데이터로 관리합니다.

```text
body_region = LUMBAR_SPINE
study_group = LUMBAR_SPINE_REVIEW
study_label = LUMBAR_T01, LUMBAR_T02, ...
```

Lumbar Spine MRI의 목적:

* 로컬 비공개 MRI 2D viewer 확인
* spine region review
* lumbar structure review
* 선택적 structure/region annotation
* 필요 시 segmentation mask 기반 volume 또는 structure mesh 생성

Lumbar Spine MRI에서 금지되는 표현:

```text
disc herniation diagnosis
stenosis diagnosis
nerve compression diagnosis
recurrence detection
treatment effect judgment
디스크 확정 진단
협착 확정 진단
신경 압박 확정 진단
```

사용 가능한 표현:

```text
spine region review
lumbar structure review
disc-level review
target region review
private lumbar MRI review
not for diagnosis
```

Lumbar Spine MRI 기본값:

```text
patient_code = P001
body_region = LUMBAR_SPINE
study_group = LUMBAR_SPINE_REVIEW
study_label = LUMBAR_T01
hospital_alias = HOSP_PRIVATE
quality_flag = private_reference
comparison_role = reference_review
finding_group = SPINE_REGION_REVIEW
diagnosis_alias = PRIVATE_DIAGNOSIS_REDACTED
note = private lumbar spine MRI review data; not for diagnosis
```

권장 private 경로:

```text
data/private/P001/lumbar/LUMBAR_T01/
data/private/P001/lumbar/LUMBAR_T02/
data/private/P001/lumbar/LUMBAR_T03/
```

Brain MRI 권장 private 경로:

```text
data/private/P001/brain/BRAIN_T01/
data/private/P001/brain/BRAIN_T02/
data/private/P001/brain/BRAIN_T03/
```

---

# 8. Brain MRI mock tracking sample

예시 `sample_data/tracking_sample.csv`:

```csv
patient_code,body_region,study_group,study_label,period,event_group,hospital_alias,volume_cm3,quality_flag,comparison_role,finding_group,diagnosis_alias,note
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T01,BRAIN_T01~BRAIN_T04,initial_reference,HOSP_A,52.8,baseline_reference,reference_only,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value; cross-hospital comparison caution
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T02,BRAIN_T01~BRAIN_T04,initial_reference,HOSP_A,50.1,baseline_reference,reference_only,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value; cross-hospital comparison caution
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T03,BRAIN_T01~BRAIN_T04,initial_reference,HOSP_A,48.7,baseline_reference,reference_only,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value; cross-hospital comparison caution
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T04,BRAIN_T01~BRAIN_T04,initial_reference,HOSP_A,45.3,baseline_reference,reference_only,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value; cross-hospital comparison caution
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T05,BRAIN_T04~BRAIN_T05,hospital_transition,HOSP_B,44.9,transition_caution,transition_point,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value; hospital or scanner transition point
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T06,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,42.0,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T07,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,39.8,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T08,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,36.5,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T09,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,34.1,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T10,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,31.6,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T11,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,29.4,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T12,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,27.9,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T13,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,26.2,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
P001,BRAIN,BRAIN_TARGET_TRACKING,BRAIN_T14,BRAIN_T06~BRAIN_T14,long_term_follow_up,HOSP_B,24.8,longitudinal_tracking,tracking_target,TARGET_REGION_TRACKING,PRIVATE_DIAGNOSIS_REDACTED,mock demo value
```

주의:

* 위 수치는 mock demo value입니다.
* 실제 환자 결과가 아닙니다.
* 치료 효과 판단에 사용할 수 없습니다.

---

# 9. Lumbar Spine MRI sample policy

Lumbar Spine MRI는 public sample_data에 실제 정보를 넣지 않습니다.

필요한 경우 demo row는 다음처럼 비식별 mock 값만 사용합니다.

```csv
patient_code,body_region,study_group,study_label,hospital_alias,quality_flag,comparison_role,finding_group,diagnosis_alias,note
P001,LUMBAR_SPINE,LUMBAR_SPINE_REVIEW,LUMBAR_T01,HOSP_PRIVATE,private_reference,reference_review,SPINE_REGION_REVIEW,PRIVATE_DIAGNOSIS_REDACTED,mock lumbar private review placeholder; not for diagnosis
```

Lumbar Spine MRI는 Brain MRI volume tracking 그래프에 포함하지 않습니다.

---

# 10. 프로젝트 구조

Codex는 다음 구조가 없으면 생성합니다.

```text
backend/
  main.py
  models.py
  schemas.py
  routers/
    studies.py
    tracking.py
    analysis.py
    private_analysis.py
  services/
    nifti_volume.py
    mesh_generator.py
    structure_masks.py
    dicom_scanner.py
    deidentify.py
    dicom_to_nifti.py
    private_pipeline.py

frontend/
  index.html
  viewer.html
  volume.html
  three_d.html
  private.html
  static/
    css/
      style.css
    js/
      app.js
      viewer.js
      volume.js
      three_d.js
      private.js

sample_data/
  README.md
  metadata_sample.csv
  tracking_sample.csv

requirements.txt
.gitignore
README.md
```

---

# 11. FastAPI 서버 요구사항

`backend/main.py`는 FastAPI 앱을 생성합니다.

필수 조건:

* frontend 정적 파일을 mount합니다.
* `/` 접속 시 `frontend/index.html`을 반환합니다.
* `/viewer` 접속 시 `frontend/viewer.html`을 반환합니다.
* `/volume` 접속 시 `frontend/volume.html`을 반환합니다.
* `/three-d` 접속 시 `frontend/three_d.html`을 반환합니다.
* `/private` 접속 시 `frontend/private.html`을 반환합니다.
* API router를 연결합니다.

필수 API:

```text
GET  /api/studies
POST /api/studies/seed
GET  /api/tracking
POST /api/analysis/volume
POST /api/analysis/volume/nifti
POST /api/analysis/mesh
POST /api/analysis/structure-mesh
POST /api/private/scan-dicom
POST /api/private/run-pipeline
GET  /api/private/manifest/{patient_code}
```

---

# 12. 주요 API 요구사항

## 12.1 Mock study seed

```bash
curl -X POST http://127.0.0.1:8000/api/studies/seed
```

역할:

* Demo Mode용 mock metadata 생성
* Brain MRI T01~T14 mock tracking values 생성
* Lumbar Spine MRI placeholder row 생성 가능
* 실제 DICOM/NIfTI/GLB/mask 파일은 생성하지 않음
* 실제 환자번호, 병원명, 병명, 촬영일을 생성하지 않음

---

## 12.2 Tracking API

```bash
curl http://127.0.0.1:8000/api/tracking
```

역할:

* Brain MRI T01~T14 tracking data 반환
* `patient_code = P001`
* `body_region = BRAIN`
* `study_group = BRAIN_TARGET_TRACKING`
* `hospital_alias = HOSP_A 또는 HOSP_B`
* `diagnosis_alias = PRIVATE_DIAGNOSIS_REDACTED`
* `finding_group = TARGET_REGION_TRACKING`
* raw metadata 반환 금지

---

## 12.3 Voxel count 기반 부피 계산

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/volume ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"BRAIN_T08\",\"voxel_count\":39400,\"spacing_mm\":[1.0,1.0,1.0]}"
```

계산식:

```text
volume_cm3 = voxel_count * spacing_x_mm * spacing_y_mm * spacing_z_mm / 1000
```

역할:

* voxel count 기반 volume 계산
* 실제 MRI 원본 없이 계산 가능
* Demo와 Private 양쪽에서 재사용 가능

---

## 12.4 Private NIfTI mask 기반 부피 계산

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/volume/nifti ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"BRAIN\",\"study_label\":\"BRAIN_T08\",\"mask_nifti_path\":\"data/private/P001/brain/BRAIN_T08/tumor_mask.nii.gz\"}"
```

역할:

* private local NIfTI mask를 읽음
* voxel count 계산
* spacing 계산
* cm³ volume 계산
* 입력 파일은 GitHub에 올리지 않음
* 파일이 없으면 서버가 죽지 않고 명확한 error message 반환

---

## 12.5 Private mask 기반 GLB 생성

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/mesh ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"BRAIN\",\"study_label\":\"BRAIN_T08\",\"mask_npy_path\":\"data/private/P001/brain/BRAIN_T08/tumor_mask.npy\",\"spacing_mm\":[1.0,1.0,1.0]}"
```

역할:

* private `.npy` mask를 읽음
* marching cubes 등으로 mesh 생성
* GLB 파일로 저장
* 저장 위치는 `media/models/` 또는 `outputs/private/`
* 생성된 GLB는 GitHub에 올리지 않음

---

## 12.6 구조별 3D mesh 생성

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/structure-mesh ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"BRAIN\",\"study_label\":\"BRAIN_T08\",\"seg_nifti_path\":\"data/private/P001/brain/BRAIN_T08/synthseg_seg.nii.gz\"}"
```

역할:

* SynthSeg/FastSurfer/FreeSurfer 계열 label map 입력
* 대뇌, 소뇌, 뇌간, 해마 등 구조별 mask 분리
* 구조별 GLB 생성
* 결과 파일은 ignored path에 저장

---

# 13. Private CD/DICOM Auto Analysis Pipeline

본 프로젝트의 핵심 확장 목표는 사용자가 로컬 PC에서 MRI CD 또는 DICOM 폴더를 지정하면, 해당 폴더를 자동으로 스캔하여 비식별화된 분석 결과를 생성하는 것입니다.

## 13.1 DICOM scan API

```bash
curl -X POST http://127.0.0.1:8000/api/private/scan-dicom ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"BRAIN\",\"dicom_root_path\":\"data/private/P001/brain/BRAIN_T01\"}"
```

Lumbar Spine MRI 예시:

```bash
curl -X POST http://127.0.0.1:8000/api/private/scan-dicom ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"LUMBAR_SPINE\",\"dicom_root_path\":\"data/private/P001/lumbar/LUMBAR_T01\"}"
```

역할:

* DICOM root folder 재귀 탐색
* DICOM 파일 후보 탐색
* pydicom으로 metadata 읽기
* SeriesInstanceUID 기준 series grouping
* slice count 계산
* body_region 기준 study_group 결정
* sanitized summary 반환
* raw metadata 반환 금지

반환 예시:

```json
{
  "patient_code": "P001",
  "mode": "private_analysis",
  "body_region": "BRAIN",
  "study_group": "BRAIN_TARGET_TRACKING",
  "series_count": 4,
  "series": [
    {
      "series_key": "SERIES_001",
      "study_label": "BRAIN_T01",
      "modality": "MR",
      "slice_count": 895,
      "sanitized_description": "MRI_SERIES_REDACTED",
      "finding_group": "TARGET_REGION_TRACKING",
      "diagnosis_alias": "PRIVATE_DIAGNOSIS_REDACTED",
      "status": "ready"
    }
  ],
  "warning": "Private analysis result is not for diagnosis."
}
```

Lumbar Spine MRI 반환 예시:

```json
{
  "patient_code": "P001",
  "mode": "private_analysis",
  "body_region": "LUMBAR_SPINE",
  "study_group": "LUMBAR_SPINE_REVIEW",
  "series_count": 1,
  "series": [
    {
      "series_key": "SERIES_001",
      "study_label": "LUMBAR_T01",
      "modality": "MR",
      "slice_count": 120,
      "sanitized_description": "MRI_SERIES_REDACTED",
      "finding_group": "SPINE_REGION_REVIEW",
      "diagnosis_alias": "PRIVATE_DIAGNOSIS_REDACTED",
      "status": "ready"
    }
  ],
  "warning": "Private analysis result is not for diagnosis."
}
```

---

## 13.2 Private pipeline API

```bash
curl -X POST http://127.0.0.1:8000/api/private/run-pipeline ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"BRAIN\",\"dicom_root_path\":\"data/private/P001/brain/BRAIN_T01\",\"study_label_start\":\"BRAIN_T01\",\"auto_convert_nifti\":true,\"auto_generate_mesh\":false}"
```

Lumbar Spine MRI 예시:

```bash
curl -X POST http://127.0.0.1:8000/api/private/run-pipeline ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"LUMBAR_SPINE\",\"dicom_root_path\":\"data/private/P001/lumbar/LUMBAR_T01\",\"study_label_start\":\"LUMBAR_T01\",\"auto_convert_nifti\":true,\"auto_generate_mesh\":false}"
```

역할:

* DICOM scan
* series grouping
* sanitized metadata 생성
* body_region에 따른 study_group 결정
* Brain MRI는 BRAIN_T01~BRAIN_T14 매핑
* Lumbar Spine MRI는 LUMBAR_T01~ 매핑
* DICOM to NIfTI 변환 시도
* mask가 있으면 volume 계산
* mask가 있으면 GLB 생성
* private manifest JSON 저장

반환 예시:

```json
{
  "patient_code": "P001",
  "mode": "private_analysis",
  "body_region": "BRAIN",
  "study_group": "BRAIN_TARGET_TRACKING",
  "total_series": 4,
  "mapped_studies": ["BRAIN_T01", "BRAIN_T02", "BRAIN_T03", "BRAIN_T04"],
  "output_manifest": "outputs/private/P001/brain/manifest.json",
  "warning": "Private analysis result is not for diagnosis."
}
```

---

## 13.3 Private manifest API

```bash
curl http://127.0.0.1:8000/api/private/manifest/P001
```

역할:

* ignored output folder에 저장된 manifest를 읽음
* sanitized result만 반환
* raw metadata 반환 금지
* Brain MRI와 Lumbar Spine MRI를 구분해서 반환

---

# 14. Backend service 요구사항

## 14.1 `backend/services/dicom_scanner.py`

구현 내용:

* 입력: `dicom_root_path`, `patient_code`, `body_region`
* 하위 폴더 재귀 탐색
* DICOM 파일 후보 찾기
* pydicom으로 metadata 읽기
* SeriesInstanceUID 기준 series grouping
* series별 slice count 계산
* body_region에 따른 study_group 결정
* Brain MRI는 BRAIN_T01~BRAIN_T14에 매핑
* Lumbar Spine MRI는 LUMBAR_T01~에 매핑
* raw metadata를 그대로 반환하지 않음
* sanitized metadata만 반환

필수 반환 필드:

```text
patient_code
body_region
study_group
series_key
study_label
modality
slice_count
sanitized_description
finding_group
diagnosis_alias
status
```

---

## 14.2 `backend/services/deidentify.py`

구현 내용:

* DICOM metadata sanitizer 함수 구현
* 민감 필드 제거
* 병명/진단명 원문 제거
* 병원명 제거
* 촬영일 제거
* PatientID 제거
* UID 제거

반환 기본값:

```text
diagnosis_alias = PRIVATE_DIAGNOSIS_REDACTED
sanitized_description = MRI_SERIES_REDACTED
```

body_region별 finding_group:

```text
BRAIN -> TARGET_REGION_TRACKING
LUMBAR_SPINE -> SPINE_REGION_REVIEW
```

제거 대상:

```text
PatientID
PatientName
PatientBirthDate
PatientSex
InstitutionName
ReferringPhysicianName
StudyDate
SeriesDate
AcquisitionDate
AccessionNumber
StudyInstanceUID
SeriesInstanceUID
SOPInstanceUID
StudyDescription
SeriesDescription
ProtocolName
```

---

## 14.3 `backend/services/dicom_to_nifti.py`

구현 내용:

* DICOM series를 NIfTI로 변환하는 함수 구조 생성
* `dicom2nifti` 또는 `SimpleITK` 사용 가능
* 해당 패키지가 없어도 서버가 죽지 않도록 try/except 처리
* 변환 실패 시 명확한 error message 반환
* output path는 ignored folder만 사용

허용 output path:

```text
data/nifti/
outputs/private/
```

---

## 14.4 `backend/services/private_pipeline.py`

구현 내용:

* private analysis pipeline 통합
* DICOM scan 호출
* sanitized metadata 생성
* body_region 분기
* study_group 생성
* study_label mapping
* NIfTI 변환 시도
* mask volume 계산 가능하면 호출
* GLB mesh 생성 가능하면 호출
* manifest JSON 생성

manifest 저장 위치:

```text
outputs/private/{patient_code}/brain/manifest.json
outputs/private/{patient_code}/lumbar/manifest.json
```

주의:

* manifest에도 raw PatientID, 병원명, 병명, 촬영일, UID를 저장하지 않음
* sanitized result만 저장

---

# 15. Frontend 요구사항

## 15.1 `/`

대시보드 화면입니다.

포함 내용:

* 프로젝트 소개
* Demo Mode 설명
* Private Analysis Mode 설명
* CD/DICOM Auto Analysis Pipeline 설명
* Brain MRI tracking 설명
* Lumbar Spine MRI 확장 설명
* `/viewer`, `/volume`, `/three-d`, `/private` 이동 버튼
* 연구용 프로토타입 문구
* 의료 진단 대체 불가 문구

---

## 15.2 `/viewer`

2D demo viewer 화면입니다.

포함 내용:

* demo MRI image 표시
* slice index UI
* overlay toggle UI
* 실제 DICOM/NIfTI가 아닌 demo image라는 안내문
* Kaggle-style 2D demo는 3D 부피 계산에 사용하지 않는다는 안내문
* 실제 병명/진단명 표시 금지

---

## 15.3 `/volume`

Volume tracking 화면입니다.

포함 내용:

* Brain MRI T01~T14 또는 BRAIN_T01~BRAIN_T14 volume chart
* Brain MRI T01~T14 table
* event group 표시
* HOSP_A, HOSP_B 표시
* quality_flag 표시
* comparison_role 표시
* T05 또는 BRAIN_T05는 transition point로 표시
* mock value라는 안내문
* 실제 치료 효과 판단에 사용할 수 없다는 안내문
* Lumbar Spine MRI는 이 그래프에 섞지 않음

---

## 15.4 `/three-d`

3D GLB viewer 화면입니다.

포함 내용:

* GLB viewer 영역
* 실제 GLB가 없을 경우 placeholder 표시
* private GLB는 로컬 ignored path에서만 사용한다는 안내
* demo mesh와 private mesh 구분
* Brain/Lumbar 구분 가능하면 표시
* 실제 진단/재발 판단용이 아니라는 안내

---

## 15.5 `/private`

Private Analysis 화면입니다.

포함 내용:

* body_region 선택

  * BRAIN
  * LUMBAR_SPINE
* DICOM root path 입력
* Scan DICOM 버튼
* Run Private Pipeline 버튼
* series 목록 표시
* study label mapping 결과 표시
* volume 계산 결과 표시
* 3D mesh 생성 결과 표시
* manifest path 표시
* 경고 문구 표시

화면 경고 문구:

```text
이 기능은 로컬 비공개 MRI 데이터를 연구용으로 정리하고 시각화하기 위한 기능입니다.
분석 결과는 의료진의 진단, 치료 효과 판단, 재발 여부 판단을 대체하지 않습니다.
실제 환자번호, 병원명, 촬영일, 병명, DICOM raw metadata는 화면/API에 직접 표시하지 않습니다.
```

---

# 16. `.gitignore` 요구사항

`.gitignore`에는 반드시 다음 항목을 포함합니다.

```gitignore
.env
.venv/
__pycache__/
*.pyc

data/private/
data/dicom/
data/nifti/
outputs/private/
raw_private/

media/slices/
media/overlays/
media/masks/
media/models/
media/reports/

*.dcm
*.dicom
*.ima
*.nii
*.nii.gz
*.npy
*.npz
*.nrrd
*.mha
*.mhd
*.mgz
*.glb
*.gltf

*mask*
*volume_result*
```

주의:

* 실제 MRI 원본과 산출물은 GitHub에 포함하지 않습니다.
* 실제 DICOM/NIfTI/GLB/mask/volume result는 ignored folder에서만 사용합니다.
* `sample_data/`에는 mock CSV만 포함합니다.

---

# 17. `requirements.txt` 요구사항

프로젝트가 실행되도록 필요한 패키지를 정리합니다.

최소 포함 후보:

```text
fastapi
uvicorn
pydantic
sqlalchemy
pandas
numpy
nibabel
pydicom
scikit-image
trimesh
python-multipart
jinja2
aiofiles
```

선택 포함 후보:

```text
dicom2nifti
SimpleITK
```

주의:

* `dicom2nifti` 또는 `SimpleITK`가 설치되지 않아도 서버 자체는 실행되어야 합니다.
* optional dependency는 try/except 구조로 처리합니다.
* 변환 기능이 불가능한 경우 명확한 error message를 반환합니다.

---

# 18. 실행 방법

Windows 기준 실행 명령어:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

접속 URL:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/viewer
http://127.0.0.1:8000/volume
http://127.0.0.1:8000/three-d
http://127.0.0.1:8000/private
```

---

# 19. 테스트 명령어

## 19.1 서버 실행 확인

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## 19.2 Mock seed 확인

```bash
curl -X POST http://127.0.0.1:8000/api/studies/seed
```

## 19.3 Tracking 확인

```bash
curl http://127.0.0.1:8000/api/tracking
```

## 19.4 Voxel volume 계산 확인

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/volume ^
  -H "Content-Type: application/json" ^
  -d "{\"study_label\":\"BRAIN_T08\",\"voxel_count\":39400,\"spacing_mm\":[1.0,1.0,1.0]}"
```

## 19.5 Brain DICOM scan 확인

```bash
curl -X POST http://127.0.0.1:8000/api/private/scan-dicom ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"BRAIN\",\"dicom_root_path\":\"data/private/P001/brain/BRAIN_T01\"}"
```

## 19.6 Lumbar DICOM scan 확인

```bash
curl -X POST http://127.0.0.1:8000/api/private/scan-dicom ^
  -H "Content-Type: application/json" ^
  -d "{\"patient_code\":\"P001\",\"body_region\":\"LUMBAR_SPINE\",\"dicom_root_path\":\"data/private/P001/lumbar/LUMBAR_T01\"}"
```

DICOM 폴더가 없을 경우에도 서버가 죽으면 안 됩니다.
명확한 error message를 반환해야 합니다.

---

# 20. 실제 MRI 데이터 적용 흐름

실제 데이터는 GitHub에 포함하지 않고 로컬에서만 사용합니다.

## 20.1 Brain MRI

권장 경로:

```text
data/private/P001/brain/BRAIN_T01/
data/private/P001/brain/BRAIN_T02/
data/private/P001/brain/BRAIN_T03/
...
data/private/P001/brain/BRAIN_T14/
```

흐름:

1. 실제 Brain MRI CD 또는 DICOM 폴더를 ignored local folder에 복사합니다.
2. `/private` 화면에서 `body_region = BRAIN`을 선택합니다.
3. DICOM root path를 입력합니다.
4. Scan DICOM을 실행합니다.
5. series 목록과 sanitized metadata를 확인합니다.
6. BRAIN_T01~BRAIN_T14 매핑을 확인합니다.
7. 필요한 경우 DICOM to NIfTI 변환을 실행합니다.
8. segmentation mask가 있으면 volume 계산을 실행합니다.
9. segmentation mask가 있으면 GLB 생성을 실행합니다.
10. 결과는 ignored folder에 저장합니다.

## 20.2 Lumbar Spine MRI

권장 경로:

```text
data/private/P001/lumbar/LUMBAR_T01/
data/private/P001/lumbar/LUMBAR_T02/
data/private/P001/lumbar/LUMBAR_T03/
```

흐름:

1. 실제 Lumbar Spine MRI CD 또는 DICOM 폴더를 ignored local folder에 복사합니다.
2. `/private` 화면에서 `body_region = LUMBAR_SPINE`을 선택합니다.
3. DICOM root path를 입력합니다.
4. Scan DICOM을 실행합니다.
5. series 목록과 sanitized metadata를 확인합니다.
6. LUMBAR_T01~ 매핑을 확인합니다.
7. 필요한 경우 DICOM to NIfTI 변환을 실행합니다.
8. segmentation mask가 있으면 optional volume 계산 또는 GLB 생성을 실행합니다.
9. 결과는 ignored folder에 저장합니다.

출력 경로:

```text
outputs/private/P001/brain/
outputs/private/P001/lumbar/
media/models/
media/masks/
media/reports/
```

---

# 21. 데이터 보호 원칙

반드시 지켜야 할 원칙:

* 실제 MRI 원본은 GitHub에 올리지 않습니다.
* 실제 DICOM/NIfTI/GLB/mask는 GitHub에 올리지 않습니다.
* 실제 환자번호는 사용하지 않습니다.
* 실제 병원명은 사용하지 않습니다.
* 실제 촬영일은 사용하지 않습니다.
* 실제 병명/진단명은 사용하지 않습니다.
* DICOM raw metadata를 public API response에 반환하지 않습니다.
* Private Analysis Mode에서도 화면에는 sanitized metadata만 표시합니다.
* sample_data는 demo/mock 전용입니다.
* 분석 결과는 연구용 보조 지표입니다.
* 의료진의 진단, 치료 효과 판단, 재발 여부 판단을 대체하지 않습니다.

---

# 22. Codex 완료 기준

Codex 작업 완료 기준은 다음과 같습니다.

* `uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload` 실행 가능
* `/` 페이지 접속 가능
* `/viewer` 페이지 접속 가능
* `/volume` 페이지 접속 가능
* `/three-d` 페이지 접속 가능
* `/private` 페이지 접속 가능
* `/api/studies/seed` 동작
* `/api/tracking`에서 Brain MRI T01~T14 데이터 반환
* `/api/analysis/volume`에서 voxel count 기반 volume 계산 가능
* `/api/private/scan-dicom` 동작
* `/api/private/run-pipeline` 동작
* `body_region = BRAIN` 처리 가능
* `body_region = LUMBAR_SPINE` 처리 가능
* DICOM 폴더가 없을 때도 서버가 죽지 않음
* private API는 파일이 없을 때 명확한 error message 반환
* 실제 의료 데이터는 Git에 포함되지 않음
* raw PatientID, 병원명, 촬영일, 병명, UID가 API response에 노출되지 않음
* Brain MRI와 Lumbar Spine MRI가 같은 tracking chart에 섞이지 않음
* README, 코드, sample_data, .gitignore가 서로 일치

---

# 23. Codex 최종 응답 형식

작업 완료 후 Codex는 다음 형식으로 보고합니다.

```text
작업 완료 요약

1. 변경된 파일
- ...

2. 새로 생성한 파일
- ...

3. 추가된 API
- ...

4. 추가된 화면
- ...

5. Brain MRI 처리 방식
- ...

6. Lumbar Spine MRI 처리 방식
- ...

7. Private Analysis Mode 사용 방법
- ...

8. 현재 자동화 가능한 부분
- ...

9. 아직 수동으로 필요한 부분
- ...

10. 실행 방법
- ...

11. 테스트 방법
- ...

12. 데이터 보호 확인
- 실제 MRI/DICOM/NIfTI/GLB/mask 파일은 GitHub에 포함하지 않았음
- raw PatientID, 병원명, 촬영일, 병명, UID는 API response에 노출하지 않음
- Demo Mode는 mock data만 사용함
- Private Analysis Mode는 로컬 ignored folder 기준임
- Brain MRI와 Lumbar Spine MRI는 body_region과 study_group으로 분리함

13. 권장 Git 명령어
git status
git add .
git commit -m "Add brain and lumbar private MRI analysis structure"
git push origin main
```

---

# 24. 권장 Git 명령어

작업 완료 후 다음 명령어를 사용합니다.

```bash
git status
git add .
git commit -m "Add brain and lumbar private MRI analysis structure"
git push origin main
```

---

# 25. 주의 문구

본 프로젝트는 연구용/포트폴리오용 프로토타입입니다.

이 시스템은 의료 진단, 치료 효과 판단, 재발 여부 판단을 목적으로 하지 않습니다.
실제 임상 판단은 반드시 의료진과 의료기관의 공식 판독 및 진료 절차를 따라야 합니다.

