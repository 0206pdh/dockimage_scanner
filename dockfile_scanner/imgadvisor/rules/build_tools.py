"""
빌드 도구가 final stage에 남아 있는지 탐지.

런타임에 불필요한 컴파일러, 빌드 시스템, 개발 헤더 등을 검사.
"""
from __future__ import annotations

import re

from imgadvisor.models import DockerfileIR, Finding, Severity

# 런타임에 불필요한 빌드 도구 목록
_BUILD_TOOLS: list[str] = [
    # C/C++ 컴파일러
    "gcc", "g\\+\\+", "clang", "clang\\+\\+", "llvm",
    # 빌드 시스템
    "make", "cmake", "ninja-build", "automake", "autoconf", "libtool",
    "build-essential", "pkg-config",
    # 바이너리 유틸
    "binutils", "gfortran",
    # Java 빌드
    "maven", "gradle", "ant",
    # Rust
    "cargo", "rustc",
    # 개발 헤더 (주요 패턴)
    "python3-dev", "python-dev", "libpython3-dev",
    "libpq-dev", "libssl-dev", "libffi-dev",
    "libblas-dev", "liblapack-dev",
    # 네트워크 다운로드 도구 (런타임 불필요)
    "wget",
]

# 실제 regex 패턴으로 컴파일
_PATTERNS: list[re.Pattern] = [
    re.compile(rf"\b{tool}\b", re.IGNORECASE) for tool in _BUILD_TOOLS
]


def check(ir: DockerfileIR) -> list[Finding]:
    final = ir.final_stage
    if final is None:
        return []

    found: list[str] = []
    first_line_no: int | None = None

    for instr in final.run_instructions:
        for tool_re, tool_name in zip(_PATTERNS, _BUILD_TOOLS):
            clean_name = tool_name.replace("\\+\\+", "++")
            if tool_re.search(instr.arguments) and clean_name not in found:
                found.append(clean_name)
                if first_line_no is None:
                    first_line_no = instr.line_no

    if not found:
        return []

    tools_display = ", ".join(f"`{t}`" for t in found[:6])
    if len(found) > 6:
        tools_display += f" 외 {len(found) - 6}개"

    recommendation = (
        "Multi-stage build로 빌드 도구 분리:\n"
        "  1. builder stage에서 컴파일/빌드 수행\n"
        "  2. runtime stage에는 실행에 필요한 결과물만 COPY\n\n"
        "  예시:\n"
        "    FROM python:3.11 AS builder\n"
        "    RUN apt-get install -y gcc && pip install --no-cache-dir -r requirements.txt\n\n"
        "    FROM python:3.11-slim AS runtime\n"
        "    COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11\n"
        "    COPY --from=builder /app /app"
    )

    return [Finding(
        rule_id="BUILD_TOOLS_IN_FINAL_STAGE",
        severity=Severity.HIGH,
        line_no=first_line_no,
        description=f"빌드 도구가 final stage에 존재: {tools_display}",
        recommendation=recommendation,
        saving_min_mb=100,
        saving_max_mb=400,
    )]
