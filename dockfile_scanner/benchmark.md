# Python 이미지 최적화 성능/운영 테스트 가이드

이 문서는 `imgadvisor`로 생성한 최적화 Dockerfile이 실제로 어떤 이점을 주는지 검증하기 위한 실험 절차를 정리한 문서입니다.

핵심은 단순 HTTP 처리 성능만 보는 것이 아니라, 실제 운영에서 체감되는 아래 지표를 함께 비교하는 것입니다.

- 이미지 크기
- 빌드 시간
- Docker Hub push 시간
- Docker Hub pull 시간
- 컨테이너 시작 후 첫 응답 시간
- 런타임 부하테스트 결과

## 왜 이런 지표를 봐야 하는가

이미지 경량화의 1차 효과는 보통 CPU 처리량보다 아래 영역에서 먼저 드러납니다.

- CI 빌드 시간 단축
- 레지스트리 업로드/다운로드 시간 단축
- 배포 시 pull 시간 단축
- 컨테이너 cold start 시간 단축
- 런타임 메모리 사용량 감소

즉, `wrk`나 `hey` 같은 요청 부하테스트만으로는 이미지 경량화의 장점을 충분히 설명하기 어렵습니다.

## 테스트 대상

이 저장소에는 아래 세 개의 테스트 Dockerfile이 있습니다.

- `test/Dockerfile.pre1`
- `test/Dockerfile.pre2`
- `test/Dockerfile.pre3`

각 원본 Dockerfile의 최적화 결과도 함께 저장되어 있습니다.

- `test/Dockerfile.pre1.optimized`
- `test/Dockerfile.pre2.optimized`
- `test/Dockerfile.pre3.optimized`

## 공통 사전 준비

Docker Hub에 push 테스트까지 할 계획이면 먼저 로그인합니다.

```bash
docker login -u 0206pdh
```

`imgadvisor`가 설치되어 있어야 합니다. 최신 release 설치는 아래 문서를 따릅니다.

- `README.md`

## 1. 이미지 크기 비교

가장 기본이 되는 지표입니다.

```bash
docker build -f test/Dockerfile.pre1 -t pre1-original test
docker build -f test/Dockerfile.pre1.optimized -t pre1-optimized test

docker image inspect pre1-original --format '{{.Size}}'
docker image inspect pre1-optimized --format '{{.Size}}'
```

같은 방식으로 `pre2`, `pre3`도 비교합니다.

기록 추천 항목:

- 원본 이미지 크기
- 최적화 이미지 크기
- 절감량
- 절감률

## 2. 빌드 시간 비교

최초 cold build와, 캐시가 있는 상태의 재빌드를 분리해서 보는 것이 좋습니다.

### cold build

```bash
docker builder prune -af
/usr/bin/time -f "elapsed=%E" docker build --no-cache -f test/Dockerfile.pre1 -t pre1-original test
/usr/bin/time -f "elapsed=%E" docker build --no-cache -f test/Dockerfile.pre1.optimized -t pre1-optimized test
```

### warm build

```bash
/usr/bin/time -f "elapsed=%E" docker build -f test/Dockerfile.pre1 -t pre1-original test
/usr/bin/time -f "elapsed=%E" docker build -f test/Dockerfile.pre1.optimized -t pre1-optimized test
```

manifest-first 전략 효과를 보려면 `requirements.txt`만 바꾼 경우와 앱 코드만 바꾼 경우를 나눠서 재빌드하는 것도 좋습니다.

## 3. Docker Hub push 시간 비교

실무적으로 가장 설득력 있는 지표 중 하나입니다.

```bash
docker build -f test/Dockerfile.pre1 -t 0206pdh/imgadvisor-test:pre1-original test
docker build -f test/Dockerfile.pre1.optimized -t 0206pdh/imgadvisor-test:pre1-optimized test

/usr/bin/time -f "elapsed=%E" docker push 0206pdh/imgadvisor-test:pre1-original
/usr/bin/time -f "elapsed=%E" docker push 0206pdh/imgadvisor-test:pre1-optimized
```

권장:

- 태그는 `pre1-original-v1`, `pre1-optimized-v1`처럼 실험 번호를 붙여 관리
- 같은 네트워크 상태에서 2~3회 반복 측정

