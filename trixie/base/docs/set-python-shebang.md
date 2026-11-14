# Selecting Python for installed entry points

`tools/set-python-shebang.py` v0.1.0 is a standalone Linux utility for Python 3.10 or newer. It uses the standard library. Run it with the permissions of the account that owns the installation. Only trusted Python installations and a trusted execution PATH should be in scope.

## Running applications

A normal analysis script keeps `#!/usr/bin/env python3`. When the terminal has actually activated lab314, `./analyze.py` uses lab314. An installed hardware logger with `#!/opt/rpi/bin/python` runs directly as `./bme280logger-v2.py -i 1 --chemcps`. The kernel reads the shebang when the executable file is invoked directly. With `python3 script.py`, the shell has already selected the interpreter and Python treats the shebang as a comment.

## Inspect and review

From `trixie/base`, run:

```sh
tools/set-python-shebang.py
tools/set-python-shebang.py --analyze analyze.py bme280logger-v2.py
tools/set-python-shebang.py --dry-run --target /opt/lab/bin --env rpi bme280logger-v2.py
tools/set-python-shebang.py --apply --target /opt/lab/bin --env rpi bme280logger-v2.py
```

The default and `--analyze` report the system and selected scripts. `--dry-run` displays the proposed first lines. With a target, dry-run and check also inspect installation path safety. `--check` verifies the desired state. `--apply` requires an explicit installation root and file list or manifest. Paths are relative to the target when supplied; explicit absolute CLI paths must be inside it. Directories are never scanned for scripts. The four modes are mutually exclusive. Any invalid or ambiguous entry blocks the whole apply before confirmation. Interactive apply shows the plan and asks once on a terminal. Type `y` to accept; Enter, `N`, EOF and Ctrl-C at the prompt leave every file untouched.

Exit 0 means a successful analysis, plan, verification or apply. Exit 1 means check found drift or an active-environment conflict, or the operator declined a change. Exit 2 indicates invalid arguments, an ambiguous or unsafe plan, or an operational error. Interrupted approval or apply returns 130. Automation should read the diagnostics as well as the exit status. A check can report a login-shell inconsistency even if all explicit shebangs match.

## How the decision is made

1. Discovery reads the OS release, architecture, system interpreter, configured /opt prefixes, active Conda prefix, the user's Conda environment registry and immediate envs directories under known prefixes. It probes existing native Python 3 executables, preferring python3 then python. A unique registered prefix named rpi or lab314 can supply the corresponding interpreter when the /opt prefix is absent. Detection works without the conda command.
2. Both PATH commands, python and python3, are compared by their reported sys.prefix with CONDA_PREFIX. This preserves the distinction between an activated prefix, a symlink to its Python binary, and the base environment. A prompt labelled lab314 can survive a login profile putting /opt/conda/bin first. Inspect the reported paths; this tool makes no changes to shell configuration.
3. The analyzer parses the selected file's bytes with Python's AST, honoring source encoding declarations. It collects import names, including dotted imports. It checks module **discovery** in isolated, time-limited interpreter processes (`-I -B`, working directory /). It uses the target interpreter's module search paths and extension suffixes. Package parents and the selected application are never imported by this probe. Python startup can execute the trusted environment's own sitecustomize and .pth hooks.
4. A manifest supplies an explicit per-file choice. Without a manifest, `--env portable|system|rpi|lab314` supplies the user's choice. For inference, a compatible portable analysis script stays portable. Known hardware imports (including Picamera2, libcamera, smbus2, RPi.GPIO and gpiod) require all collected imports to be discoverable in rpi, with system as a fallback. A unique compatible named environment can resolve other missing dependencies. Ambiguous, unresolved or dynamic inference needs review. Explicit choices are still checked for known static dependencies.
5. The plan shows the file, current line, current and proposed environments, KEEP/CHANGE, reasons and uncertainties. Changes operate on bytes; AST output is never written back.

