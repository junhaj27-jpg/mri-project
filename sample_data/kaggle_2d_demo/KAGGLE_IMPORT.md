# Kaggle Direct Import

이 폴더는 공개 2D MRI 데모 데이터를 Kaggle에서 직접 내려받아 정리하는 위치입니다.

## 대상 라벨

- `brain_mri/tumor`: 뇌 MRI 종양 공개 데모 데이터
- `lumbar_mri/normal`: 허리 MRI 정상/참고용 공개 데모 데이터

Kaggle JPG/PNG는 2D preview, classification demo, public reference mask/overlay, fine-tuning 준비용으로만 사용합니다. 3D 부피 계산에는 사용하지 않습니다.

## 인증

Kaggle API token이 필요합니다.

1. Kaggle 계정 > Settings > API > Create New Token
2. `%USERPROFILE%\.kaggle\kaggle.json`에 저장
3. 또는 `KAGGLE_USERNAME`, `KAGGLE_KEY` 환경 변수 설정

## 웹 API로 직접 받기

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/kaggle-direct-import ^
  -H "Content-Type: application/json" ^
  -d "{\"dataset\":\"owner/brain-mri-dataset\",\"anatomy\":\"brain_mri\",\"label\":\"tumor\",\"max_files\":200}"
```

## CLI로 직접 받기

```bash
python scripts/import_kaggle_demo.py --dataset owner/brain-mri-dataset --anatomy brain_mri --label tumor --max-files 200
python scripts/import_kaggle_demo.py --dataset owner/lumbar-spine-mri-dataset --anatomy lumbar_mri --label normal --max-files 200
```

여러 dataset을 한 번에 받을 때는 `kaggle_sources.example.json`을 `kaggle_sources.json`으로 복사한 뒤 실행합니다.

```bash
python scripts/import_kaggle_demo.py
```

## 저장 규칙

- Kaggle 원본/cache: `_downloads/`에 저장하고 GitHub에는 올리지 않습니다.
- 공개 JPG/PNG만 `brain_mri/tumor/`, `lumbar_mri/normal/`로 복사합니다.
- reference mask/overlay는 `masks/`에 생성합니다.
- `manifest.csv`에는 public demo metadata만 기록합니다.
