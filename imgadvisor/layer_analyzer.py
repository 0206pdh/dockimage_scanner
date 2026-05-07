"""
`docker history` 기반 Docker 레이어 분석 모듈.

이 모듈은 대상 Dockerfile을 임시 태그로 실제 빌드한 뒤,
`docker image inspect`와 `docker history --no-trunc` 결과를 조합해
이미지 전체 크기와 레이어별 증분 크기를 수집한다.

전체 흐름:
  1. `analyze(path)` 호출
  2. 임시 태그로 Docker 이미지 빌드
  3. 이미지 전체 크기 조회
  4. 레이어 히스토리 파싱
  5. `LayerAnalysis` 객체로 정리
  6. 성공/실패와 무관하게 finally 블록에서 임시 이미지 삭제

주의:
  - Docker 데몬이 실행 중이어야 한다.
  - 이 분석은 실제 이미지를 빌드하므로 빌드 시간과 네트워크 비용이 들 수 있다.
  - 레이어 순서는 `docker history`와 동일하게 최신 레이어가 먼저 온다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class LayerEntry:
    """
    `docker history`에서 추출한 단일 레이어 정보.

    Attributes:
        size_bytes  : 해당 레이어가 추가한 크기(Byte).
                      메타데이터 전용 레이어라면 0일 수 있다.
        instruction : Dockerfile 명령어 종류.
                      예: RUN / COPY / ADD / ENV / CMD / ...
        display_cmd : 화면 표시용 명령 문자열.
                      너무 길면 `_truncate()`로 잘라서 출력한다.
        raw         : `docker history`의 원본 CreatedBy 문자열.
                      파싱이 이상할 때 디버깅 근거로 사용한다.
    """

    size_bytes: int
    instruction: str
    display_cmd: str
    raw: str


@dataclass
class LayerAnalysis:
    """
    빌드된 이미지의 레이어 분석 결과 전체.

    Attributes:
        image_tag       : 분석 중 임시로 사용한 이미지 태그
        dockerfile_path : 분석 대상 Dockerfile 경로
        total_bytes     : `docker image inspect` 기준 전체 이미지 크기(Byte)
        layers          : 전체 레이어 목록.
                          `docker history`와 같은 순서로, 최신 레이어가 먼저 온다.
    """

    image_tag: str
    dockerfile_path: str
    total_bytes: int
    layers: list[LayerEntry] = field(default_factory=list)
    build_time_s: float = 0.0

    @property
    def total_mb(self) -> float:
        """전체 이미지 크기를 MB 단위로 변환해 반환한다."""
        return self.total_bytes / (1024 * 1024)

    @property
    def layer_count(self) -> int:
        """수집된 전체 레이어 개수를 반환한다."""
        return len(self.layers)

    @property
    def nonempty_layers(self) -> list[LayerEntry]:
        """실제로 파일시스템 크기 변화를 만든 레이어만 반환한다."""
        return [layer for layer in self.layers if layer.size_bytes > 0]

    @property
    def history_total_bytes(self) -> int:
        """`docker history`에 보이는 각 레이어 증분 크기의 총합을 반환한다."""
        return sum(layer.size_bytes for layer in self.layers)

    def size_pct(self, layer: LayerEntry) -> float:
        """특정 레이어가 전체 레이어 증분 합계에서 차지하는 비율을 계산한다."""
        total = self.history_total_bytes
        if total == 0:
            return 0.0
        return layer.size_bytes / total * 100


def analyze(dockerfile_path: str) -> LayerAnalysis:
    """
    Dockerfile을 실제로 빌드한 뒤 레이어 정보를 분석한다.

    분석 정확도를 위해 Dockerfile을 임시 태그로 직접 빌드한다.
    빌드가 끝나면 전체 이미지 크기와 레이어 히스토리를 수집해 `LayerAnalysis`
    객체로 반환한다. 중간에 예외가 발생해도 finally 블록에서 임시 이미지를
    삭제해 로컬 환경에 찌꺼기가 남지 않게 한다.

    Args:
        dockerfile_path: 분석할 Dockerfile 경로

    Returns:
        레이어별 크기와 명령어 정보가 들어 있는 `LayerAnalysis`

    Raises:
        RuntimeError: Docker 빌드 실패, Docker 미실행 등으로 분석할 수 없을 때
    """

    # 호출마다 고유한 임시 태그를 만들어 다른 분석 작업과 충돌하지 않게 한다.
    tag = f"imgadvisor-layers-{uuid.uuid4().hex[:8]}"
    try:
        # 빌드 시간도 결과에 포함하기 위해 monotonic clock으로 측정한다.
        t0 = time.monotonic()
        _build(dockerfile_path, tag)
        build_time_s = time.monotonic() - t0

        # 동일한 임시 이미지에서 전체 크기와 레이어 목록을 각각 수집한다.
        total_bytes = _inspect_total_size(tag)
        layers = _parse_history(tag)
        return LayerAnalysis(
            image_tag=tag,
            dockerfile_path=dockerfile_path,
            total_bytes=total_bytes,
            layers=layers,
            build_time_s=build_time_s,
        )
    finally:
        # analyze 성공 여부와 관계없이 임시 이미지는 항상 정리한다.
        _cleanup(tag)


# internal helpers


def _build(dockerfile_path: str, tag: str) -> None:
    """Dockerfile을 빌드하고 결과 이미지에 임시 태그를 붙인다."""

    # Docker build context는 Dockerfile이 위치한 디렉터리로 맞춘다.
    # 그래야 상대 경로 COPY/ADD가 실제 빌드 시점과 동일하게 동작한다.
    context_dir = os.path.dirname(os.path.abspath(dockerfile_path))
    result = subprocess.run(
        ["docker", "build", "-f", os.path.abspath(dockerfile_path), "-t", tag, context_dir],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # stderr 전체가 너무 길 수 있으므로 마지막 일부만 잘라서 예외에 담는다.
        raise RuntimeError(f"Docker build failed:\n{result.stderr[-2000:]}")


def _inspect_total_size(tag: str) -> int:
    """`docker image inspect`로 전체 이미지 크기(Byte)를 조회한다."""

    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=True,
    )
    # inspect 결과는 JSON 배열이므로 첫 번째 항목의 Size 값을 읽는다.
    data = json.loads(result.stdout)[0]
    return data["Size"]


def _parse_history(tag: str) -> list[LayerEntry]:
    """
    `docker history --no-trunc` 결과를 읽어 `LayerEntry` 목록으로 변환한다.

    반환 순서는 `docker history`와 동일하며 최신 레이어가 먼저 온다.
    """

    result = subprocess.run(
        ["docker", "history", "--no-trunc", "--format", "{{.Size}}\t{{.CreatedBy}}", tag],
        capture_output=True,
        text=True,
        check=True,
    )
    entries: list[LayerEntry] = []
    for line in result.stdout.strip().splitlines():
        # 지정한 format 기준으로 탭이 없으면 비정상 라인이므로 건너뛴다.
        if "\t" not in line:
            continue

        size_str, created_by = line.split("\t", 1)
        size_bytes = _parse_size(size_str.strip())
        instruction, display_cmd = _clean_created_by(created_by.strip())
        entries.append(
            LayerEntry(
                size_bytes=size_bytes,
                instruction=instruction,
                display_cmd=display_cmd,
                raw=created_by,
            )
        )
    return entries


def _parse_size(size_str: str) -> int:
    """
    `docker history`의 크기 문자열을 Byte 정수로 변환한다.

    Docker history 출력은 기본적으로 SI 단위를 사용한다.
    예:
      "0B" -> 0
      "4.96kB" -> 4960
      "54.9MB" -> 54900000
      "1.23GB" -> 1230000000

    파싱에 실패하면 보수적으로 0을 반환한다.
    """

    s = size_str.strip().upper().replace(" ", "")
    if s in ("0", "0B", ""):
        return 0

    m = re.match(r"^([\d.]+)([KMGT]?I?B?)$", s)
    if not m:
        return 0

    value = float(m.group(1))
    unit = m.group(2)

    # Docker history는 보통 SI 배수(kB=1000)를 쓰지만,
    # 혹시 KiB/MiB/GiB 형태가 들어와도 함께 처리한다.
    multipliers: dict[str, int] = {
        "B": 1,
        "": 1,
        "KB": 1_000,
        "MB": 1_000_000,
        "GB": 1_000_000_000,
        "KIB": 1_024,
        "MIB": 1_048_576,
        "GIB": 1_073_741_824,
    }
    return int(value * multipliers.get(unit, 1))


def _clean_created_by(raw: str) -> tuple[str, str]:
    """
    `docker history`의 CreatedBy 문자열을 사람이 읽기 쉬운 형태로 정리한다.

    Docker builder 종류에 따라 CreatedBy 형식이 달라진다.

    BuildKit 예시:
        "RUN /bin/sh -c pip install flask # buildkit"
        "COPY src /app # buildkit"

    Legacy builder 예시:
        "/bin/sh -c apt-get install -y gcc"              -> RUN
        "/bin/sh -c #(nop)  CMD [\"python\", \"app\"]"   -> CMD
        "/bin/sh -c #(nop) WORKDIR /app"                 -> WORKDIR

    Returns:
        (instruction, display_cmd)
    """

    raw = raw.strip()

    # BuildKit은 문자열 앞부분에 Dockerfile 키워드가 그대로 드러나는 편이다.
    # 뒤에 붙는 "# buildkit" 표시는 분석에 불필요하므로 제거한다.
    keywords = (
        "RUN",
        "COPY",
        "ADD",
        "ENV",
        "WORKDIR",
        "CMD",
        "ENTRYPOINT",
        "USER",
        "ARG",
        "LABEL",
        "EXPOSE",
        "HEALTHCHECK",
        "SHELL",
        "VOLUME",
    )
    for keyword in keywords:
        if raw.upper().startswith(keyword + " ") or raw.upper().startswith(keyword + "\t"):
            cmd = raw[len(keyword) :].strip()
            cmd = re.sub(r"\s*#\s*buildkit\s*$", "", cmd, flags=re.IGNORECASE).strip()
            # BuildKit의 RUN도 내부적으로 /bin/sh -c 래핑이 남아 있을 수 있어 제거한다.
            cmd = re.sub(r"^/bin/sh\s+-c\s+", "", cmd)
            return keyword, _truncate(cmd)

    # legacy builder의 메타데이터 명령은 #(nop) 패턴으로 들어온다.
    nop = re.match(r"/bin/sh\s+-c\s+#\(nop\)\s+(\w+)\s+(.*)", raw, re.DOTALL)
    if nop:
        instruction = nop.group(1).upper()
        return instruction, _truncate(nop.group(2).strip())

    # 일반 shell command 형태면 RUN으로 간주한다.
    run = re.match(r"/bin/sh\s+-c\s+(.*)", raw, re.DOTALL)
    if run:
        return "RUN", _truncate(run.group(1).strip())

    # 어느 패턴에도 맞지 않으면 원문을 최대한 보존한 일반 레이어로 처리한다.
    return "LAYER", _truncate(raw)


def _truncate(text: str, max_len: int = 72) -> str:
    """출력용 문자열의 공백을 정리하고 너무 길면 잘라낸다."""

    # 여러 줄 명령이나 공백이 많은 shell 문자열을 한 줄로 보기 좋게 만든다.
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _cleanup(tag: str) -> None:
    """임시 이미지를 조용히 삭제한다. 삭제 실패는 무시한다."""

    # cleanup 자체의 실패로 원래 예외를 덮어쓰지 않도록 check=True를 쓰지 않는다.
    subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)