Discovery of a module does not verify native linking, symbols, devices, optional extras or application behavior. Conditional imports are checked conservatively, even in inactive branches. Local helper packages, from-import members, runtime plugins and Python syntax newer than the analyzer can require manual review. Imports such as `import helpers.sensor_utils` execute in the main interpreter; changing the imported module's shebang cannot switch it. A separately launched executable helper can be selected explicitly. CPython 3.13-specific native extensions generally require a matching 3.13 ABI and architecture; 3.14 needs compatible builds (or an applicable stable ABI). Keep Debian dist-packages in the matching rpi environment.

## Installer contract

The installer first copies an executable to a dedicated installation directory. It supplies an independently reviewed JSON manifest and the name of the profile approved for that deployment. Keep the approved input under installer control. The profile name is an assertion by the caller, not a cryptographic signature. Derive the source SHA-256 from the trusted release copy, for example with `sha256sum bme280logger-v2.py`. Record the precise interpreter spelling from the target's dry-run.

```json
{
  "version": 1,
  "profile": "trixie-sensors",
  "target": "/opt/lab/bin",
  "files": [
    {
      "path": "bme280logger-v2.py",
      "env": "rpi",
      "from": "#!/usr/bin/env python3",
      "to": "#!/opt/rpi/bin/python3",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

Replace the example digest with the actual 64 lowercase hex digits. All fields are required. The CLI target must equal the manifest's absolute target. Entries use relative paths; duplicates, traversal and unknown fields are errors. Manifest and positional paths or `--env` cannot be combined.

```sh
tool=trixie/base/tools/set-python-shebang.py
"$tool" --dry-run --target /opt/lab/bin --manifest approved.json
"$tool" --apply --non-interactive --approved-profile trixie-sensors \
    --target /opt/lab/bin --manifest approved.json
"$tool" --check --target /opt/lab/bin --manifest approved.json
```

A future installer should stop on a failed dry-run, check the exact planned replacements against its release profile, apply, then check and run application-specific smoke tests. Unattended apply requires all three of the manifest, explicit apply and matching approval name. Already-installed bytes are accepted only if substituting the approved original header reconstructs the trusted SHA-256. This makes retries idempotent and detects body changes even after installation. The existing installer is independent of this utility.

## File integrity and concurrency

Use a dedicated, access-controlled installation tree outside Git worktrees. The installer owns the boundary between its trusted sources and managed copies. An exported source tree without Git metadata cannot be distinguished automatically from an installation. Executable Python entry points with a recognized Python 3 shebang are eligible, including extensionless commands. Missing, unknown or option-bearing shebangs and non-executable modules require separate review.

Each directory component and file is opened without following symbolic links. The utility rejects hardlinked targets, special files, set-ID files, competing write permissions and unsupported security attributes. Writers must control the destination directories; sticky system ancestors such as /tmp are supported for private staging. Keep other processes with the same UID or administrative privileges from changing the tree during apply. Advisory directory locks coordinate concurrent invocations of this utility; Linux rename has no general conditional replacement operation against arbitrary uncooperative writers.

For each changed file, the utility stages the replacement and rollback copy in its pinned parent directory, preserves ownership, mode, timestamps and extended attributes, and checks file identity and change time before replacement. Only the first line changes. LF, CRLF and a missing final newline are retained. A CRLF shebang can fail direct execution on Linux because the carriage return reaches the interpreter name or argument. Review such scripts before deployment. A KEEP result preserves the inode. Staged files are flushed before atomic rename and the directory is synced. A caught interrupt or write failure rolls back replacements already made by the batch where possible. Atomicity is per file. Power loss, SIGKILL or a filesystem failure during rollback can leave a partially applied batch. Re-run check against the approved manifest before resuming deployment.

Run the offline regressions from the repository root:

```sh
python3 -B -m unittest discover -s trixie/base/tests -p test_set_python_shebang.py -v
```

The suite uses automatically cleaned private /tmp installations and synthetic interpreter layouts. The CLI integration test copies a source script, plans, applies, verifies and executes the installed copy.
