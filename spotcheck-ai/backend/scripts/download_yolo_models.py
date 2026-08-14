"""Download the pinned YOLO weights used by the masking pipeline.

The files are deliberately not committed to Git. Docker builds run this script and
verify SHA-256 so an upstream replacement cannot silently enter the image.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelAsset:
    filename: str
    url: str
    sha256: str


ASSETS = (
    ModelAsset(
        filename="yolov8n.pt",
        url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
        sha256="f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
    ),
    ModelAsset(
        filename="yolov8n-face.pt",
        url=(
            "https://github.com/lindevs/yolov8-face/releases/download/1.0.1/"
            "yolov8n-face-lindevs.pt"
        ),
        sha256="b038ca653b503453a94f6e12d76feca6840b2a97d7a1322b4498c5e922f29832",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(asset: ModelAsset, destination: Path) -> None:
    if destination.exists() and _sha256(destination) == asset.sha256:
        print(f"YOLO model already verified: {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{asset.filename}.", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        print(f"Downloading {asset.filename} from {asset.url}")
        urllib.request.urlretrieve(asset.url, temporary)
        actual = _sha256(temporary)
        if actual != asset.sha256:
            raise RuntimeError(
                f"SHA-256 mismatch for {asset.filename}: expected {asset.sha256}, got {actual}"
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    output_dir = Path(os.environ.get("YOLO_MODELS_DIR", "models_weights"))
    for asset in ASSETS:
        _download(asset, output_dir / asset.filename)


if __name__ == "__main__":
    main()
