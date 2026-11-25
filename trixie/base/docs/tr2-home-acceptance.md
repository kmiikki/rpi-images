# Raspberry Pi 5 HOME acceptance on tr2

On 25 November 2026, the operator completed a clean interactive HOME
installation over Ethernet SSH on a Raspberry Pi 5 with 8 GB RAM, a 64 GB
SD card and an IMX708 Camera Module 3. The card used Raspberry Pi OS Trixie
Full 64-bit dated 6 October 2026 and Raspberry Pi Imager 1.8.5.

## Physical results

| Check | Result | Observation |
|---|---|---|
| Clean installation and catalog | PASS, original installation | HOME offered multiple matching catalogs, excluded AALTO, retained the selection across reboot, and installed equivalent JSON with verified ownership and mode 0600. |
| OS, boot and access | PASS, original installation | Full upgrade, stock v8 kernel transition, 4096-byte pages, I²C/SPI nodes, hostname and key-based SSH survived installation and reboot. NTP synchronized with time.mikes.fi. |
| Scientific and hardware environments | PASS, original installation | Automated Scientific Python verification completed. Hardware Python imported Picamera2 and detected the IMX708. Spyder opened with an IPython console and HTML Help. OpenCV, the Finnish keyboard layout and LXTerminal zoom shortcuts passed. |
| WLAN repair | PASS, corrected installer | The initial global domain was 00, the PHY reported 99, rfkill showed a software block, and NetworkManager Wi-Fi was disabled. Standalone lifecycle repair produced FI in the boot command line and global domain, radio enabled, and both WLAN blocks clear. The driver still reported PHY 99. A second repair and a separate verify succeeded. Ethernet stayed up through the same SSH session. Bluetooth remained unblocked. |
| Locale | PASS, SSH and on-device PTY | With an unavailable forwarded fi_FI.UTF-8 LC_TIME, the corrected command environment ran Perl and reported UTF-8 from locale without backend warnings. This passed over SSH and inside an on-device terminal pair with SSH variables removed. The second check emulated a local terminal. |
| Kernel and WLAN plan | PASS, corrected installer | The HOME plan reported “Ready – stock v8 kernel, 4096 byte pages” for 6.18.60+rpt-rpi-v8 and showed the FI WLAN policy. |
| WLAN after reboot | PENDING | At the operator's request, tr2 kept its active connections. A host-specific, enabled oneshot service will read back the radio and country on the next boot. Its probe and unit validation passed. The result will be stored at the path below. |

The physical retest used a temporary copy of the corrected installer in RAM.
It did not repeat the accepted OS upgrade or reinstall either Python environment.
The one-time readback has no network configuration commands. After the next boot,
retrieve the dated PASS or FAIL result from the workstation with:

```sh
ssh tr2 sudo cat /var/lib/rpi-images/tr2-wlan-20261125/result.txt
```

If the file is missing after startup, inspect `journalctl -b -u tr2-wlan-acceptance.service`
on tr2. The check allows up to one minute for radio initialization. Once the
result exists, systemd skips the unit on subsequent boots.

## Diagnosis and corrections

| Issue | Cause | Correction |
|---|---|---|
| Keyboard setup warnings | The SSH client forwarded an LC_TIME value missing from the target's locale inventory. Keyboard configuration passed this environment to raspi-config and Perl. | Validate locale values before launching children, retain usable categories, and fall back for unavailable overrides. Root keyboard setup can generate an explicitly enabled missing locale. XKB selection is independent of interface language. |
| Staircase output | APT's internal dpkg PTY can put inherited terminal input into raw mode. When input and output share the terminal, this disables output post-processing. The line logger decoded CR/LF and printed LF while the terminal no longer supplied the carriage return. | Disable the inner dpkg PTY and fancy progress for logged APT, retain a single merged stream, handle line endings according to OPOST/ONLCR and restore termios when the command exits or is interrupted. |
| WLAN disabled | Setup configured neither the regulatory country nor the radio. Unset country, software rfkill and disabled NetworkManager Wi-Fi persisted through the accepted install. | Offer an ISO country in all three profiles, preserve existing valid country choices, call Trixie's raspi-config for country changes, enable WLAN, and verify boot settings and live state. Repair uses the same implementation. |
| Stale kernel plan | The plan printed a static approval notice regardless of the running kernel and installed artifacts. | Inspect firmware selection, image, initramfs, modules, running release, page size and outstanding reboot state before displaying the plan. |
| Duplicate mapping and browse failure | Both selection and execution printed the accepted default mapping. The opener was backgrounded with errors discarded. | Show the default mapping and authorization note once, retain confirmation and destination, check for a graphical session and propagate opener failures. |

The APT diagnosis was reproduced on Niobium with a real local fixture package,
isolated APT state and dpkg root, and a shared terminal pair. With the
pre-correction logger the transaction emitted nine LF bytes without a preceding
CR. With the corrected logger it emitted zero. Unpack and configure messages
each appeared once on screen and once in the log. The terminal attributes
matched their original values afterwards. [APT implementation of dpkg PTY setup](https://github.com/Debian/apt/blob/main/apt-pkg/deb/dpkgpm.cc)

## Automated regression and scope

The complete suite on Niobium ran **435 tests: 434 passed and one was skipped**.
The skipped case requires a native ARM64 kernel with 16 KiB pages and a prepared
Spyder environment. Coverage includes all three profile plans, an approved
international country across first-install reboot and resume, existing-machine
repair, read-only preview, stale plans, unavailable hardware, rfkill and
driver-specific reporting. PTY tests exercise merged stdout/stderr, CR and LF,
exit status 17, interruption and terminal restoration. Share tests cover the
default confirmation, absent graphical session, failed opener and successful
dispatch. The suite also passed the actual LibreOffice catalog round trips.

Temporary work used RAM-backed storage. The 32 GiB workstation mount had
30 GiB free before the suite. No production share or credential was required
for these checks.

| Outstanding acceptance | Status |
|---|---|
| Next-boot WLAN persistence on tr2 | Queued for the next operator-selected boot. |
| Matplotlib QtAgg and interactive Plotly on this installation | Pending graphical acceptance. |
| IMX708 capture | Detection passed. Frame capture remains pending. |
| Physical Raspberry Pi 4 | Pending. |
| NAS file access | Blocked externally. Both tr2 and the workstation could not reach the NAS during acceptance. |
| Corrected full OS upgrade on a physical console | Output verified with real APT/dpkg on Niobium. Repeating an upgrade on tr2 was outside the non-destructive retest. |

The installation and repair commands are in the [unified setup guide](unified-setup.md).

## Files in this correction round

Paths below are relative to `trixie/base/`. Earlier staged catalog-discovery
and profile changes are a separate review in the same working tree.

| Area | Files |
|---|---|
| Keyboard and share commands | `bin/rpi-keyboard`, `bin/rpi-share` |
| Installer and maintenance | `install/setup_rpi.py`, `install/preboot.py`, `install/lifecycle.py`, `install/wlan.py` |
| Package output | `install/diagnostics.py`, `install/pre_profile.sh`, `install/install_rpi_base.sh`, `install/create_rpi_env.sh` |
| Regression tests | `tests/test_installer_terminal.py`, `tests/test_os_upgrade.py`, `tests/test_rpi_keyboard.py`, `tests/test_rpi_preboot.py`, `tests/test_rpi_share_backends.py`, `tests/test_wlan.py` |
| Guides and evidence | `docs/unified-setup.md`, `docs/rpi-share.md`, `docs/tr2-home-acceptance.md` |
