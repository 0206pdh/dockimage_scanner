"""
Base image 최적화 규칙.

패턴 목록을 순서대로 매칭 후 첫 번째 매칭에서 Finding 생성.
이미 slim/alpine/distroless 등 경량 이미지면 skip.
"""
from __future__ import annotations

import re
from typing import Optional

from imgadvisor.models import DockerfileIR, Finding, Patch, Severity

# (regex_pattern, list of recommendation dicts)
# recommendation dict keys: image, min, max, note
# {v} → regex group(1) 로 치환
_RULES: list[tuple[str, list[dict]]] = [
    # ── Python ──────────────────────────────────────────────────────────────
    (r"^python:(\d+\.\d+(?:\.\d+)?)$", [
        {"image": "python:{v}-slim",                  "min": 250, "max": 420, "note": None},
        {"image": "python:{v}-alpine",                "min": 350, "max": 520, "note": "musl libc 호환성 주의"},
        {"image": "gcr.io/distroless/python3",        "min": 450, "max": 630, "note": "쉘 없음, 프로덕션 권장"},
    ]),
    (r"^python:(\d+)$", [
        {"image": "python:{v}-slim",                  "min": 250, "max": 420, "note": None},
        {"image": "python:{v}-alpine",                "min": 350, "max": 520, "note": "musl libc 호환성 주의"},
    ]),
    (r"^python:latest$", [
        {"image": "python:3-slim",                    "min": 250, "max": 420, "note": "latest 태그 고정 권장"},
    ]),

    # ── Node ────────────────────────────────────────────────────────────────
    (r"^node:(\d+)$", [
        {"image": "node:{v}-slim",                    "min": 280, "max": 420, "note": None},
        {"image": "node:{v}-alpine",                  "min": 380, "max": 550, "note": "musl libc 호환성 주의"},
        {"image": "gcr.io/distroless/nodejs{v}",      "min": 450, "max": 620, "note": "쉘 없음"},
    ]),
    (r"^node:(\d+)-slim$", [
        {"image": "node:{v}-alpine",                  "min": 50,  "max": 150, "note": "musl libc 호환성 주의"},
    ]),
    (r"^node:lts$", [
        {"image": "node:lts-slim",                    "min": 280, "max": 420, "note": None},
        {"image": "node:lts-alpine",                  "min": 380, "max": 550, "note": "musl libc 호환성 주의"},
    ]),
    (r"^node:current$", [
        {"image": "node:current-slim",                "min": 280, "max": 420, "note": None},
    ]),
    (r"^node:latest$", [
        {"image": "node:lts-slim",                    "min": 280, "max": 420, "note": "latest 태그 고정 권장"},
    ]),

    # ── Java (OpenJDK — deprecated) ─────────────────────────────────────────
    (r"^openjdk:(\d+)$", [
        {"image": "eclipse-temurin:{v}-jre",              "min": 200, "max": 380, "note": "JDK→JRE 전환"},
        {"image": "gcr.io/distroless/java{v}-debian12",   "min": 350, "max": 550, "note": "쉘 없음"},
    ]),
    (r"^openjdk:(\d+)-jdk$", [
        {"image": "eclipse-temurin:{v}-jre",              "min": 200, "max": 380, "note": "JDK→JRE 전환"},
    ]),
    (r"^openjdk:(\d+)-slim$", [
        {"image": "eclipse-temurin:{v}-jre-alpine",       "min": 100, "max": 250, "note": None},
    ]),

    # ── Eclipse Temurin ─────────────────────────────────────────────────────
    (r"^eclipse-temurin:(\d+)$", [
        {"image": "eclipse-temurin:{v}-jre",              "min": 150, "max": 300, "note": "기본값이 JDK — JRE로 전환"},
    ]),
    (r"^eclipse-temurin:(\d+)-jdk$", [
        {"image": "eclipse-temurin:{v}-jre",              "min": 150, "max": 300, "note": "JDK→JRE 전환"},
        {"image": "gcr.io/distroless/java{v}-debian12",   "min": 300, "max": 500, "note": "쉣 없음"},
    ]),
    (r"^eclipse-temurin:(\d+)-jdk-alpine$", [
        {"image": "eclipse-temurin:{v}-jre-alpine",       "min": 100, "max": 250, "note": "JDK→JRE 전환"},
    ]),

    # ── Go ──────────────────────────────────────────────────────────────────
    (r"^golang:(\d+\.\d+(?:\.\d+)?)$", [
        {"image": "scratch (multi-stage 후)",                          "min": 600, "max": 950, "note": "Go 바이너리 정적 링크 가능"},
        {"image": "gcr.io/distroless/static-debian12 (multi-stage 후)", "min": 580, "max": 920, "note": "CA 인증서 포함"},
        {"image": "alpine:3.19 (multi-stage 후)",                      "min": 540, "max": 880, "note": "쉘 필요시"},
    ]),
    (r"^golang:(\d+\.\d+(?:\.\d+)?)-alpine$", [
        {"image": "scratch (multi-stage 후)",             "min": 400, "max": 750, "note": "Go 바이너리 정적 링크 가능"},
        {"image": "alpine:3.19 (multi-stage 후)",         "min": 350, "max": 700, "note": None},
    ]),
    (r"^golang:latest$", [
        {"image": "scratch (multi-stage 후)",             "min": 600, "max": 950, "note": "latest 태그 고정 권장"},
    ]),

    # ── Rust ────────────────────────────────────────────────────────────────
    (r"^rust:(\d+\.\d+(?:\.\d+)?)$", [
        {"image": "scratch (multi-stage 후)",                  "min": 700, "max": 1100, "note": "Rust 바이너리 정적 링크 가능"},
        {"image": "debian:bookworm-slim (multi-stage 후)",     "min": 600, "max": 1000, "note": None},
        {"image": "gcr.io/distroless/cc-debian12 (multi-stage 후)", "min": 650, "max": 1050, "note": "C 런타임만 포함"},
    ]),
    (r"^rust:(\d+\.\d+(?:\.\d+)?)-slim$", [
        {"image": "scratch (multi-stage 후)",                  "min": 500, "max": 900, "note": "Rust 바이너리 정적 링크 가능"},
    ]),
    (r"^rust:latest$", [
        {"image": "scratch (multi-stage 후)",                  "min": 700, "max": 1100, "note": "latest 태그 고정 권장"},
    ]),

    # ── Ubuntu ──────────────────────────────────────────────────────────────
    (r"^ubuntu:(\d+\.\d+)$", [
        {"image": "ubuntu:{v}-minimal",     "min": 30,  "max": 60,  "note": None},
        {"image": "debian:bookworm-slim",   "min": 20,  "max": 80,  "note": None},
        {"image": "alpine:3.19",            "min": 150, "max": 280, "note": "패키지 호환성 주의"},
    ]),
    (r"^ubuntu:latest$", [
        {"image": "ubuntu:22.04",           "min": 0,   "max": 0,   "note": "latest 태그 → 버전 고정 권장"},
        {"image": "debian:bookworm-slim",   "min": 20,  "max": 80,  "note": None},
    ]),
    (r"^ubuntu:jammy$", [
        {"image": "ubuntu:22.04-minimal",   "min": 30,  "max": 60,  "note": None},
    ]),
    (r"^ubuntu:focal$", [
        {"image": "ubuntu:20.04-minimal",   "min": 30,  "max": 60,  "note": None},
    ]),
    (r"^ubuntu:noble$", [
        {"image": "ubuntu:24.04-minimal",   "min": 30,  "max": 60,  "note": None},
    ]),

    # ── Debian ──────────────────────────────────────────────────────────────
    (r"^debian:(bullseye|bookworm|buster|stretch|trixie)$", [
        {"image": "debian:{v}-slim",        "min": 50,  "max": 120, "note": None},
        {"image": "alpine:3.19",            "min": 150, "max": 280, "note": "패키지 호환성 주의"},
    ]),
    (r"^debian:latest$", [
        {"image": "debian:bookworm-slim",   "min": 50,  "max": 120, "note": "latest 태그 → 버전 고정 권장"},
    ]),

    # ── Nginx ───────────────────────────────────────────────────────────────
    (r"^nginx:(\d+\.\d+(?:\.\d+)?)$", [
        {"image": "nginx:{v}-alpine",          "min": 90,  "max": 180, "note": None},
        {"image": "nginx:{v}-alpine-slim",     "min": 100, "max": 200, "note": "최소 모듈만 포함"},
    ]),
    (r"^nginx:latest$", [
        {"image": "nginx:alpine",              "min": 90,  "max": 180, "note": "latest 태그 → 버전 고정 권장"},
    ]),
    (r"^nginx:stable$", [
        {"image": "nginx:stable-alpine",       "min": 90,  "max": 180, "note": None},
    ]),
    (r"^nginx:mainline$", [
        {"image": "nginx:mainline-alpine",     "min": 90,  "max": 180, "note": None},
    ]),

    # ── Redis ───────────────────────────────────────────────────────────────
    (r"^redis:(\d+(?:\.\d+)*)$", [
        {"image": "redis:{v}-alpine",          "min": 50,  "max": 100, "note": None},
    ]),
    (r"^redis:latest$", [
        {"image": "redis:alpine",              "min": 50,  "max": 100, "note": "latest 태그 → 버전 고정 권장"},
    ]),

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    (r"^postgres:(\d+(?:\.\d+)*)$", [
        {"image": "postgres:{v}-alpine",       "min": 80,  "max": 150, "note": None},
    ]),
    (r"^postgres:latest$", [
        {"image": "postgres:alpine",           "min": 80,  "max": 150, "note": "latest 태그 → 버전 고정 권장"},
    ]),

    # ── MySQL ───────────────────────────────────────────────────────────────
    (r"^mysql:(\d+\.\d+)$", [
        {"image": "mysql:{v}-debian",          "min": 20,  "max": 60,  "note": None},
    ]),

    # ── MariaDB ─────────────────────────────────────────────────────────────
    (r"^mariadb:(\d+\.\d+)$", [
        {"image": "mariadb:{v}-focal",         "min": 10,  "max": 40,  "note": None},
    ]),

    # ── PHP ─────────────────────────────────────────────────────────────────
    (r"^php:(\d+\.\d+)$", [
        {"image": "php:{v}-alpine",            "min": 150, "max": 280, "note": "musl libc 주의"},
        {"image": "php:{v}-slim",              "min": 80,  "max": 180, "note": None},
    ]),
    (r"^php:(\d+\.\d+)-fpm$", [
        {"image": "php:{v}-fpm-alpine",        "min": 150, "max": 280, "note": "musl libc 주의"},
    ]),
    (r"^php:(\d+\.\d+)-apache$", [
        {"image": "php:{v}-fpm-alpine + nginx:alpine", "min": 100, "max": 250,
         "note": "Apache → Nginx+FPM 구조 전환 권장"},
    ]),

    # ── Ruby ────────────────────────────────────────────────────────────────
    (r"^ruby:(\d+\.\d+(?:\.\d+)?)$", [
        {"image": "ruby:{v}-slim",             "min": 200, "max": 380, "note": None},
        {"image": "ruby:{v}-alpine",           "min": 280, "max": 450, "note": "native gem 빌드 주의"},
    ]),
    (r"^ruby:(\d+\.\d+(?:\.\d+)?)-slim$", [
        {"image": "ruby:{v}-alpine",           "min": 50,  "max": 150, "note": "native gem 빌드 주의"},
    ]),

    # ── .NET ────────────────────────────────────────────────────────────────
    (r"^mcr\.microsoft\.com/dotnet/sdk:(\d+\.\d+)$", [
        {"image": "mcr.microsoft.com/dotnet/runtime:{v}",      "min": 350, "max": 500,
         "note": "SDK→Runtime 전환, multi-stage 권장"},
        {"image": "mcr.microsoft.com/dotnet/aspnet:{v}",       "min": 250, "max": 420,
         "note": "ASP.NET 앱용"},
        {"image": "mcr.microsoft.com/dotnet/runtime-deps:{v}", "min": 400, "max": 550,
         "note": "self-contained 앱용"},
    ]),
    (r"^mcr\.microsoft\.com/dotnet/aspnet:(\d+\.\d+)$", [
        {"image": "mcr.microsoft.com/dotnet/runtime:{v}",      "min": 50,  "max": 150,
         "note": "ASP.NET 불필요시"},
    ]),

    # ── Kafka (Confluent) ────────────────────────────────────────────────────
    (r"^confluentinc/cp-kafka:(\S+)$", [
        {"image": "bitnami/kafka:{v}",         "min": 50,  "max": 200,
         "note": "Bitnami non-root 기반, 보안 강화"},
    ]),

    # ── CentOS (EOL) ─────────────────────────────────────────────────────────
    (r"^centos:(\d+)$", [
        {"image": "almalinux:{v}",             "min": 0,   "max": 0,
         "note": "CentOS EOL → AlmaLinux / RockyLinux 마이그레이션 권장"},
        {"image": "rockylinux:{v}",            "min": 0,   "max": 0,   "note": None},
    ]),
    (r"^centos:latest$", [
        {"image": "almalinux:9",               "min": 0,   "max": 0,
         "note": "CentOS EOL → AlmaLinux 마이그레이션 권장"},
    ]),

    # ── Amazon Linux ─────────────────────────────────────────────────────────
    (r"^amazonlinux:2$", [
        {"image": "amazonlinux:2023",          "min": 0,   "max": 50,
         "note": "AL2 EOL 2025-06-30 예정, AL2023 마이그레이션 권장"},
    ]),
]

