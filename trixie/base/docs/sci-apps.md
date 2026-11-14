# Raspberry Pi application installation v0.1.0

> This document describes the retained cam-imgcheck pilot and its existing
> HOME/AALTO integration. The broader application installer is maintained in
> the Scientific Imaging repository under `scripts/install/`. That installer
> reuses this engine with application/native packaging extensions; the two
> copies have not been merged or replaced. Trixie provisions OS/APT and Python
> environments; Scientific Imaging provisions applications. Use one ownership
> path per application. See [base installation](../README.md#scientific-imaging-applications-and-build-dependencies).


The optional Bash steps in `install/` can be run against previously provisioned environments. For a new HOME or AALTO system, pass `--with-cam-imgcheck /path/to/scientific-imaging` to the corresponding existing run script to select the application and its rpi prerequisite before provisioning. Omitting the option preserves the environment-only profile. For a running system use the application-only commands below. The full HOME/AALTO scripts still perform their original account and OS provisioning. A full APT upgrade in the Pi base step requires explicit `DO_APT_UPGRADE=1`.

## Review and install

From the distribution's `trixie/base` directory, with a trusted source checkout:

```bash
bash install/install_sci_apps.sh --source /path/to/scientific-imaging --plan
sudo bash install/install_sci_apps.sh --source /path/to/scientific-imaging
bash install/verify_sci_apps.sh
cam-imgcheck --version
```

Interactive installation displays the release, destination, command and interpreter, then asks once (default N). For a previously approved release add `--approve cam-imgcheck`. Use the same `--target /absolute/path/to/sci` on both steps for a staging prefix. The parent must exist. The target and its ancestors must meet the existing shebang tool's trust policy and lie outside source checkouts. On the pilot Pi, / itself failed this check. A change to host ownership and permissions requires a separate administration decision; do not bypass the check. A plan performs imports and conflicts checks without creating the target. An identical reinstall verifies the existing release and returns KEEP. No APT, Conda, sudo configuration or camera opening occurs in the application step.

## Files and startup

The profile pins the cam-imgcheck 0.1.2 release. The existing LF-terminated `cam-imgcheck.py` launcher resolves its own path and executes the bundled `source/apps/capture/rpi/cam-imgcheck.py`. The latter has a CRLF shebang and works as an internal Python file. A relative command symlink in bin-rpi points to the original launcher copy inside `lib/cam-imgcheck-0.1.2`. It receives the verified rpi shebang through the existing tool. The launcher, imgcheck package, still backend, USB common modules, preview support, ROI editor and focus helper retain their relative source layout. Runtime options include --help, --version, --camera, --config, --roi-file, --list-cameras and --once. The camera configuration and ROI JSON are user inputs; they are not required installed defaults. The package's own offline regressions are under source/tests/rpi_imgcheck and source/tests/rpi_camera. The legacy source installer and reference applications are not executed.

The base step creates bin, bin-rpi and lib. A single POSIX PATH snippet adds the two command directories once for login and interactive shells. Existing /opt/lab/bin and its legacy PATH snippet are preserved. The pilot machine had no entries in that directory. The Miniforge installation publishes its command in /usr/local/bin, and its profile fragment no longer prepends base/bin after lab314 activation. The activation step loads the Conda hook and uses Conda's own prompt modifier; deactivation restores the previous prompt and system Python. These snippets take effect on a newly provisioned system. Installing a single app on an existing system does not rewrite shell settings.

A fixed shebang selects the initial interpreter. PATH and CONDA_PREFIX can still describe lab314, and PYTHONHOME, PYTHONPATH, LD_LIBRARY_PATH and Qt variables can affect the running program. The probe imports dependencies with the selected binary and inherited environment, verifies its prefix and imports application modules from their installed location. Use a clean shell to diagnose contamination; do not export global PYTHONPATH entries for application helpers. Python 3.13 native hardware bindings stay in the 3.13 process. Independently executed helpers can use their own shebang.

## Profiles, updates and recovery

Pass `--profile FILE` to either step to select another reviewed release JSON. The file specifies the command name, version, source subdirectory, bin category, relative entry, environment, expected interpreter, required external imports, application import location, verification modules, expected --version output and SHA-256 for each selected source file. See [the pilot profile](../config/cam-imgcheck.json). A portable entry uses environment portable and interpreter /usr/bin/env python3. Only trusted profiles and source bundles should be installed; verification imports application code. Preserve the source checkout and the approved profile together to reproduce a release.

Installation locks the destination parent for cooperating installers, stages files on the destination filesystem, runs the existing shebang dry-run and approved apply on the staged entry, and verifies hashes, imports and version before publishing the private runtime and then its command. Caught errors and signals clean up the newly published artifacts. Command visibility and multi-file installation are not a single filesystem transaction across power loss. After an unclean shutdown run verify, inspect any reported incomplete release and isolate it before retrying. The installer refuses conflicting or modified releases. For data safety the removal action also checks all release bytes and the exact command link; it keeps the common directories and other applications.

For an approved update retain the old source and profile, run verify, then remove the old release in a maintenance window and install the new pinned profile. To roll back, remove the new release using **its** profile and reinstall the retained old version using the old profile. For the pilot the original state is the absence of cam-imgcheck in the new prefix:

```bash
sudo bash install/install_sci_apps.sh --remove --approve cam-imgcheck
```

## Pilot and production decision, 2026-11-13

- PASS on Niobium: 69 standard-library tests (53 existing shebang regressions and 16 installer tests). They cover isolated command layout, exact source preservation, helper bytes, approval, real system and portable shebangs, refused writes, drift and conflicts, unavailable dependencies and interpreters, interrupted publication and rollback, plus HOME/AALTO stage order with provisioning steps replaced by fixtures.
- PASS on the Raspberry Pi: the final package was installed as kim in a private mount namespace and a chroot rooted on a new 64 MiB ext4 image on the exFAT T9. Host Python environments and system libraries were mounted read-only. The test ran the shipped Bash activation block in login and non-login interactive shells with the real Conda hook, checked both interpreter names, prompt and deactivation. While lab314 was active, the installed command used /opt/rpi/bin/python3 (3.13.13), imported APT Picamera2/libcamera/OpenCV and rpi NumPy, loaded the bundled backend, GUI and review modules without opening cameras, and passed --help and --version. An unchanged second install retained inode and mtime fingerprints. Explicit removal and reinstallation passed. The pilot package, image and log are under `/media/kim/T9/Codex/sci-installer-QqnrM9rb/` on the Pi.
- FAIL during preliminary runs: the profile initially rejected __init__.py; the parser was corrected. Direct installation through the host filesystem was rejected by the shebang path safety policy. A real Conda shell probe also exposed a stripped space after (lab314); the activation source now normalizes that separator following successful activation.
- BLOCKED on the real host prefix: / is owned by kim and group-writable. This needs separate review before production deployment; the pilot passes in its secure isolated root. The host's global shell settings and existing application installations were left in place.
- SKIP: full HOME/AALTO machine provisioning, lab314 candidate promotion and unrelated applications. NOT RUN: physical IMX477/IMX708 capture, live GUI and brightness matching.
- Next: review host directory trust with the administrator, obtain deployment approval, verify the approved source hashes and both environments, and run --plan against /opt/sci. Publish the reviewed PATH/activation settings separately with backups, test fresh login and non-login terminals, install the approved app and run verify from lab314. Schedule GUI and both sensor tests after this step. To undo the app installation, use the verified removal above. Restore backed-up shell snippets separately if deployed.
