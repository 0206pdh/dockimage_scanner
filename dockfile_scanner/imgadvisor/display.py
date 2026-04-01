"""
Rich 기반 터미널 출력.
"""
from __future__ import annotations

import json

from rich import box
import sys

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from imgadvisor.models import DockerfileIR, Finding, Severity, ValidationResult

# Windows 터미널 UTF-8 강제
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

console = Console()

_COLOR = {
    Severity.HIGH:   "bold red",
    Severity.MEDIUM: "bold yellow",
    Severity.LOW:    "bold cyan",
}
_LABEL = {
    Severity.HIGH:   "FAIL",
    Severity.MEDIUM: "WARN",
    Severity.LOW:    "INFO",
}
_BORDER = {
    Severity.HIGH:   "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW:    "cyan",
}


def print_analysis(ir: DockerfileIR, findings: list[Finding]) -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]imgadvisor[/bold cyan]  -  Pre-Build Analyzer",
        border_style="cyan",
    ))
    console.print()

    # ── 기본 정보 ─────────────────────────────────────────────────────────
    stage_text = str(len(ir.stages))
    if ir.is_multi_stage:
        stage_text += "  [green](multi-stage OK)[/green]"
    else:
        stage_text += "  [yellow](single-stage !)[/yellow]"

    di_text = "[green]있음[/green]" if ir.has_dockerignore else "[red]없음[/red]"

    console.print(f"  [dim]Dockerfile   :[/dim]  {ir.path}")
    console.print(f"  [dim]Stages       :[/dim]  {stage_text}")
    if ir.final_stage:
        console.print(
            f"  [dim]Final image  :[/dim]  [bold]{ir.final_stage.base_image}[/bold]"
        )
    console.print(f"  [dim].dockerignore:[/dim]  {di_text}")
    console.print()

    if not findings:
        console.print(Panel(
            "[bold green][OK]  최적화 이슈 없음[/bold green]\n"
            "현재 분석 규칙을 모두 통과했습니다.",
            border_style="green",
        ))
        return

    console.print(Rule("[dim]분석 결과[/dim]", style="dim"))
    console.print()

    for f in findings:
        _print_finding(f)

    # ── 요약 ─────────────────────────────────────────────────────────────
    console.print(Rule("[dim]요약[/dim]", style="dim"))
    console.print()

    fail_n = sum(1 for f in findings if f.severity == Severity.HIGH)
    warn_n = sum(1 for f in findings if f.severity == Severity.MEDIUM)
    info_n = sum(1 for f in findings if f.severity == Severity.LOW)

    issues_parts: list[str] = []
    if fail_n:
        issues_parts.append(f"[bold red]{fail_n} FAIL[/bold red]")
    if warn_n:
        issues_parts.append(f"[bold yellow]{warn_n} WARN[/bold yellow]")
    if info_n:
        issues_parts.append(f"[bold cyan]{info_n} INFO[/bold cyan]")

    total_min = sum(f.saving_min_mb for f in findings)
    total_max = sum(f.saving_max_mb for f in findings)

    tbl = Table(box=box.ROUNDED, show_header=False, padding=(0, 2))
    tbl.add_column("key", style="dim", no_wrap=True)
    tbl.add_column("val")
    tbl.add_row("이슈",      "  ".join(issues_parts))
    tbl.add_row("예상 절감", f"[bold green]{total_min:,} ~ {total_max:,} MB[/bold green]")
    console.print(tbl)
    console.print()

    console.print(
        "  [dim]최적화 Dockerfile 생성:[/dim]  "
        "[bold cyan]imgadvisor recommend --dockerfile <path>[/bold cyan]"
    )
    console.print()


def _print_finding(f: Finding) -> None:
    label  = _LABEL.get(f.severity, "INFO")
    color  = _COLOR.get(f.severity, "white")
    border = _BORDER.get(f.severity, "white")

    line_hint = f"  line {f.line_no}" if f.line_no else ""

    header = Text()
    header.append(f"[{label}] ", style=color)
    header.append(f.rule_id, style="bold")
    header.append(line_hint, style="dim")

    body_parts = [f"  {f.description}", ""]
    for line in f.recommendation.splitlines():
        body_parts.append(f"  {line}")

    if f.saving_min_mb > 0 or f.saving_max_mb > 0:
        body_parts += ["", f"  [dim]예상 절감:[/dim]  [green]{f.saving_display}[/green]"]

    content = Text.from_markup(str(header) + "\n" + "\n".join(body_parts))

    console.print(Panel(content, border_style=border, padding=(0, 1)))
    console.print()


def print_recommended_dockerfile(content: str) -> None:
    console.print()
    console.print(Rule("[dim]최적화 Dockerfile[/dim]", style="dim"))
    console.print(Syntax(content, "dockerfile", theme="monokai", line_numbers=True))
    console.print()


def print_validation(result: ValidationResult) -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]imgadvisor[/bold cyan]  -  Build Validation",
        border_style="cyan",
    ))
    console.print()

    size_delta = result.original_size_mb - result.optimized_size_mb
    layer_delta = result.original_layers - result.optimized_layers

    tbl = Table(box=box.ROUNDED)
    tbl.add_column("", style="dim")
    tbl.add_column("Original",  justify="right")
    tbl.add_column("Optimized", justify="right", style="green")
    tbl.add_column("절감",       justify="right")

    tbl.add_row(
        "Image size",
        f"{result.original_size_mb:.1f} MB",
        f"{result.optimized_size_mb:.1f} MB",
        f"[bold green]-{size_delta:.1f} MB  ({result.reduction_pct:.1f}%)[/bold green]",
    )
    tbl.add_row(
        "Layers",
        str(result.original_layers),
        str(result.optimized_layers),
        (f"[bold green]-{layer_delta}[/bold green]" if layer_delta > 0
         else f"[yellow]{layer_delta:+}[/yellow]"),
    )

    console.print(tbl)
    console.print()


def print_json_result(ir: DockerfileIR, findings: list[Finding]) -> None:
    data = {
        "dockerfile": ir.path,
        "stages": len(ir.stages),
        "is_multi_stage": ir.is_multi_stage,
        "final_image": ir.final_stage.base_image if ir.final_stage else None,
        "has_dockerignore": ir.has_dockerignore,
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity.value,
                "line_no": f.line_no,
                "description": f.description,
                "recommendation": f.recommendation,
                "saving_min_mb": f.saving_min_mb,
                "saving_max_mb": f.saving_max_mb,
            }
            for f in findings
        ],
        "total_saving_min_mb": sum(f.saving_min_mb for f in findings),
        "total_saving_max_mb": sum(f.saving_max_mb for f in findings),
    }
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))
