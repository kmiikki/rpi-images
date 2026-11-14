#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=/opt/lab314
while (($#)); do
    case "$1" in
        --prefix) prefix=$2; shift 2 ;;
        --help) echo "Usage: $0 [--prefix ABSOLUTE_NEW_PREFIX]"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $prefix == /* && $(realpath -m -- "$prefix") == "$prefix" ]] || { echo 'Noncanonical prefix' >&2; exit 2; }
[[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || { echo 'This lock targets Linux ARM64' >&2; exit 2; }
contract="$here/../config/lab314/packages.json"
check() { "$prefix/bin/python" -IB "$here/check_lab314.py" --prefix "$prefix" --contract "$contract" "$@"; }
if [[ -e $prefix || -L $prefix ]]; then
    if [[ -x $prefix/bin/python ]] && check; then
        echo "KEEP $prefix"
        exit 0
    fi
    echo "Existing prefix differs or is incomplete. Choose a new --prefix; no files replaced." >&2
    exit 1
fi
[[ -d $(dirname -- "$prefix") && -x /opt/conda/bin/conda ]] || { echo 'Missing parent or Conda' >&2; exit 2; }
# Keep caches with the selected installation filesystem, never base's cache.
mkdir -m 700 -- "$prefix"
work=$(mktemp -d -- "$(dirname -- "$prefix")/.lab314-build.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
export CONDA_PKGS_DIRS="$work/conda-pkgs" TMPDIR="$work" PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
if ! /opt/conda/bin/conda create -y --no-default-packages -p "$prefix" --file "$here/../config/lab314/conda-linux-aarch64.txt"; then
    echo "Failed prefix retained at $prefix for diagnosis" >&2; exit 1
fi
"$prefix/bin/python" -m pip install --only-binary=:all: --require-hashes --no-deps -r "$here/../config/lab314/wheels.txt"
# OpenCV wheel declares this font directory but does not bundle it.
site="$prefix/lib/python3.14/site-packages"
mkdir -p "$site/cv2/qt/fonts"
for font in DejaVuSans.ttf DejaVuSans-Bold.ttf; do
    [[ -f /usr/share/fonts/truetype/dejavu/$font ]] || { echo "Missing Qt font $font" >&2; exit 1; }
    ln -s /usr/share/fonts/truetype/dejavu/"$font" "$site/cv2/qt/fonts/$font"
done
printf '%s\n' 'import os' 'os.environ.setdefault("QT_QPA_PLATFORM", "xcb")' > "$site/sitecustomize.py"
check --functional
