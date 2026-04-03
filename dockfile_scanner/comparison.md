# Python 이미지 최적화 비교

이 문서는 의도적으로 비대하게 만든 Python Dockerfile과 `imgadvisor`가 생성한 최적화 Dockerfile을 비교합니다.

## 원본 Dockerfile

```dockerfile
FROM python:3.11

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    wget \
    curl \
    git \
    vim

WORKDIR /app

COPY . .

RUN pip install flask sqlalchemy psycopg2-binary \
    requests numpy pandas scikit-learn \
    celery redis gunicorn

RUN wget https://github.com/jwilder/dockerize/releases/download/v0.6.1/dockerize-linux-amd64-v0.6.1.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-v0.6.1.tar.gz \
    && rm dockerize-linux-amd64-v0.6.1.tar.gz

RUN rm -rf /var/lib/apt/lists/*

ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000
CMD flask run --host=0.0.0.0 --port=5000
```

## 최적화 Dockerfile

```dockerfile
# -- builder stage --
FROM python:3.11 AS builder
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv $VIRTUAL_ENV
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ make cmake build-essential libpq-dev libssl-dev libffi-dev wget curl git vim \
    && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --no-cache-dir flask sqlalchemy psycopg2-binary requests numpy pandas scikit-learn celery redis gunicorn
RUN wget https://github.com/jwilder/dockerize/releases/download/v0.6.1/dockerize-linux-amd64-v0.6.1.tar.gz && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-v0.6.1.tar.gz && rm dockerize-linux-amd64-v0.6.1.tar.gz
RUN rm -rf /var/lib/apt/lists/*

# -- runtime stage --
FROM python:3.11-slim
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app
EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

## 무엇이 달라졌는가

### 1. 단일 스테이지를 multi-stage로 분리

원본은 빌드 도구 설치, Python 의존성 설치, 런타임 구성까지 모두 한 이미지에서 처리합니다.

최적화본은 다음처럼 역할을 분리합니다.

- `builder`: 빌드 도구 설치와 의존성 구성
- `runtime`: 실행에 필요한 결과물만 복사

이 변화로 런타임 이미지에 컴파일러와 개발 패키지가 남지 않습니다.

### 2. 런타임 base image 축소

- 원본: `python:3.11`
- 최적화본: `python:3.11-slim`

runtime 시작점 자체를 더 작게 가져가면서 Alpine 전환보다 호환성 리스크를 줄입니다.

### 3. Python 의존성을 가상환경으로 분리

최적화본은 `/opt/venv`에 전용 가상환경을 만들고, 런타임에는 그 결과만 복사합니다.

이렇게 하면 builder의 전체 Python 환경을 통째로 가져오지 않아도 됩니다.

### 4. `apt` 설치 명령 정리

원본:

```dockerfile
RUN apt-get update && apt-get install -y ...
```

최적화본:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends ... \
    && rm -rf /var/lib/apt/lists/*
```

효과:

- 불필요한 추천 패키지 감소
- apt index cache 제거

### 5. `pip install` 정리

원본은 캐시를 남길 수 있는 일반 `pip install`을 사용합니다.

최적화본은:

- `pip install --no-cache-dir ...`
- `PIP_NO_CACHE_DIR=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`

를 함께 적용해 불필요한 캐시와 추가 동작을 줄입니다.

### 6. Python 런타임 `ENV` 보강

추가되거나 보강되는 항목:

- `PYTHONUNBUFFERED=1`
- `PYTHONDONTWRITEBYTECODE=1`
- `PIP_NO_CACHE_DIR=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`

효과:

- 로그가 버퍼링 없이 바로 출력됨
- `.pyc` 생성 감소
- pip 캐시 감소

### 7. 개발 서버를 런타임 서버로 교체

원본:

```dockerfile
CMD flask run --host=0.0.0.0 --port=5000
```

최적화본:

```dockerfile
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

`flask run`은 개발용 서버이므로, 실제 컨테이너 런타임에서는 `gunicorn` 같은 WSGI 서버가 더 적절합니다.

## 기대 효과

최적화 후 일반적으로 기대할 수 있는 변화는 다음과 같습니다.

- 런타임 이미지 크기 감소
- 컴파일러와 개발용 라이브러리 제거
- 패키지 관리자 캐시 감소
- 더 적절한 Python 런타임 기본값 적용
- 운영용 서버 사용으로 실행 방식 개선

## 검증 방법

```bash
imgadvisor recommend -f Dockerfile -o optimized.Dockerfile
imgadvisor validate -f Dockerfile --optimized optimized.Dockerfile
```

직접 빌드와 push까지 비교하려면:

```bash
docker build -f Dockerfile -t 0206pdh/imgadvisor-test:original .
docker build -f optimized.Dockerfile -t 0206pdh/imgadvisor-test:optimized .

docker push 0206pdh/imgadvisor-test:original
docker push 0206pdh/imgadvisor-test:optimized
```

## 참고

이 문서는 최상단 저장소 루트가 아니라 `dockfile_scanner/` 하위 프로젝트 기준 문서입니다.
