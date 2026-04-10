# OpenCV Qt Font Fix

## Problem

OpenCV GUI functions such as:

```python
cv2.imshow()
cv2.selectROI()
cv2.imwrite()
```

opened dialogs without any visible text or button labels in the `lab314` Python 3.14 environment on Raspberry Pi OS Trixie.

Typical error messages:

```text
qt.qpa.plugin: Could not find the Qt platform plugin "wayland"
QFontDatabase: Cannot find font directory .../cv2/qt/fonts
```

The dialogs opened, but all labels and buttons were blank.

---

## Cause

`opencv-python` installed from pip bundles its own Qt runtime under:

```text
/opt/lab314/lib/python3.14/site-packages/cv2/qt
```

However:

* only the X11 plugin `libqxcb.so` is present
* there is no `wayland` plugin
* the `fonts/` directory is missing completely

After importing `cv2`, OpenCV automatically sets:

```text
QT_QPA_PLATFORM_PLUGIN_PATH=/opt/lab314/.../cv2/qt/plugins
QT_QPA_FONTDIR=/opt/lab314/.../cv2/qt/fonts
```

Because the font directory does not exist, Qt cannot find any fonts and therefore renders empty labels.

---

## Solution

Force OpenCV Qt to use X11 (`xcb`) and create the missing font directory.

Create:

```text
/opt/lab314/lib/python3.14/site-packages/sitecustomize.py
```

with:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
```

Then create:

```text
/opt/lab314/lib/python3.14/site-packages/cv2/qt/fonts
```

and link DejaVu fonts:

```bash
mkdir -p /opt/lab314/lib/python3.14/site-packages/cv2/qt/fonts

ln -sf /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
    /opt/lab314/lib/python3.14/site-packages/cv2/qt/fonts/DejaVuSans.ttf

ln -sf /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf \
    /opt/lab314/lib/python3.14/site-packages/cv2/qt/fonts/DejaVuSans-Bold.ttf
```

This fix is performed automatically by:

```text
install/create_lab314_env.sh
```

---

## Verification

Run:

```bash
/opt/lab314/bin/python - <<'EOF'
import cv2
import numpy as np

img = np.zeros((300, 500, 3), dtype=np.uint8)
cv2.putText(img, "OpenCV GUI OK", (20, 150),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 2)

cv2.imshow("Test", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
EOF
```

Then test:

* Save dialog
* ROI dialog
* Button labels
* Text fields

If labels are visible, the fix works.
