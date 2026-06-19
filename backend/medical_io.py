from pathlib import Path
import numpy as np

try:
    import nibabel as nib
except Exception:
    nib = None

try:
    import pydicom
except Exception:
    pydicom = None

try:
    import SimpleITK as sitk
except Exception:
    sitk = None


def load_nifti(nifti_path: str | Path):
    if nib is None:
        raise RuntimeError("nibabel이 설치되어 있지 않습니다")
    img = nib.load(str(nifti_path))
    data = img.get_fdata()
    spacing = img.header.get_zooms()[:3]
    return data, spacing


def dicom_series_to_nifti(dicom_dir: str | Path, output_path: str | Path):
    if sitk is None:
        raise RuntimeError("SimpleITK가 설치되어 있지 않습니다")
    dicom_dir = str(dicom_dir)
    output_path = str(output_path)
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(dicom_dir)
    if not series_ids:
        raise ValueError("DICOM series를 찾을 수 없습니다")
    file_names = reader.GetGDCMSeriesFileNames(dicom_dir, series_ids[0])
    reader.SetFileNames(file_names)
    image = reader.Execute()
    sitk.WriteImage(image, output_path)
    return output_path


def calculate_mask_volume_cm3(mask: np.ndarray, spacing_mm: tuple[float, float, float]) -> float:
    voxel_count = int(np.count_nonzero(mask))
    voxel_volume_mm3 = float(spacing_mm[0] * spacing_mm[1] * spacing_mm[2])
    return round((voxel_count * voxel_volume_mm3) / 1000.0, 3)
