from pathlib import Path

import numpy as np


# FreeSurfer/SynthSeg aseg-style labels. Adjust these values if a different
# segmentation LUT is used.
REGION_LABELS = {
    "cerebrum": [2, 3, 41, 42],
    "cerebellum": [7, 8, 46, 47],
    "brainstem": [16],
    "hippocampus": [17, 53],
}


def extract_region_masks(seg_nifti_path: str | Path, output_dir: str | Path) -> dict:
    import nibabel as nib

    seg_nifti_path = Path(seg_nifti_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    nii = nib.load(str(seg_nifti_path))
    seg = nii.get_fdata().astype(np.int16)

    result = {}
    for region_name, labels in REGION_LABELS.items():
        mask = np.isin(seg, labels).astype(np.uint8)
        out_path = output_dir / f"{region_name}_mask.nii.gz"
        out_nii = nib.Nifti1Image(mask, nii.affine, nii.header)
        nib.save(out_nii, str(out_path))

        result[region_name] = {
            "mask_path": str(out_path),
            "voxel_count": int(np.count_nonzero(mask)),
            "labels": labels,
        }

    return result
