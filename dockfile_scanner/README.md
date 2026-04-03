# imgadvisor

`imgadvisor`는 Dockerfile을 빌드 전에 정적으로 분석해서 이미지 비대 원인과 최적화 방향을 보여주는 CLI입니다.

현재 프로젝트는 범위를 의도적으로 좁혀서 Python Dockerfile 최적화에 가장 깊게 집중하고 있습니다. 단순히 예시 템플릿을 붙이는 수준이 아니라, Python 단일 스테이지 Dockerfile을 읽고 실제 multi-stage Dockerfile 본문을 생성하는 흐름까지 포함합니다.

## 저장소 구조

최상단 Git 저장소는 `0206pdh/dockimage_scanner` 이고, 실제 `imgadvisor` 패키지와 문서는 그 아래 `dockfile_scanner/` 하위 프로젝트에 있습니다.

즉 이 문서가 가리키는 실제 프로젝트 루트는 다음 경로입니다.

- `dockfile_scanner/`

## 설치

### 가장 쉬운 방법

최신 release를 기준으로 전용 가상환경 `~/.imgadvisor`에 설치하려면 아래 명령을 사용합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/0206pdh/dockimage_scanner/main/dockfile_scanner/install.sh | bash
```

이 스크립트는 다음을 처리합니다.

- Python 3.11 이상 탐색
- 최신 GitHub release 태그 조회
- `dockfile_scanner` 하위 프로젝트만 설치
- `~/.local/bin/imgadvisor` 실행 링크 생성

### 수동 설치

하위 프로젝트를 정확히 지정해서 직접 설치하려면 아래처럼 `subdirectory`를 포함해야 합니다.

```bash
python -m pip install --no-cache-dir --force-reinstall \
  "git+https://github.com/0206pdh/dockimage_scanner.git@main#subdirectory=dockfile_scanner"
```

특정 릴리스를 설치하려면:

```bash
python -m pip install --no-cache-dir --force-reinstall \
  "git+https://github.com/0206pdh/dockimage_scanner.git@v0.3.10#subdirectory=dockfile_scanner"