## 4. Docker Hub pull 시간 비교

배포 환경에서 체감되는 지표입니다.

```bash
docker rmi 0206pdh/imgadvisor-test:pre1-original
/usr/bin/time -f "elapsed=%E" docker pull 0206pdh/imgadvisor-test:pre1-original

docker rmi 0206pdh/imgadvisor-test:pre1-optimized
/usr/bin/time -f "elapsed=%E" docker pull 0206pdh/imgadvisor-test:pre1-optimized
```

주의:

- 로컬 캐시를 완전히 통제하려면 새 VM 또는 새 Docker host가 더 정확합니다.
- `docker rmi`만으로도 실험은 가능하지만 완전한 무캐시 상태를 보장하지는 않습니다.

## 5. 컨테이너 시작 후 첫 응답 시간

이미지 경량화와 runtime 정리의 효과를 보기 좋은 지표입니다.

예시:

```bash
docker run --rm -d --name pre1-orig -p 5000:5000 pre1-original
curl http://127.0.0.1:5000/
docker rm -f pre1-orig

docker run --rm -d --name pre1-opt -p 5000:5000 pre1-optimized
curl http://127.0.0.1:5000/
docker rm -f pre1-opt
```

더 엄밀히 하려면 `docker run` 직후부터 첫 200 응답까지 시간을 스크립트로 측정합니다.

비교 포인트:

- 실행 가능 여부
- 첫 성공 응답까지 시간
- 시작 실패 여부

## 6. 실제 HTTP 부하테스트

이 단계는 "경량화 후에도 성능이 유지되는가"를 검증하는 용도로 쓰는 것이 좋습니다.

권장 도구:

- `hey`
- `wrk`
- `ab`

예시:

```bash
hey -n 10000 -c 100 http://127.0.0.1:5000/
```

또는:

```bash
wrk -t4 -c100 -d30s http://127.0.0.1:5000/
```

기록 항목:

- RPS
- 평균 latency
- p95 latency
- p99 latency
- 에러율

## 7. 메모리/CPU 사용량 비교

이미지 경량화는 런타임 메모리에도 영향을 줄 수 있습니다.

```bash
docker stats --no-stream pre1-orig
docker stats --no-stream pre1-opt
```

또는 컨테이너를 띄운 뒤 일정 부하를 준 상태에서:

- CPU 사용률
- 메모리 사용량
- 네트워크 I/O

를 함께 기록합니다.

## 테스트 설계 시 주의점

### 엔트리포인트가 바뀐 경우

`pre1`처럼 `flask run`이 `gunicorn`으로 바뀌면, 순수 이미지 경량화 효과와 서버 교체 효과가 같이 나타납니다.

이 경우 결과 해석을 두 단계로 나누는 것이 좋습니다.

- 이미지/배포 효율 개선
- 런타임 서버 개선

즉 `pre1`은 "이미지 경량화 + 엔트리포인트 개선"이 함께 반영된 케이스로 보는 것이 맞습니다.

### `pre2`와 `pre3`의 의미

- `pre2`: Uvicorn 엔트리포인트를 유지한 채 구조와 이미지 크기를 줄이는 케이스
- `pre3`: `requirements.txt` 기반 dependency layer 전략이 얼마나 유지되는지 보는 케이스

## 권장 비교 표

아래 항목을 표로 정리하면 발표나 문서화에 가장 적합합니다.

| 케이스 | 원본 크기 | 최적화 크기 | 빌드 시간 | push 시간 | pull 시간 | 첫 응답 시간 | p95 latency | 메모리 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pre1 |  |  |  |  |  |  |  |  |
| pre2 |  |  |  |  |  |  |  |  |
| pre3 |  |  |  |  |  |  |  |  |

## 추천 결론 방식

결과를 설명할 때는 아래 순서가 가장 자연스럽습니다.

1. 이미지 크기가 얼마나 줄었는가
2. 빌드/배포 시간이 얼마나 줄었는가
3. 실행과 부하테스트에서 회귀가 없는가
4. 엔트리포인트 변경이 있는 경우, 그것이 성능에 어떤 영향을 주었는가

이렇게 정리하면 단순 "가벼워졌다"가 아니라 실제 운영상 이점을 더 설득력 있게 보여줄 수 있습니다.
