from __future__ import annotations

import re
from pathlib import Path

from imgadvisor.models import DockerfileIR, DockerInstruction, Stage


def _join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """백슬래시 줄 이어쓰기를 합치고 (원본 줄 번호, 합쳐진 내용) 목록 반환."""
    result: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        original_line_no = i + 1
        joined = stripped

        while joined.endswith("\\") and i + 1 < len(lines):
            joined = joined[:-1].rstrip()
            i += 1
            next_part = lines[i].strip()
            if next_part and not next_part.startswith("#"):
                joined = joined + " " + next_part

        result.append((original_line_no, joined))
        i += 1

    return result


def _collect_arg_defaults(joined: list[tuple[int, str]]) -> dict[str, str]:
    """첫 번째 FROM 이전의 ARG 기본값을 수집 (변수 치환용)."""
    args: dict[str, str] = {}
    for _, line in joined:
        if re.match(r"^FROM\s+", line, re.IGNORECASE):
            break
        m = re.match(r"^ARG\s+(\w+)(?:=(.+))?$", line, re.IGNORECASE)
        if m:
            name = m.group(1)
            default = (m.group(2) or "").strip().strip('"').strip("'")
            args[name] = default
    return args


def _substitute_vars(text: str, args: dict[str, str]) -> str:
    """${VAR} 및 $VAR 형태를 ARG 기본값으로 치환."""
    def replacer(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return args.get(name, m.group(0))

    return re.sub(r"\$\{(\w+)\}|\$(\w+)", replacer, text)


def parse(dockerfile_path: str) -> DockerfileIR:
    path = Path(dockerfile_path)
    content = path.read_text(encoding="utf-8", errors="replace")
    raw_lines = content.splitlines()

    has_dockerignore = (path.parent / ".dockerignore").exists()

    joined = _join_continuations(raw_lines)
    arg_defaults = _collect_arg_defaults(joined)

    stages: list[Stage] = []
    stage_aliases: set[str] = set()
    current_idx = -1

    for line_no, line in joined:
        m = re.match(r"^(\w+)\s*(.*)", line, re.IGNORECASE)
        if not m:
            continue

        cmd = m.group(1).upper()
        args_raw = m.group(2).strip()
        args = _substitute_vars(args_raw, arg_defaults)

        if cmd == "FROM":
            current_idx += 1
            from_m = re.match(r"^(\S+)(?:\s+AS\s+(\S+))?", args, re.IGNORECASE)
            if from_m:
                base_image = from_m.group(1)
                alias = from_m.group(2)
            else:
                base_image = args
                alias = None

            if alias:
                stage_aliases.add(alias.lower())

            # 이전 스테이지를 참조하는 FROM이면 내부 참조로 표시
            if base_image.lower() in stage_aliases:
                base_image = f"[stage:{base_image}]"

            stage = Stage(
                index=current_idx,
                base_image=base_image,
                alias=alias,
            )
            stages.append(stage)

        elif current_idx >= 0 and cmd != "ARG":
            instr = DockerInstruction(
                line_no=line_no,
                instruction=cmd,
                arguments=args,
                stage_index=current_idx,
                raw=line,
            )
            stages[current_idx].instructions.append(instr)

    if stages:
        stages[-1].is_final = True

    return DockerfileIR(
        stages=stages,
        raw_lines=raw_lines,
        path=dockerfile_path,
        has_dockerignore=has_dockerignore,
    )
