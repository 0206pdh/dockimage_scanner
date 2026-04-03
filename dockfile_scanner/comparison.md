# Python 테스트 Dockerfile 비교

이 문서는 `test/` 아래에서 실제로 최적화한 세 개의 Python Dockerfile을 기준으로, 원본과 최적화 결과를 비교 정리한 문서입니다.

대상 파일:

- `test/Dockerfile.pre1` / `test/Dockerfile.pre1.optimized`
- `test/Dockerfile.pre2` / `test/Dockerfile.pre2.optimized`
- `test/Dockerfile.pre3` / `test/Dockerfile.pre3.optimized`

## 비교 요약

| 케이스 | 앱 성격 | 원본 엔트리포인트 | 최적화 후 엔트리포인트 | 핵심 변화 |
|---|---|---|---|---|
| `pre1` | Flask + `pip install` inline | `flask run` | `gunicorn -b 0.0.0.0:5000 app:app` | multi-stage, slim runtime, apt/pip 정리, 개발 서버 제거 |
| `pre2` | FastAPI + Uvicorn | `uvicorn main:app` | 유지 | multi-stage, slim runtime, apt/pip 정리, worker 자동 고정은 하지 않음 |
| `pre3` | Flask + `requirements.txt` | `flask run` | 유지 | manifest-first install, multi-stage, slim runtime, apt/pip 정리 |

## 공통적으로 적용된 최적화

세 케이스 모두 아래 원칙이 공통으로 반영됩니다.

- 단일 스테이지에서 builder / runtime multi-stage 구조로 분리
- runtime 이미지를 `python:3.11-slim` 계열로 축소
- `/opt/venv` 가상환경을 만들어 런타임 의존성만 복사
- `apt-get install`에 `--no-install-recommends` 추가
- 같은 `RUN`에서 `rm -rf /var/lib/apt/lists/*` 수행
- `pip install`에 `--no-cache-dir` 적용
- Python 컨테이너 기본 `ENV` 보강
  - `PYTHONUNBUFFERED=1`
  - `PYTHONDONTWRITEBYTECODE=1`
  - `PIP_NO_CACHE_DIR=1`
  - `PIP_DISABLE_PIP_VERSION_CHECK=1`

## 케이스 1: Flask 개발 서버를 Gunicorn으로 교체

대상:

- 원본: `test/Dockerfile.pre1`
- 결과: `test/Dockerfile.pre1.optimized`

원본 특징:

- `python:3.11` 단일 스테이지
- `gcc`, `g++`, `build-essential`이 최종 이미지에 남음
- `COPY . .`
- `pip install flask gunicorn requests pandas`
- 엔트리포인트가 `flask run`

최적화 결과 핵심:

- builder stage에서 빌드 도구와 의존성 설치
- runtime stage에서는 `/opt/venv`와 `/app`만 복사
- `python:3.11-slim` 사용
- Flask 앱 소스를 실제로 읽어 `app.py` 안의 `app = Flask(__name__)`를 확인한 뒤, 엔트리포인트를 `gunicorn`으로 교체

최적화 결과의 핵심 부분:

```dockerfile
# -- runtime stage --
FROM python:3.11-slim
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
```

포인트:

- `-w 2` 같은 고정 worker 값은 넣지 않음
- `gunicorn`이 실제 설치되는 경우에만 자동 교체

## 케이스 2: FastAPI / Uvicorn은 유지하고 런타임만 경량화

대상:

- 원본: `test/Dockerfile.pre2`
- 결과: `test/Dockerfile.pre2.optimized`

원본 특징:

- `fastapi`, `uvicorn`, `sqlalchemy` inline 설치
- `uvicorn` 실행
- 빌드 도구와 캐시 정리가 부족

최적화 결과 핵심:

- builder / runtime 분리
- `python:3.11-slim` runtime 사용
- `pip install --no-cache-dir`
- `apt` cache 정리
- `uvicorn` 엔트리포인트는 유지

최적화 결과의 핵심 부분:

```dockerfile
# -- runtime stage --
FROM python:3.11-slim
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

포인트:

- `uvicorn`에 worker 수를 자동으로 넣지 않음
- `PYTHON_ASGI_WORKERS_NOT_SET` 경고는 주되, CPU/메모리/배포 환경을 모르는 상태에서 자동 고정하지 않음

## 케이스 3: requirements 기반 Flask 앱

대상:

- 원본: `test/Dockerfile.pre3`
- 결과: `test/Dockerfile.pre3.optimized`

원본 특징:

- `requirements.txt`를 먼저 복사하고 `pip install -r requirements.txt`
- 그 뒤 `COPY . .`
- 엔트리포인트는 `flask run`

최적화 결과 핵심:

- `requirements.txt`를 먼저 복사하는 manifest-first 전략 유지
- builder에서 `pip install --no-cache-dir -r requirements.txt`
- runtime을 slim으로 축소
- Flask 엔트리포인트는 그대로 유지

최적화 결과의 핵심 부분:

```dockerfile
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# -- runtime stage --
FROM python:3.11-slim
...
CMD flask run --host=0.0.0.0 --port=5000
```

왜 `gunicorn`으로 안 바뀌는가:

- 이 케이스는 실제 최적화 결과 기준으로 엔트리포인트가 유지됨
- 현재 자동 치환은 앱 소스 추론과 의존성 확인이 모두 맞을 때만 동작
- 따라서 `pre3`는 “엔트리포인트 자동 치환보다 Dockerfile 구조 최적화가 우선 적용된 예시”로 보는 것이 맞음

## 케이스별 차이

### `pre1`

- inline `pip install`
- Flask 개발 서버를 운영형 `gunicorn`으로 교체
- broad COPY 포함

### `pre2`

- FastAPI / Uvicorn 케이스
- 엔트리포인트는 유지
- worker 수는 경고만 하고 자동 수정하지 않음

### `pre3`

- `requirements.txt` 기반 설치
- dependency layer 캐시 전략이 반영됨
- Flask지만 엔트리포인트는 유지된 실제 결과를 기록

## 테스트 방법

예시:

```bash
imgadvisor analyze -f test/Dockerfile.pre1
imgadvisor recommend -f test/Dockerfile.pre1 -o test/Dockerfile.pre1.optimized
imgadvisor validate -f test/Dockerfile.pre1 --optimized test/Dockerfile.pre1.optimized
```

직접 빌드 비교:

```bash
docker build -f test/Dockerfile.pre1 -t pre1-original test
docker build -f test/Dockerfile.pre1.optimized -t pre1-optimized test
```

다른 케이스도 `pre2`, `pre3`로 같은 방식으로 실행하면 됩니다.

## 정리

현재 `imgadvisor`의 Python 최적화는 다음 방향으로 정리됩니다.

- 구조 최적화: 자동
- 캐시/기본 ENV 정리: 자동
- base image 축소: 자동
- 엔트리포인트 변경: 보수적 자동화

즉, 이미지 크기와 런타임 구성 최적화는 적극적으로 수행하되, worker 수나 서버 설정처럼 운영 환경 의존성이 큰 값은 자동으로 고정하지 않는 방향입니다.
