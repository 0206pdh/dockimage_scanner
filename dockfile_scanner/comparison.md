# Python 이미지 최적화 비교

이 문서는 비대하게 작성된 원본 Python Dockerfile과, `imgadvisor`가 생성한 최적화된 multi-stage Dockerfile을 비교합니다.

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

## 최적화된 Dockerfile

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

### 1. single-stage에서 multi-stage로 분리

이전:

- 빌드 도구 설치
- Python 의존성 설치
- 실행 환경 구성

이 모든 작업이 하나의 최종 이미지 안에서 처리되었습니다.

이후:

- 무거운 설치/빌드 작업은 `builder` stage에 남김
- 최종 `runtime` stage에는 실행에 필요한 결과만 복사

의미:

- 컴파일러와 개발 패키지가 운영 이미지에 남지 않음
- 최종 이미지 크기 감소
- 공격 표면 축소

### 2. runtime base image 축소

이전:

- `python:3.11`

이후:

- `python:3.11-slim`

의미:

- runtime stage 시작점 자체가 더 가벼워짐
- Alpine처럼 공격적인 전환보다 호환성이 더 안전함

### 3. Python 의존성을 venv로 분리

이전:

- Python 패키지가 기본 Python 환경에 직접 설치됨

이후:

- `/opt/venv`에 가상환경 생성
- runtime stage에는 `/opt/venv`만 복사

의미:

- builder 전체 Python 환경을 복사하지 않아도 됨
- runtime에 필요한 dependency 경계가 더 명확해짐

### 4. apt install 정규화

이전:

- `apt-get install -y ...`

이후:

- `apt-get install -y --no-install-recommends ...`
- 같은 layer에서 `rm -rf /var/lib/apt/lists/*`

의미:

- 권장 패키지까지 불필요하게 깔리는 것을 줄임
- apt index cache가 layer에 남는 것을 줄임

### 5. pip install 정규화

이전:

- `pip install ...`

이후:

- `pip install --no-cache-dir ...`
- `PIP_NO_CACHE_DIR=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`

의미:

- pip cache로 인한 layer 증가를 막음
- 불필요한 버전 체크 동작을 줄임

### 6. Python runtime 기본 ENV 추가

추가된 항목:

- `PYTHONUNBUFFERED=1`
- `PIP_NO_CACHE_DIR=1`
- `PIP_DISABLE_PIP_VERSION_CHECK=1`

원래 있던 값 중 유지된 항목:

- `PYTHONDONTWRITEBYTECODE=1`

의미:

- 컨테이너 로그가 바로 flush됨
- 불필요한 `.pyc` 생성과 pip cache 동작을 줄임

### 7. 개발 서버에서 운영 서버로 엔트리포인트 교체

이전:

```dockerfile
CMD flask run --host=0.0.0.0 --port=5000
```

이후:

```dockerfile
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

의미:

- `flask run`은 개발 서버이므로 운영 환경에 부적절함
- `gunicorn`은 WSGI 운영 서버로 더 적합함
- worker 수를 명시해서 실행 특성이 더 예측 가능해짐

## 기대 효과

원본 Dockerfile과 비교했을 때, 최적화 결과는 일반적으로 다음을 기대할 수 있습니다.

- runtime 이미지 크기 감소
- 컴파일러/개발 헤더 제거
- 패키지 매니저 캐시 감소
- Flask 개발 서버 대신 운영 서버 사용
- push/pull/deploy 비용 감소

## 검증 방법

```bash
imgadvisor recommend -f Dockerfile -o optimized.Dockerfile
imgadvisor validate -f Dockerfile --optimized optimized.Dockerfile
```

직접 build/push를 비교하고 싶다면:

```bash
docker build -f Dockerfile -t 0206pdh/imgadvisor-test:original .
docker build -f optimized.Dockerfile -t 0206pdh/imgadvisor-test:optimized .

docker push 0206pdh/imgadvisor-test:original
docker push 0206pdh/imgadvisor-test:optimized
```

## 참고

이 비교 문서는 현재 저장소 루트가 아니라 `dockfile_scanner/` 하위 프로젝트 기준 문서입니다.  
즉 실제 경로는 다음과 같습니다.

- `dockfile_scanner/comparison.md`
