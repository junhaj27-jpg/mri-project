from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from mesh_builder import build_brain_mesh_from_mask, export_stl
from mri_loader import discover_dicom_series, load_dicom
from skull_stripping import run_skull_stripping


DEFAULT_DATA_DIR = Path(r"C:\Users\user\Desktop\mri2\mri-project-main\data")
DEFAULT_OUTPUT_DIR = Path("outputs") / "batch_hdbet"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch HD-BET skull stripping for the first 14 DICOM series.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=14)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    parser.add_argument("--mesh", action="store_true", default=True)
    parser.add_argument("--no-mesh", action="store_false", dest="mesh")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    series = discover_dicom_series(data_dir)
    selected = series[int(args.start) : int(args.start) + int(args.count)]
    manifest: list[dict] = []

    print(f"Found {len(series)} DICOM series. Processing {len(selected)} series from index {args.start}.")
    for offset, item in enumerate(selected):
        series_index = int(args.start) + offset
        description = str(item.get("description") or "series")
        case_name = f"series_{series_index:02d}_{safe_name(description)}"
        case_dir = output_dir / case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        done_marker = case_dir / "DONE.json"
        if args.skip_existing and done_marker.exists():
            previous = json.loads(done_marker.read_text(encoding="utf-8"))
            if previous.get("status") == "done":
                print(f"[{series_index:02d}] skip existing {description}")
                manifest.append(previous)
                continue

        started = time.time()
        record = {
            "index": series_index,
            "key": str(item.get("key")),
            "description": description,
            "file_count": int(item.get("file_count") or 0),
            "output_dir": str(case_dir),
            "status": "running",
        }
        print(f"[{series_index:02d}] load {description} ({record['file_count']} files)")
        try:
            mri = load_dicom(str(data_dir), series_key=str(item["key"]))
            result = run_skull_stripping(
                mri,
                method="HD-BET",
                output_dir=case_dir,
                hdbet_command="hd-bet",
                hdbet_device="cpu",
                fill_holes=True,
                closing_radius=3,
                remove_small_holes_threshold=5000,
                remove_small_objects_threshold=20000,
                mask_smoothing_sigma=1.0,
            )
            record.update(
                {
                    "status": "mask_done",
                    "mask_path": str(result.mask_path),
                    "refined_mask_path": str(result.refined_mask_path),
                    "filled_mask_path": str(result.filled_mask_path),
                    "brain_path": str(result.brain_path),
                    "method": result.metadata.get("method", result.method_used),
                    "warnings": result.warnings,
                    "voxels": int(result.metadata.get("voxels", 0)),
                }
            )

            if args.mesh:
                mesh = build_brain_mesh_from_mask(
                    result.filled_mask,
                    spacing=mri.spacing,
                    downsample_factor=2,
                    step_size=2,
                    smoothing_iterations=4,
                    apply_mesh_smoothing=True,
                )
                mesh_path = export_stl(mesh, case_dir / "brain_mesh_hdbet.stl")
                record.update(
                    {
                        "status": "done",
                        "mesh_path": str(mesh_path),
                        "mesh_vertices": int(len(mesh.vertices)),
                        "mesh_faces": int(len(mesh.faces)),
                        "mesh_warnings": mesh.quality_warnings or [],
                    }
                )
            else:
                record["status"] = "done"
        except Exception as exc:
            record.update({"status": "failed", "error": repr(exc)})
            print(f"[{series_index:02d}] failed: {exc}")

        record["elapsed_sec"] = round(time.time() - started, 2)
        done_marker.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest.append(record)
        print(f"[{series_index:02d}] {record['status']} in {record['elapsed_sec']}s")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {manifest_path}")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9가-힣._+-]+", "_", value).strip("_")
    return value[:80] or "series"


if __name__ == "__main__":
    main()
