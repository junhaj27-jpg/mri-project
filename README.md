# Brain MRI Viewer

`mri2` 폴더에 들어 있는 병원 CD export 형태의 DICOM MRI를 Streamlit에서
확인하는 간단한 뷰어입니다.

## 현재 데이터 위치

기본 데이터 경로는 아래로 설정되어 있습니다.

```text
C:\Users\user\Desktop\mri2\mri-project-main\data
```

앱 왼쪽 입력칸에서 다른 폴더로 바꿀 수도 있습니다.

## 기능

- `mri2` 폴더 아래의 확장자 없는 DICOM 파일까지 검색
- DICOM 시리즈 목록 표시
- 선택한 시리즈를 3D volume으로 로드
- axial slice slider
- window level / window width 조절
- 표시용 뇌 영역 마스킹
- 밝은 후보 영역 contour 표시
- PDF 리포트 생성
- 화면에 PatientID를 표시하지 않음

## 실행

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

패키지를 다시 설치해야 할 때:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Docker

```powershell
docker build -t brain-mri-viewer .
docker run --rm -p 8501:8501 brain-mri-viewer
```

Docker에서 로컬 데이터를 쓰려면 볼륨으로 연결합니다.

```powershell
docker run --rm -p 8501:8501 -v C:\Users\user\Desktop\mri2\mri-project-main\data:/data -e MRI_DATA_DIR=/data brain-mri-viewer
```

## 주의

진단용 프로그램이 아닙니다. 두개골 제거와 후보 영역 표시는 시각 확인을 돕는
간단한 처리이며 의료용 segmentation 또는 자동 판독이 아닙니다.
