#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=/opt/lab314
if [[ ${1:-} == --prefix && $# == 2 ]]; then prefix=$2; elif (($#)); then echo "Usage: $0 [--prefix PREFIX]" >&2; exit 2; fi
"$prefix/bin/python" -IB "$here/check_lab314.py" --prefix "$prefix" --contract "$here/../config/lab314/packages.json" --functional
if [[ -x /opt/rpi/bin/python3 ]]; then
    /opt/rpi/bin/python3 -B -c 'import sys,cv2,picamera2,libcamera; print("rpi preserved",sys.executable,cv2.__version__)'
fi
if [[ -x /opt/sci/bin-rpi/cam-imgcheck ]]; then
    . /opt/conda/etc/profile.d/conda.sh
    conda activate "$prefix"
    /opt/sci/bin-rpi/cam-imgcheck --version
fi
echo 'GUI, interactive selectROI and the Spyder desktop require separate acceptance.'
