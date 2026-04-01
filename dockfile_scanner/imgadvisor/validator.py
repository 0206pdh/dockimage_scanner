"""
원본 vs 최적화 Dockerfile 실제 빌드 후 크기/레이어 비교.

Docker 데몬이 실행 중이어야 사용 가능.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid

from imgadvisor.models import ValidationResult


def validate(original_path: str, optimized_path: str) -> ValidationResult:
    orig_tag = f"imgadvisor-orig-{uuid.uuid4().hex[:8]}"
    opt_tag = f"imgadvisor-opt-{uuid.uuid4().hex[:8]}"

    try:
        _build(original_path, orig_tag)
        _build(optimized_path, opt_tag)

        orig = _inspect(orig_tag)
        opt = _inspect(opt_tag)

        return ValidationResult(
            original_size_mb=orig["size"] / (1024 * 1024),
            optimized_size_mb=opt["size"] / (1024 * 1024),
            original_layers=orig["layers"],
            optimized_layers=opt["layers"],
        )
    finally:
        _cleanup(orig_tag)
        _cleanup(opt_tag)


def _build(dockerfile_path: str, tag: str) -> None:
    context_dir = os.path.dirname(os.path.abspath(dockerfile_path))
    result = subprocess.run(
        ["docker", "build", "-f", os.path.abspath(dockerfile_path), "-t", tag, context_dir],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Docker build 실패 (tag={tag}):\n{result.stderr[-2000:]}"
        )


def _inspect(tag: str) -> dict:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)[0]
    return {
        "size": data["Size"],
        "layers": len(data["RootFS"]["Layers"]),
    }


def _cleanup(tag: str) -> None:
    subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)
