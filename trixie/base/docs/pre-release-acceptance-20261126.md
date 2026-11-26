# Raspberry Pi 5 pre-release acceptance · 26 November 2026 · r2

**Manual acceptance is pending.** Use one clean HOME install on tr3 with
Raspberry Pi OS Trixie Full 64-bit. In Imager use hostname `tr3`, account
`kim` and leave SSH disabled. Use Ethernet or local Wi-Fi and the Pi desktop.

## One installation on tr3

1. Verify `sha256sum -c rpi-images-pre-release-acceptance-20261126-r2.zip.sha256`
   and extract the ZIP. From the extracted tree, run the following in a
   terminal as `kim`. The extra local administrator `tr3-it` exercises A02.

   ```bash
   cd rpi-images-main/trixie/base/install
   sudo bash setup-rpi.sh --profile HOME --primary-user kim \
     --additional-user tr3-it --ntp-server time.mikes.fi --ssh keep \
     --keyboard-layout fi --wlan-country FI --wolfram \
     --chromium-policy shared --share-later --no-imaging
   ```

2. **A01, A03, A04, A08.** At **Hostname**, enter `tr3!` once to check the
   validation error, then press Enter to keep `tr3`. Check the plan for FI,
   `time.mikes.fi`, SSH `keep`, Chromium `shared`, and Wolfram's package sizes,
   free space and license. Review the terms before approving the Wolfram
   install. Approve the displayed I²C/SPI and 4 KiB kernel changes if prompted.
   Scientific Imaging is tested separately. Shares are deferred.
3. **A02–A03, A08.** After each requested reboot, resume with just
   `sudo bash setup-rpi.sh`. Check that setup reuses FI and the selected
   components and browser policy. When `passwd` opens, the previous message
   should name `tr3-it` and its additional administrator role. Check `tr3`,
   FI and the shared browser policy in the summary. Compare
   `sudo bash setup-rpi.sh --manage --action verify --component profile`
   with `hostnamectl --static`, the local `127.0.1.1` alias in `/etc/hosts`
   and the active/startup states of `ssh.service` and `ssh.socket`.
4. **A05.** As `kim`, open `lxterminal --no-remote`. Try **Ctrl + +**,
   **Ctrl + −** and **Ctrl + 0** with FI selected. The installer summary
   should name the account and explain how to open a separate process.
