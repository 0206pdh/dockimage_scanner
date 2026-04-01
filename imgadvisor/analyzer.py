from __future__ import annotations

from imgadvisor.models import DockerfileIR, Finding
from imgadvisor.rules import base_image, build_tools, cache_cleanup, copy_scope, multi_stage

_ALL_RULES = [
    base_image.check,
    build_tools.check,
    cache_cleanup.check,
    copy_scope.check,
    multi_stage.check,
]


def analyze(ir: DockerfileIR) -> list[Finding]:
    findings: list[Finding] = []
    for rule in _ALL_RULES:
        findings.extend(rule(ir))
    return findings
