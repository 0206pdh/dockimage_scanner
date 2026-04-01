"""
광범위한 COPY 범위 탐지.

COPY . . 또는 COPY . /app 처럼 컨텍스트 전체를 복사하는 패턴 감지.
.dockerignore 부재 여부도 함께 고려.
"""
from __future__ import annotations

from imgadvisor.models import DockerfileIR, Finding, Severity

_DOCKERIGNORE_EXAMPLE = (
    ".dockerignore 예시:\n"
    "    .git\n"
    "    .github\n"
    "    __pycache__\n"
    "    *.pyc\n"
    "    .env\n"
    "    .env.*\n"
    "    node_modules\n"
    "    dist\n"
    "    build\n"
    "    tests\n"
    "    *.md\n"
    "    Dockerfile*\n"
    "    docker-compose*"
)


def check(ir: DockerfileIR) -> list[Finding]:
    final = ir.final_stage
    if final is None:
        return []

    findings: list[Finding] = []

    for instr in final.copy_instructions:
        args = instr.arguments

        # 스테이지 간 복사 skip (--from=...)
        if "--from=" in args:
            continue

        parts = args.split()
        # COPY . <dest> 패턴
        if not parts or parts[0] != ".":
            continue

        if not ir.has_dockerignore:
            severity = Severity.HIGH
            recommendation = (
                ".dockerignore 파일 없음 — 불필요한 파일이 모두 이미지에 포함될 수 있음\n\n"
                "  해결 방법 1: .dockerignore 생성\n"
                f"    {_DOCKERIGNORE_EXAMPLE}\n\n"
                "  해결 방법 2: 명시적 COPY 사용\n"
                "    COPY src/ /app/src/\n"
                "    COPY pyproject.toml /app/\n"
                "    COPY requirements.txt /app/"
            )
            saving_min, saving_max = 90, 300
        else:
            severity = Severity.MEDIUM
            recommendation = (
                ".dockerignore가 존재하지만 `COPY . .`는 여전히 불필요한 파일 포함 위험\n\n"
                "  권장: 명시적 COPY 패턴\n"
                "    COPY src/ /app/src/\n"
                "    COPY requirements.txt /app/\n"
                "    COPY pyproject.toml /app/"
            )
            saving_min, saving_max = 50, 200

        findings.append(Finding(
            rule_id="BROAD_COPY_SCOPE",
            severity=severity,
            line_no=instr.line_no,
            description=f"광범위한 COPY 감지: `COPY {args}`",
            recommendation=recommendation,
            saving_min_mb=saving_min,
            saving_max_mb=saving_max,
        ))

    return findings
