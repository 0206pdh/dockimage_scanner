#!/usr/bin/env bash
set -e

REPO="0206pdh/dockimage_scanner"
TOOL="imgadvisor"
MIN_PYTHON="3.11"

# ── 색상 ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[imgadvisor]${NC} $*"; }
warn()  { echo -e "${YELLOW}[imgadvisor]${NC} $*"; }
error() { echo -e "${RED}[imgadvisor] ERROR:${NC} $*" >&2; exit 1; }

# ── Python 확인 ──────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=${ver%%.*}; minor=${ver##*.}
    if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

[ -z "$PYTHON" ] && error "Python ${MIN_PYTHON}+ 이 필요합니다. https://python.org 에서 설치하세요."
info "Python 확인: $($PYTHON --version)"

# ── pip 확인 ─────────────────────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null; then
  error "pip 가 없습니다. 'python -m ensurepip --upgrade' 로 설치하세요."
fi

# ── 설치 ─────────────────────────────────────────────────────────────────────
info "설치 중... (github.com/${REPO})"
"$PYTHON" -m pip install --quiet --upgrade \
  "git+https://github.com/${REPO}.git"

# ── 확인 ─────────────────────────────────────────────────────────────────────
if command -v "$TOOL" &>/dev/null; then
  info "설치 완료!"
  echo ""
  echo "  사용법:"
  echo "    imgadvisor analyze   --dockerfile Dockerfile"
  echo "    imgadvisor recommend --dockerfile Dockerfile --output optimized.Dockerfile"
  echo "    imgadvisor validate  --dockerfile Dockerfile --optimized optimized.Dockerfile"
  echo ""
  echo "  자세한 도움말:"
  echo "    imgadvisor --help"
else
  warn "'imgadvisor' 명령어를 찾을 수 없습니다."
  warn "pip install 경로가 PATH에 있는지 확인하세요."
  warn "  예: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
