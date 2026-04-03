# dockimage_scanner

이 저장소의 실제 프로젝트는 [dockfile_scanner](./dockfile_scanner) 하위 디렉터리에 있습니다.

`imgadvisor` 설치와 사용은 아래 문서를 기준으로 보면 됩니다.

- 프로젝트 문서: [dockfile_scanner/README.md](./dockfile_scanner/README.md)

## 빠른 설치

최신 release 기준 설치:

```bash
curl -fsSL https://raw.githubusercontent.com/0206pdh/dockimage_scanner/main/dockfile_scanner/install.sh | bash
```

직접 설치:

```bash
python -m pip install --no-cache-dir --force-reinstall \
  "git+https://github.com/0206pdh/dockimage_scanner.git@main#subdirectory=dockfile_scanner"
```

특정 태그 설치:

```bash
python -m pip install --no-cache-dir --force-reinstall \
  "git+https://github.com/0206pdh/dockimage_scanner.git@v0.3.9#subdirectory=dockfile_scanner"
```

## 프로젝트 위치

핵심 파일은 모두 `dockfile_scanner/` 아래에 있습니다.

- 패키지: [dockfile_scanner/imgadvisor](./dockfile_scanner/imgadvisor)
- 설치 스크립트: [dockfile_scanner/install.sh](./dockfile_scanner/install.sh)
- 테스트 Dockerfile: [dockfile_scanner/test](./dockfile_scanner/test)