# 이미 최적화된 이미지 — 매칭 skip
_ALREADY_OPTIMAL = re.compile(
    r"^("
    r"scratch"
    r"|gcr\.io/distroless/"
    r"|.*-slim"
    r"|.*-alpine"
    r"|.*-minimal"
    r"|alpine:"
    r"|busybox:"
    r"|\[stage:.*\]"
    r")",
    re.IGNORECASE,
)


def check(ir: DockerfileIR) -> list[Finding]:
    final = ir.final_stage
    if final is None:
        return []

    image = final.base_image

    if _ALREADY_OPTIMAL.search(image):
        return []

    for pattern, recs in _RULES:
        m = re.match(pattern, image, re.IGNORECASE)
        if not m:
            continue

        version = m.group(1) if m.lastindex else ""
        best = max(recs, key=lambda r: r["max"])
        best_image = best["image"].replace("{v}", version)
        note_str = f" ({best['note']})" if best.get("note") else ""

        alternatives = [r["image"].replace("{v}", version) for r in recs[1:]]
        alt_str = ""
        if alternatives:
            alt_str = "\n  다른 후보: " + ", ".join(alternatives)

        recommendation = f"→ {best_image}{note_str}{alt_str}"

        # Patch: 해당 FROM 라인을 교체 (단순 이미지명일 때만)
        patch = None
        from_line_no = _find_final_from_line(ir)
        if from_line_no and "(" not in best_image and "[" not in best_image:
            old = ir.raw_lines[from_line_no - 1]
            new = old.replace(image, best_image, 1)
            patch = Patch(line_no=from_line_no, old_text=old, new_text=new)

        return [Finding(
            rule_id="BASE_IMAGE_NOT_OPTIMIZED",
            severity=Severity.HIGH,
            line_no=from_line_no,
            description=f"베이스 이미지 최적화 필요: `{image}`",
            recommendation=recommendation,
            saving_min_mb=best["min"],
            saving_max_mb=best["max"],
            patch=patch,
        )]

    return []


def _find_final_from_line(ir: DockerfileIR) -> Optional[int]:
    """final stage FROM 명령의 1-based 줄 번호 반환."""
    target = len(ir.stages)
    count = 0
    for i, line in enumerate(ir.raw_lines):
        if re.match(r"^\s*FROM\s+", line, re.IGNORECASE):
            count += 1
            if count == target:
                return i + 1
    return None