```

필수 조건:

- Python 3.11 이상
- `validate`, `layers` 사용 시 Docker daemon
- `scan` 사용 시 Trivy

## 명령

| 명령 | Docker 필요 | 설명 |
|---|---|---|
| `analyze` | 아니오 | Dockerfile 규칙 분석 |
| `recommend` | 아니오 | 최적화 Dockerfile 생성 |
| `layers` | 예 | 실제 빌드 후 레이어 크기 분석 |
| `validate` | 예 | 원본과 최적화본을 실제로 빌드해 비교 |
| `scan` | 아니오 | Trivy 기반 pre-build 설정/취약점 검사 |

## 현재 최적화 범위

현재 구현은 Python 중심입니다.

- Python 단일 스테이지 Dockerfile을 multi-stage 전환 대상으로 판단
- 실제 instruction 흐름을 읽어서 builder/runtime 재구성
- `/opt/venv` 기반 의존성 분리
- runtime 이미지를 보수적으로 `python:*‑slim` 계열로 축소
- `apt` / `pip` 설치 명령 정규화
- `requirements*.txt`, `constraints*.txt`, `pyproject.toml`, `poetry.lock` 기반 manifest-first 복사 전략
- Python runtime 기본 `ENV` 보강
- `flask run`, `uvicorn` 같은 엔트리포인트 보정

자동으로 보강하는 Python 기본 `ENV`:

- `PYTHONUNBUFFERED=1`
- `PYTHONDONTWRITEBYTECODE=1`
- `PIP_NO_CACHE_DIR=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`

자동으로 보수적으로 보정하는 엔트리포인트:

- `flask run`은 가능할 때 `gunicorn`으로 교체
- `uvicorn`에 `--workers`가 없으면 경고만 표시하고 자동 고정은 하지 않음

실제 전후 비교와 성능/배포 테스트 방법은 아래 문서를 참고합니다.

- [comparison.md](./comparison.md)
- [benchmark.md](./benchmark.md)

## 빠른 사용 예시

```bash
imgadvisor analyze -f Dockerfile
imgadvisor recommend -f Dockerfile -o optimized.Dockerfile
imgadvisor validate -f Dockerfile --optimized optimized.Dockerfile
```

레이어별 크기를 먼저 보고 싶다면:

```bash
imgadvisor layers -f Dockerfile
```

Trivy pre-build 검사까지 하고 싶다면:

```bash
imgadvisor scan -f Dockerfile
```

## 주요 규칙

### `BASE_IMAGE_NOT_OPTIMIZED`

너무 무거운 base image를 감지하고 더 가벼운 대안을 제안합니다. Python multi-stage 생성 경로에서는 호환성을 위해 Alpine보다 `slim` 쪽을 더 보수적으로 사용합니다.

### `BUILD_TOOLS_IN_FINAL_STAGE`

최종 런타임 이미지에 남아 있는 컴파일러와 개발용 패키지를 감지합니다.

### `APT_CACHE_NOT_CLEANED`, `PIP_CACHE_NOT_DISABLED`

패키지 설치 후 캐시가 이미지 레이어에 남는 패턴을 감지합니다.

### `BROAD_COPY_SCOPE`

`.dockerignore` 없이 `COPY . .` 같은 과한 복사 범위를 감지합니다.

### `SINGLE_STAGE_BUILD`

Python 단일 스테이지 Dockerfile이 실제 multi-stage 전환 가치가 있는지 판단하고, 조건이 맞으면 builder/runtime 구조의 Dockerfile 본문을 생성합니다.

### `PYTHON_RUNTIME_ENVS_MISSING`, `PYTHON_RUNTIME_ENVS_CONFLICT`

Python 컨테이너에서 자주 누락되거나 충돌하는 런타임 환경 변수를 감지합니다.

### `PYTHON_DEV_SERVER_IN_RUNTIME`, `PYTHON_ASGI_WORKERS_NOT_SET`

개발 서버를 런타임에서 그대로 쓰는 패턴, ASGI worker 설정 누락을 감지합니다.

## Python에서 `recommend`가 생성하는 결과 예시

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
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

중요한 점은 이 결과가 단순 템플릿 붙이기가 아니라는 점입니다. 실제 Dockerfile instruction을 읽고, 가능한 범위에서 원래 의도를 유지하면서 builder/runtime를 다시 조립합니다.

주의:

- 현재 구현은 `uvicorn`에 worker 수를 자동으로 넣지 않습니다.
- 위 예시는 구조 설명용이며, 실제 생성 결과는 프로젝트 의존성과 엔트리포인트 추론 결과에 따라 달라집니다.

## Trivy pre-build 검사

`scan` 명령은 아래 두 검사를 묶어서 실행합니다.

- `trivy config`: Dockerfile 설정 문제 검사
- `trivy fs`: build context 의존성 취약점 검사

예시:

```bash
imgadvisor scan -f Dockerfile --ignore-unfixed
```

## 프로젝트 구조

```text
dockfile_scanner/
├─ README.md
├─ comparison.md
├─ install.sh
├─ pyproject.toml
├─ imgadvisor/
│  ├─ main.py
│  ├─ parser.py
│  ├─ analyzer.py
│  ├─ recommender.py
│  ├─ validator.py
│  ├─ layer_analyzer.py
│  ├─ trivy_scanner.py
│  ├─ display.py
│  ├─ models.py
│  └─ rules/
│     ├─ base_image.py
│     ├─ build_tools.py
│     ├─ cache_cleanup.py
│     ├─ copy_scope.py
│     ├─ multi_stage.py
│     └─ python_runtime.py
└─ test/
   ├─ Dockerfile.bloated
   └─ app.py
```

## 현재 범위 정리

이 프로젝트는 넓은 언어 지원보다 Python 최적화 깊이를 우선합니다. 다른 언어도 일부 범용 rule로 분석은 하지만, 실제 Dockerfile 본문을 재구성하는 multi-stage 생성 경로는 현재 Python 전용입니다.
