# v1.0.0 – Unified Raspberry Pi OS Trixie Installer

Released 27 November 2026. This is the first stable release of the unified
GENERAL, HOME and AALTO installer for Raspberry Pi OS Trixie 64-bit.

## Highlights

All profiles add ReportLab, pypdf and Jinja2 to the existing lab314 environment.
The normal functional verifier now generates and validates a multipage PDF,
vector chart and self-contained HTML report in a headless session. Available
updates preserve the existing package ownership. See
[Scientific Reporting and Document Generation](scientific-reporting.md)
for commands, limitations and the reporting acceptance scope.

The unified installer asks for the hostname and WLAN country before approval
and resumes with the approved choices after reboot. It names the account before
each new password prompt and reports the live state and startup policies of SSH
and its socket. All three profiles keep existing SSH settings by default.
All three profiles also enable and generate required regional locales, including
supported SSH-forwarded categories, while preserving language and numeric
defaults. Existing installations can apply the locale repair independently.
After successful setup, all profiles recommend a final manual reboot.

AALTO defaults to regular Chromium browsing without the desktop keyring.
Browser settings and bookmarks persist, and password saving is disabled.
GENERAL and HOME default to the personal browser
policy and offer the same shared policy in Customize. Setup saves the selected
policy across reboot. Plotly continues to open in the separate Scientific
Python browser session. For FI/SE zoom shortcuts in an already running desktop
login, launch `lxterminal --no-remote`.

The optional Wolfram installation reports its APT package sizes, free space and
license terms before approval. The desktop menu names are **Wolfram Mathematica
(GUI)** and **Wolfram Language (CLI)**. The two entries retain their vendor icons
and use the installed package's GUI and interactive kernel commands.

Scientific Python 3.14 at `/opt/lab314` includes integrated Spyder and OpenCV
Qt6. The Raspberry Pi Python 3.13 hardware environment remains at `/opt/rpi`.
The installer offers the stock 4 KiB Pi 5 kernel for Spyder Help and supports
in-place package maintenance and targeted repair.

## Acceptance

| Check | Result |
|---|---|
| Maintainer's end-to-end HOME acceptance on Raspberry Pi 5 `tr3` | **PASS**. The installer completed and the maintainer confirmed functional acceptance on 27 November 2026. The PDF and HTML checks both reported **PASS**. |
| Existing `tr3` lab314 and fresh ARM64 dependency resolution | **PASS**. The in-place Conda transaction added ReportLab 5.1.2 and pypdf 7.2.0, reused Jinja2 3.1.6, and passed the normal lab314 verifier on CPython 3.14.10. The fresh install dependency solve also passed. |
| Headless offline reporting | **PASS**. The separate network-isolated test verified the multipage A4 PDF, Unicode text, bookmarks, chart, PDF merge and self-contained Plotly HTML. |
| GENERAL, HOME and AALTO installer regressions | **PASS**. The shared profile plan and reboot behavior passed. Across the regression runs, 459 tests passed and the native 16 KiB hardware test was skipped. |

The maintainer used `rpi-images-home-acceptance-20261127.zip`
(SHA-256 `8b4e93d41febbf8dcf87e75f89daa52e77b9677441cbc42d0414d35c0cf4ed6f`).
The v1.0.0 archive is built from the release tag and contains identical accepted
installer code and package configuration plus the final release documentation.

## Known limitations and untested configurations

- Standalone Qt5 WebEngine rendering is limited on the tested Trixie build.
  The stock 4 KiB Pi 5 kernel remains the supported path for Spyder's formatted
  Help. See the [Qt5 WebEngine results](tr3-qt5-webengine.md).
- Physical Raspberry Pi 4 operation and Pi 5 reporting with 16 KiB pages were
  **NOT TESTED** in this release acceptance. GENERAL and AALTO had shared
  regression coverage. The final end-to-end installation used HOME.
- USB camera operation on Raspberry Pi OS Trixie was **NOT TESTED**.
  The final HOME run omitted Scientific Imaging, which uses a reviewed
  separate checkout. Earlier CSI evidence is in the
  [Raspberry Pi 5 acceptance record](tr3-acceptance.md).
- Applying the reporting update to a live historical Conda–pip prefix and
  performing an actual targeted reporting-package reinstall were **NOT TESTED**.
  The wheel resolver, checksum validation and repair preview were checked.
- The headless reporting test validated the embedded Plotly.js and chart
  document. Interactive use of that report in a browser was **NOT TESTED**.

## Verify the release ZIP

Download `rpi-images-v1.0.0.zip` and `rpi-images-v1.0.0.zip.sha256` into the
same directory and run:

```sh
sha256sum -c rpi-images-v1.0.0.zip.sha256
```

[Changelog](../../../CHANGELOG.md) · [Unified setup](unified-setup.md) ·
[Reporting acceptance](scientific-reporting.md) ·
[Pre-release test scope](pre-release-acceptance-20261126.md)
