from __future__ import annotations

import json
from urllib.request import urlopen


BASE_URL = "http://127.0.0.1:8000"


def read(url: str):
    with urlopen(url, timeout=60) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()


def main() -> None:
    status, content_type, body = read(f"{BASE_URL}/api/mri/metadata")
    assert status == 200, status
    assert "application/json" in content_type, content_type
    metadata = json.loads(body.decode("utf-8"))
    assert metadata.get("volume_loaded") is True, metadata
    assert metadata.get("shape"), metadata
    assert metadata.get("spacing"), metadata
    assert metadata.get("series_name"), metadata
    assert metadata.get("file_count"), metadata

    status, content_type, body = read(f"{BASE_URL}/api/mri/slice?plane=sagittal&overlay=false")
    assert status == 200, status
    assert content_type == "image/png", content_type
    assert body.startswith(b"\x89PNG\r\n\x1a\n"), body[:16]

    status, content_type, body = read(f"{BASE_URL}/api/mri/slice?plane=sagittal&index=999999&overlay=false")
    assert status == 200, status
    assert content_type == "image/png", content_type
    assert body.startswith(b"\x89PNG\r\n\x1a\n"), body[:16]

    status, content_type, body = read(f"{BASE_URL}/api/mri/slice?plane=axial&index=middle&overlay=false")
    assert status == 200, status
    assert content_type == "image/png", content_type
    assert body.startswith(b"\x89PNG\r\n\x1a\n"), body[:16]

    print("MRI slice API smoke test passed.")


if __name__ == "__main__":
    main()