5. **A06.** The R2 acceptance run rejected forced Guest mode. Apply the
   [Chromium-only repair](unified-setup.md#chromium-policy) before this retest.
   Start Chromium from the menu in a fresh desktop session. Add a test
   bookmark, fully exit Chromium and start `chromium` in a terminal. Both
   launches should open a regular window without a keyring prompt, and the
   bookmark should persist. Check `PasswordManagerEnabled=false` at
   `chrome://policy`. In Spyder run
   `import plotly.express as px; px.line(y=[1, 3, 2]).show()`. The figure
   should open in the separate Scientific Python Firefox session without a
   keyring prompt. A prompt, forced Guest or Incognito mode, or loss of the
   bookmark blocks A06.
6. **A07.** Find exactly **Wolfram Mathematica (GUI)** and **Wolfram Language
   (CLI)** under the Wolfram menu entries. Check the vendor icons and launch both.
   In the CLI evaluate `2+2`, expect `4`, then enter `Quit[]`.
   In a GUI notebook evaluate `Plot[Sin[x], {x, 0, 2 Pi}]` with Shift+Enter.
   If the WolframScript check was limited, run `wolframscript -code '2+2'`
   as `kim`. Duplicate or broken menu entries block A07.
7. **Separate CSI smoke test.** Use Camera Module 3 if available.
   Run `rpicam-hello --list-cameras`. From the reviewed Scientific Imaging
   checkout run `sudo bash scripts/install/01-install.sh --app cam-imgcheck --plan`,
   then run it without `--plan` and diagnose with
   `sudo bash scripts/install/02-diagnose.sh --app cam-imgcheck`.
   Check preview, save one still, and try one exposure or gain change and one
   ROI. Repeat with HQ Camera IMX477 if convenient. Power off before
   swapping ribbons. Record the sensor and result. AALTO mounts need no home retest.

## Correction and regression report

| Item | Implementation | Automatic evidence | Physical Pi 5 acceptance |
|---|---|---|---|
| A01 hostname | Complete | **PASS** all-profile prompt, invalid input retry, keep/cancel, local alias edits, dry-run and saved selection | **PENDING MANUAL ACCEPTANCE** static name and hosts mapping across reboot |
| A02 account prompt | Complete | **PASS** account role and name before password entry, account guards and password retention | **PENDING MANUAL ACCEPTANCE** real maintenance account prompt |
| A03 WLAN and resume | Complete | **PASS** simulated reboot, boot/active readback, drift, repair and saved catalog checks | **PENDING MANUAL ACCEPTANCE** physical radio and resume |
| A04 Wolfram preflight | Complete | **PASS** size metadata, free-space guard, changed candidate and explicit license approval | **PENDING MANUAL ACCEPTANCE** actual APT candidate and space |
| A05 LXTerminal | Complete | **PASS** FI/SE edits, account handling, idempotence and scoped restoration. Trixie ships the separate-process option | **PENDING MANUAL ACCEPTANCE** accelerators in new window |
| A06 Chromium | Complete | **PASS** default, Customize and CLI choices across profiles, saved policy, hook, repair, Update All and scoped return to personal. Plotly regressions passed | **PENDING MANUAL ACCEPTANCE** fresh-session menu, terminal and Plotly |
| A07 Wolfram launchers | Complete | **PASS** optional selection in all profiles, simulated vendor entries, desktop-file validation, duplicate suppression, repair, update and owned removal | **PENDING MANUAL ACCEPTANCE** package entries, both launches and plot |
| A08 SSH | Complete | **PASS** state from nonzero systemctl probes, service/socket startup, read-only output and keep policy | **PENDING MANUAL ACCEPTANCE** compare with live units |

GENERAL, HOME and AALTO passed the common A01–A08 regression coverage using
profile fixtures. The matrix exercised the personal defaults on GENERAL/HOME,
the shared default on AALTO and policy overrides, Wolfram selection and
deselection, and read-only plans. The simulated reboot resumed the explicit
selection in each profile. Live hardware and desktop acceptance uses HOME once.

### Automatic test scope

- **PASS** 446 repository tests passed across the sandbox and LibreOffice
  rerun. One hardware-specific test was skipped. Syntax checks passed for
  43 shell files, 57 Python files and 7 JSON files. The public share example
  validated against its JSON schema.
- **PASS** Both actual LibreOffice CSV/ODS round-trip tests with an isolated
  temporary profile outside the sandbox. The sandbox run recorded three
  failures across their subcases when LibreOffice could not start conversion.
- **PASS** Scientific Imaging's separate 35-test installer and payload suite.
  Ubuntu's read-only plan selected the portable USB Light Edition recorder
  and left the temporary installation path absent. The same installer marked
  the selected Pi-only applications unsupported on Ubuntu.
- **LIMITED** RPi desktop and package checks used fixtures. The development host
  lacks the tested arm64 OS packages, desktop session and CSI hardware.
- **NOT TESTED** The optional native ARM64 16 KiB Spyder probe was skipped.
  The standalone Qt5 WebEngine renderer remains limited on the tested Trixie
  build. Spyder Help worked on the earlier 4 KiB Pi 5.
- **NOT TESTED** USB camera operation on either platform this round. USB camera
  support is included in this release. USB cameras have not been tested or
  validated on Raspberry Pi OS Trixie for this release. Compatibility and
  correct operation on this platform are not guaranteed. The USB Full
  recorder is cataloged for Ubuntu only. Native Pi `cam-preview` and camera
  applications still need physical testing.

### Previously observed in AALTO

The 25 November sample used a Pi 5 with 8 GB RAM, Trixie Full 64-bit
(Debian 13.7), 128 GB microSD and HQ Camera IMX477. The stock
`6.18.60+rpt-rpi-v8` kernel ran with 4096-byte pages and the installation
used about 27 GB including Wolfram. Spyder desktop and terminal starts,
IPython, formatted Help, Matplotlib QtAgg, OpenCV HighGUI, Plotly,
interpreter switching to `/opt/rpi`, Picamera2 and live camera image
worked. AALTO mounts, the Finnish keyboard, LXTerminal zoom after reboot,
Wolfram CLI, the Mathematica GUI and notebook plotting worked. These results
apply to that sample. The corrected desktop routes and current Scientific
Imaging camera tests remain pending.
