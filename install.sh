#!/usr/bin/env bash
set -e

REPO="0206pdh/dockimage_scanner"
TOOL="imgadvisor"
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

if [ -z "$PYTHON" ]; then
  error "Python 3.${MIN_PYTHON_MINOR}+ 이 필요합니다.
  Ubuntu/Debian: sudo apt update && sudo apt install -y python3.11
  macOS:         brew install python@3.11"
fi
info "Python: $($PYTHON --version)"

# ── pip 확인 및 자동 설치 ────────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null 2>&1; then
  warn "pip 없음 — 자동 설치 시도..."
  if command -v apt-get &>/dev/null; then
    sudo apt-get install -y python3-pip 2>/dev/null || \
      "$PYTHON" -m ensurepip --upgrade 2>/dev/null || \
      error "pip 설치 실패. 수동으로 설치하세요: sudo apt install python3-pip"
  elif command -v yum &>/dev/null; then
    sudo yum install -y python3-pip 2>/dev/null || \
      error "pip 설치 실패. 수동으로 설치하세요: sudo yum install python3-pip"
  else
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || \
      error "pip 설치 실패. https://pip.pypa.io/en/stable/installation/ 참고"
  fi
fi

# ── git 확인 ────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
  warn "git 없음 — 자동 설치 시도..."
  if command -v apt-get &>/dev/null; then
    sudo apt-get install -y git || error "git 설치 실패"
  elif command -v yum &>/dev/null; then
    sudo yum install -y git || error "git 설치 실패"
  else
    error "git 이 없습니다. 수동으로 설치하세요."
  fi
fi

# ── imgadvisor 설치 ──────────────────────────────────────────────────────────
info "설치 중... (github.com/${REPO})"
"$PYTHON" -m pip install --quiet --upgrade \
  "git+https://github.com/${REPO}.git"

# ── PATH 처리 ────────────────────────────────────────────────────────────────
# ~/.local/bin 이 PATH에 없으면 추가
LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
  export PATH="$LOCAL_BIN:$PATH"
  warn "PATH에 $LOCAL_BIN 추가. 영구 적용하려면 ~/.bashrc 에 아래 줄 추가:"
  warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── 확인 ─────────────────────────────────────────────────────────────────────
if command -v "$TOOL" &>/dev/null; then
  info "설치 완료! ($("$TOOL" --version 2>/dev/null || echo 'v0.1.0'))"
  echo ""
  echo "  사용법:"
  echo "    imgadvisor analyze   --dockerfile Dockerfile"
  echo "    imgadvisor recommend --dockerfile Dockerfile --output optimized.Dockerfile"
  echo "    imgadvisor validate  --dockerfile Dockerfile --optimized optimized.Dockerfile"
  echo ""
  echo "  도움말:"
  echo "    imgadvisor --help"
else
  warn "'imgadvisor' 명령어를 찾을 수 없습니다."
  warn "새 터미널을 열거나 아래 명령으로 PATH를 갱신하세요:"
  warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
