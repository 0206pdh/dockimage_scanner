#!/usr/bin/env bash
set -e

REPO="0206pdh/dockimage_scanner"
TOOL="imgadvisor"
VENV_DIR="${HOME}/.imgadvisor"
BIN_DIR="${HOME}/.local/bin"
MIN_PYTHON_MINOR=11

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[imgadvisor]${NC} $*"; }
warn()  { echo -e "${YELLOW}[imgadvisor]${NC} $*"; }
error() { echo -e "${RED}[imgadvisor] ERROR:${NC} $*" >&2; exit 1; }

# ── Python 3.11+ 탐색 ────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
    major=${ver%%.*}; minor=${ver##*.}
    if [ "$major" -ge 3 ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
      PYTHON="$cmd"; break
    fi
  fi
done

[ -z "$PYTHON" ] && error "Python 3.${MIN_PYTHON_MINOR}+ 이 필요합니다."
info "Python: $($PYTHON --version)"

# ── git 확인 ────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
  info "git 설치 중..."
  if command -v apt-get &>/dev/null; then
    apt-get install -y git 2>/dev/null || sudo apt-get install -y git
  elif command -v yum &>/dev/null; then
    yum install -y git 2>/dev/null || sudo yum install -y git
  else
    error "git 이 없습니다. 수동으로 설치하세요."
  fi
fi

# ── venv 생성 (시스템 Python 건드리지 않음) ──────────────────────────────────
info "가상환경 생성 중: ${VENV_DIR}"
"$PYTHON" -m venv "$VENV_DIR"

VENV_PIP="${VENV_DIR}/bin/pip"
VENV_PYTHON="${VENV_DIR}/bin/python"

# ── venv 안에서 pip 업그레이드 후 설치 ───────────────────────────────────────
info "설치 중... (github.com/${REPO})"
"$VENV_PIP" install --quiet --upgrade pip
"$VENV_PIP" install --quiet "git+https://github.com/${REPO}.git"

# ── ~/.local/bin 에 심볼릭 링크 ──────────────────────────────────────────────
mkdir -p "$BIN_DIR"
ln -sf "${VENV_DIR}/bin/${TOOL}" "${BIN_DIR}/${TOOL}"
info "심볼릭 링크: ${BIN_DIR}/${TOOL} -> ${VENV_DIR}/bin/${TOOL}"

# ── PATH 확인 ────────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
  export PATH="${BIN_DIR}:$PATH"
  warn "PATH에 ${BIN_DIR} 추가됨. 영구 적용:"
  warn "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
fi

# ── 완료 ─────────────────────────────────────────────────────────────────────
if command -v "$TOOL" &>/dev/null; then
  info "설치 완료!"
  echo ""
  echo "  사용법:"
  echo "    imgadvisor analyze   --dockerfile Dockerfile"
  echo "    imgadvisor recommend --dockerfile Dockerfile --output optimized.Dockerfile"
  echo "    imgadvisor validate  --dockerfile Dockerfile --optimized optimized.Dockerfile"
  echo ""
  echo "  도움말: imgadvisor --help"
  echo ""
  echo "  업데이트:"
  echo "    ${VENV_PIP} install --upgrade git+https://github.com/${REPO}.git"
else
  warn "설치 완료됐으나 명령어를 찾을 수 없습니다."
  warn "새 터미널을 열거나: export PATH=\"\$HOME/.local/bin:\$PATH\""
  warn "직접 실행: ${VENV_DIR}/bin/${TOOL} --help"
fi
