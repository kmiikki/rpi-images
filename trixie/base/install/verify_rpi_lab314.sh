#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=/opt/lab314
flags=()
science_only=0
while (($#)); do
    case "$1" in
        --prefix) prefix=$2; shift 2 ;;
        --snapshot) flags+=(--snapshot); shift ;;
        --require-spyder) flags+=(--require-spyder); shift ;;
        --science-only) science_only=1; shift ;;
        *) echo "Usage: $0 [--prefix PREFIX] [--snapshot] [--require-spyder]" >&2; exit 2 ;;
    esac
done
"$prefix/bin/python" -IB "$here/check_lab314.py" --prefix "$prefix" --functional "${flags[@]}"
(( ! science_only )) || exit 0
if [[ -x /opt/rpi/bin/python3 ]]; then
    /opt/rpi/bin/python3 -B -c 'import sys,cv2,picamera2,libcamera; print("rpi preserved",sys.executable,cv2.__version__)'
fi
if [[ -x /opt/sci/bin-rpi/cam-imgcheck ]]; then
    . /opt/conda/etc/profile.d/conda.sh
    conda activate "$prefix"
    /opt/sci/bin-rpi/cam-imgcheck --version
fi
echo 'GUI, interactive selectROI and the Spyder desktop require separate acceptance.'
