# imgadvisor

Dockerfile 사전 정적 분석 및 이미지 최적화 도구입니다.

`imgadvisor`는 Docker 이미지를 실제로 빌드하기 전에 Dockerfile을 읽고, 이미지가 왜 커질지, 어떤 부분이 위험한지, 어떤 식으로 줄일 수 있는지를 분석합니다. 현재 구현은 특히 Python Dockerfile 최적화에 가장 깊게 맞춰져 있으며, 단순한 예시 템플릿이 아니라 실제 multi-stage Dockerfile 본문을 생성할 수 있습니다.

## 현재 저장소 구조

이 저장소의 Git 루트는 `0206pdh/dockimage_scanner` 최상단입니다.  
현재 `imgadvisor` 패키지와 문서는 그 아래 `dockfile_scanner/` 경로에 있습니다.

즉 이 문서는 다음 경로에 해당합니다.

- `dockfile_scanner/README.md`

설치나 개발 작업을 할 때도 이 점을 기준으로 보는 것이 맞습니다.

## 설치

현재 구조상 GitHub tarball만 바로 설치하면 상위 루트의 다른 패키지 설정을 타게 될 수 있습니다. 그래서 현재는 `subdirectory`를 명시하는 설치가 가장 정확합니다.

```bash
python -m pip install --no-cache-dir --force-reinstall \
  "git+https://github.com/0206pdh/dockimage_scanner.git@main#subdirectory=dockfile_scanner"
```

특정 버전 태그를 설치하려면:

```bash
python -m pip install --no-cache-dir --force-reinstall \
  "git+https://github.com/0206pdh/dockimage_scanner.git@v0.3.0#subdirectory=dockfile_scanner"
```

요구 사항:

- Python 3.11 이상
- `layers`, `validate` 명령을 쓸 경우 Docker daemon
- `scan` 명령을 쓸 경우 Trivy

## 명령어

| 명령어 | Docker 필요 | 설명 |
|---|---|---|
| `analyze` | 아니오 | Dockerfile 문제를 정적 분석 |
| `recommend` | 아니오 | 최적화된 Dockerfile 생성 |
| `layers` | 예 | 실제 이미지 빌드 후 레이어 크기 분석 |
| `validate` | 예 | 원본/최적화 Dockerfile 실제 빌드 비교 |
| `scan` | 아니오 | Trivy pre-build 설정/취약점 검사 |

## Python 중심 최적화

현재 구현은 의도적으로 Python 쪽을 가장 깊게 다룹니다.

Python Dockerfile에 대해 현재 가능한 것:

- single-stage Python 이미지를 multi-stage로 전환 판단
- 실제 instruction 흐름을 기반으로 builder/runtime stage 재구성
- `/opt/venv` 기반 의존성 분리
- runtime stage를 보수적으로 `python:*‑slim`으로 축소
- `apt`/`pip` 명령 정규화
- `requirements*.txt`, `constraints*.txt`, `pyproject.toml`, `poetry.lock` 기반 manifest-first 전략
- Python runtime 기본 `ENV` 보강
- 일부 엔트리포인트 자동 보정

현재 반영되는 Python runtime 기본값:

- `PYTHONUNBUFFERED=1`
- `PYTHONDONTWRITEBYTECODE=1`
- `PIP_NO_CACHE_DIR=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`

현재 반영되는 Python runtime command 보정:

- `flask run` 감지 시, 안전하게 추론 가능하면 `gunicorn`으로 전환
- `uvicorn`에 `--workers`가 없으면 `--workers 2` 추가

## 기본 사용 흐름

```bash
imgadvisor analyze -f Dockerfile
imgadvisor recommend -f Dockerfile -o optimized.Dockerfile
imgadvisor validate -f Dockerfile --optimized optimized.Dockerfile
```

레이어 단위 근거를 먼저 보고 싶다면:

```bash
imgadvisor layers -f Dockerfile
```

빌드 전 보안/설정 검사까지 하고 싶다면:

```bash
imgadvisor scan -f Dockerfile
```

## 사용 예시

정적 분석:

```bash
imgadvisor analyze -f Dockerfile
```

최적화 Dockerfile 생성:

```bash
imgadvisor recommend -f Dockerfile -o optimized.Dockerfile
```

실제 크기 감소 검증:

```bash
imgadvisor validate -f Dockerfile --optimized optimized.Dockerfile
```

Trivy pre-build 검사:

```bash
imgadvisor scan -f Dockerfile --severity HIGH,CRITICAL
```

## 주요 rule

### Base image

과하게 무거운 base image를 감지하고, 더 작은 대안을 추천합니다.  
다만 현재 Python multi-stage 생성 경로에서는 Alpine 같은 공격적 전환보다 `slim` 계열을 더 보수적으로 사용합니다.

### Build tools in final stage

final stage에 남아 있는 컴파일러, 개발 헤더, 빌드 도구를 감지합니다.

### Cache cleanup

패키지 매니저 설치 후 캐시를 남기는 패턴을 감지합니다.

예:

- `apt-get install` 후 apt lists 미정리
- `pip install` 에 `--no-cache-dir` 누락

### Python runtime defaults

Python 컨테이너에서 자주 빠지는 기본 `ENV`와 개발용 엔트리포인트 패턴을 감지합니다.

### Broad copy scope

`.dockerignore` 없이 `COPY . .` 같은 패턴이 있는지 검사합니다.

### Single-stage Python build

Python Dockerfile을 실제 multi-stage로 바꾸는 것이 유의미한지 판정하고, 조건이 맞으면 구체적인 builder/runtime Dockerfile 본문을 생성합니다.

## Python에서 `recommend`가 하는 일

Python final stage에 최적화 신호가 있으면, `recommend`는 다음과 비슷한 결과를 만들 수 있습니다.

```dockerfile
# -- builder stage --
FROM python:3.11 AS builder
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv $VIRTUAL_ENV
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# -- runtime stage --
FROM python:3.11-slim
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

중요한 점은, 이 결과가 고정 예시를 붙이는 방식이 아니라는 점입니다.  
파싱된 Dockerfile instruction을 읽고, 가능한 범위에서 원래 순서를 보존하면서 builder/runtime를 다시 조립합니다.

## Trivy pre-build 검사

`scan`은 두 가지를 함께 수행합니다.

- `trivy config`: Dockerfile 설정 문제 검사
- `trivy fs`: build context의 dependency 취약점 검사

예:

```bash
imgadvisor scan -f Dockerfile --ignore-unfixed
```

## 프로젝트 구조

```text
dockfile_scanner/
├── README.md
├── comparison.md
├── pyproject.toml
├── imgadvisor/
│   ├── main.py
│   ├── parser.py
│   ├── analyzer.py
│   ├── recommender.py
│   ├── validator.py
│   ├── layer_analyzer.py
│   ├── trivy_scanner.py
│   ├── display.py
│   ├── models.py
│   └── rules/
│       ├── base_image.py
│       ├── build_tools.py
│       ├── cache_cleanup.py
│       ├── copy_scope.py
│       ├── multi_stage.py
│       └── python_runtime.py
└── test/
    ├── Dockerfile.bloated
    └── app.py
```

## 현재 범위

가장 깊은 재작성 로직은 의도적으로 Python에 집중되어 있습니다.  
다른 언어도 일부 범용 rule로 분석은 되지만, 실제 Dockerfile 본문을 재구성하는 multi-stage 최적화 경로는 현재 Python 중심입니다.
