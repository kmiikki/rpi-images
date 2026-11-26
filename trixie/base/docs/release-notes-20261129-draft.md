# Raspberry Pi OS Trixie · release notes draft

Target release date: 29 November 2026. Pi 5 acceptance pending.

The unified installer asks for the hostname and WLAN country before approval
and resumes with the approved choices after reboot. It names the account before
each new password prompt and reports the live state and startup policies of SSH
and its socket. All three profiles keep existing SSH settings by default.
All three profiles also enable and generate required regional locales, including
supported SSH-forwarded categories, while preserving language and numeric
defaults. Existing installations can apply the locale repair independently.

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

The release retains Scientific Python 3.14 at `/opt/lab314` with integrated
Spyder, Raspberry Pi Python 3.13 at `/opt/rpi`, and the stock 4 KiB Pi 5 kernel
for Spyder Help. Spyder Help worked in the AALTO Pi 5 sample. Standalone Qt5
WebEngine renderer use remains limited on the tested Trixie build. Scientific
Imaging applications are installed from the reviewed separate checkout.
USB camera support is included in this release. USB cameras have not been
tested or validated on Raspberry Pi OS Trixie for this release. Compatibility and
correct operation on this platform are not guaranteed.

[Changelog](../../../CHANGELOG.md) · [Unified setup](unified-setup.md) · [Acceptance and regression results](pre-release-acceptance-20261126.md)
