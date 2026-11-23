#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=/opt/lab314
mode=normal
selected=()
plan=0
spyder=integrated
while (($#)); do
    case "$1" in
        --package) selected+=(--package "$2"); shift 2 ;;
        --plan) plan=1; shift ;;
        --snapshot) mode=snapshot; shift ;;
        --prefix) prefix=$2; shift 2 ;;
        --without-spyder) spyder=none; shift ;;
        --external-spyder) spyder=external; shift ;;
        --help) echo "Usage: $0 [--prefix ABSOLUTE_NEW_PREFIX] [--without-spyder | --external-spyder] [--snapshot] [--package REQUIREMENT ...] [--plan]"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $prefix == /* && $(realpath -m -- "$prefix") == "$prefix" ]] || { echo 'Noncanonical prefix' >&2; exit 2; }
[[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]] || { echo 'This installer targets Linux ARM64' >&2; exit 2; }
contract="$here/../config/lab314/packages.json"
check() {
    local flags=()
    [[ $mode != snapshot ]] || flags+=(--snapshot)
    "$prefix/bin/python" -IB "$here/check_lab314.py" --prefix "$prefix" --contract "$contract" "${flags[@]}" "$@"
}
if [[ $mode == snapshot ]]; then
    (cd "$here/../config/lab314" && sha256sum -c SHA256SUMS)
fi
if [[ -e $prefix || -L $prefix ]]; then
    [[ -x $prefix/bin/python && -d $prefix/conda-meta ]] || { echo 'Existing prefix is incomplete; no files replaced.' >&2; exit 1; }
    if [[ $mode == snapshot ]]; then
        ((${#selected[@]} == 0 && plan == 0)) || { echo 'Snapshot mode does not update packages.' >&2; exit 2; }
        check
        echo "KEEP exact snapshot $prefix"
    else
        update=("${selected[@]}")
        ((${#update[@]})) || update=(--all)
        if ((plan)); then
            "$prefix/bin/python" -IB "$here/update_lab314.py" --prefix "$prefix" "${update[@]}"
        else
            # Small persistent operation records, never a replacement environment.
            records=$(mktemp -d -- "$(dirname -- "$prefix")/.lab314-update.XXXXXXXX")
            TMPDIR="$records" "$prefix/bin/python" -IB "$here/update_lab314.py" --prefix "$prefix" "${update[@]}" --apply --record-dir "$records/state"
            echo "Update completed; records: $records/state"
        fi
    fi
    exit 0
fi
((${#selected[@]} == 0 && plan == 0)) || { echo 'Targeted updates/plans require an existing prefix.' >&2; exit 2; }
[[ -d $(dirname -- "$prefix") && -x /opt/conda/bin/conda ]] || { echo 'Missing parent or Conda' >&2; exit 2; }
# Keep caches with the selected installation filesystem, never base's cache.
work=$(mktemp -d -- "$(dirname -- "$prefix")/.lab314-build.XXXXXXXX")
trap 'code=$?; rm -rf -- "$work" || true; exit "$code"' EXIT
export CONDA_PKGS_DIRS="$work/conda-pkgs" TMPDIR="$work" PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
if [[ $mode == normal && $spyder != external ]]; then
    echo "Scientific Python: preparing Conda requirements for $prefix" >&2
    df -Pk -- "$work" >&2
    specs=$(/opt/conda/bin/python -B "$here/lab314_policy.py" --conda-specs "$spyder")
    mapfile -t conda_specs <<< "$specs"
    create=(/opt/conda/bin/conda create -y --no-default-packages --override-channels -c conda-forge -p "$prefix")
    flags=()
    if [[ $spyder == integrated ]]; then
        echo "Scientific Python: resolving ARM64 packages and stable Spyder" >&2
        if "${create[@]}" --dry-run --json "${conda_specs[@]}" > "$work/solver.json"; then
            :
        else
            status=$?
            cat "$work/solver.json" >&2 || true
            exit "$status"
        fi
        version=$(/opt/conda/bin/python -B "$here/lab314_policy.py" --solved-spyder < "$work/solver.json")
        conda_specs[-1]="spyder==$version"
        flags+=(--require-spyder)
    fi
    echo "Scientific Python: downloading and installing resolved packages" >&2
    "${create[@]}" "${conda_specs[@]}"
    echo "Scientific Python: checking installed packages, graphics backend and IPython kernel" >&2
    check --functional --require-opencv-target "${flags[@]}"
    exit 0
fi
if [[ $mode == snapshot ]]; then
    /opt/conda/bin/conda create -y --no-default-packages -p "$prefix" --file "$here/../config/lab314/conda-linux-aarch64.txt"
    "$prefix/bin/python" -m pip install --only-binary=:all: --require-hashes --no-deps -r "$here/../config/lab314/wheels.txt"
else
    # Resolve the direct product requirements, not the historical transitive set.
    /usr/bin/python3 -B "$here/lab314_policy.py" > /dev/null
    mapfile -t conda_specs < <(/usr/bin/python3 -c 'import json,sys;print("\n".join(json.load(open(sys.argv[1]))["conda"]))' "$here/../config/lab314/requirements.json")
    /opt/conda/bin/conda create -y --no-default-packages --override-channels -c conda-forge -p "$prefix" "${conda_specs[@]}"
    "$prefix/bin/python" -B "$here/update_lab314.py" --initialize --apply --record-dir "$work/initial-install"
fi
# OpenCV wheel declares this font directory but does not bundle it.
site="$prefix/lib/python3.14/site-packages"
mkdir -p "$site/cv2/qt/fonts"
for font in DejaVuSans.ttf DejaVuSans-Bold.ttf; do
    [[ -f /usr/share/fonts/truetype/dejavu/$font ]] || { echo "Missing Qt font $font" >&2; exit 1; }
    ln -s /usr/share/fonts/truetype/dejavu/"$font" "$site/cv2/qt/fonts/$font"
done
printf '%s\n' 'import os' 'os.environ.setdefault("QT_QPA_PLATFORM", "xcb")' > "$site/sitecustomize.py"
check --functional
