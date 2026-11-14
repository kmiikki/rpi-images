# lab314 installation, updates and recovery

## Policy and package ownership

**Lab314 is a continuously maintainable, modern Scientific Python environment for research, not a permanently frozen software distribution.**

Normal installation is **rolling by default**. The authoritative editable
specification is `config/lab314/requirements.json`. It lists the intended
scientific, imaging, measurement and development tools, not every transitive
dependency from one installation. Requirements come from the existing product
package list and the workloads in `check_lab314.py`. Ordinary dependencies are
resolved by Conda and pip. No invented numerical minimums or permanent exact
pins have been added for these libraries.

Python stays in the **3.14 series**; maintenance releases are allowed. A new
minor series requires separate compatibility validation. Conda manages Python,
pip, packaging and their native dependencies. Scientific distributions are
installed as binary wheels using the existing `opencv-python` distribution
and the PyPI/piwheels sources. Headless/contrib OpenCV replacements are rejected;
normal verification checks a Linux GUI backend and retains the image/video tests.

The separate Spyder IDE is not installed inside lab314. Its declared
`spyder-kernels` requirement is read from the IDE's own interpreter metadata.
The fallback APT IDE is read with `/usr/bin/python3`. An administrator-selected
external IDE is read with its own Python; its extension modules
are never loaded into lab314. Kernel dependencies, including compatible IPython
and ipykernel ranges, are left to the kernel's own package metadata and pip check.
No IDE version, kernel version or IPython version is permanently pinned here.

The November 2026 inputs (`conda-linux-aarch64.txt`, `wheels.txt`, `packages.json`,
`SHA256SUMS`) are **historical snapshot inputs**, retained without modification.
They are not normal requirements. They describe 23 Conda artifacts and 144
wheels, exposing 145 Python distributions; pip is Conda-owned in that snapshot.
Normal verification no longer requires those exact 145 versions. Snapshot
verification still does. A restored historical kernel may require the matching
historical IDE; exact snapshot verification deliberately does not rewrite it
to match a newer selected IDE.

## Installation and verification

From `trixie/base/install`, on a new or already compatible prefix:

```sh
sudo bash create_lab314_env.sh
bash verify_rpi_lab314.sh
```

The HOME/AALTO entry points use this default without changed ordering or flags.
**Rerunning the same normal installation script updates an existing environment**
to the latest compatible packages. A current environment completes without
reinstalling its packages. Neither case recreates the prefix or resets user
configuration. No OS upgrade or unattended action is part of this command.
An incomplete or incorrectly selected prefix is rejected without replacement.
Take the external backup described below before rerunning an existing environment.
Small operation records are retained in a `.lab314-update.*` directory next to
the target prefix; temporary caches are removed. If an update fails, the records
remain for diagnosis. This is not an automatic transactional rollback.

The same installer supports targeted maintenance, without a separate normal
update workflow:

```sh
sudo bash create_lab314_env.sh --package numpy --package scipy
# Preview an existing environment's full update without applying it:
bash create_lab314_env.sh --plan
```

Internally these operations reuse `update_lab314.py` for dependency plans,
ownership protection and verification. That helper is also exposed below for
explicit plans, security version requirements and independent IDE maintenance.

To reproduce the old accepted set in a **new vacant prefix**, explicitly select:

```sh
sudo bash create_lab314_env.sh --snapshot --prefix /absolute/new/lab314-snapshot
bash verify_rpi_lab314.sh --snapshot --prefix /absolute/new/lab314-snapshot
```

Snapshot installation verifies the shipped SHA256SUMS, uses the explicit Conda
artifact hashes and pip `--require-hashes --no-deps`, and runs the original exact
contract checks. Merely running the normal installer never restores this snapshot.
A snapshot can contain historical vulnerable versions; select it deliberately
for reproduction/recovery, not as the default response to a security advisory.

Normal verification checks Python series, required distributions, dynamic
Spyder compatibility, imports, isolation, GUI-capable OpenCV, fonts and `pip
check`. The existing scientific/geometry/file/video functional checks remain.
The new update command runs normal functional verification after applying an
update. Display/Spyder GUI interaction still needs the existing manual acceptance.

## Identify ownership, then update a selected package

Run the updater with the **target lab314 Python**, not system Python or base:

```sh
/opt/conda/bin/conda list -p /opt/lab314
/opt/lab314/bin/python -m pip show urllib3
```

Conda metadata is authoritative. The updater checks actual Conda file ownership,
not just pip's listing (pip also lists Conda-installed Python distributions).
It refuses unknown ownership. Conda-owned Python distributions are frozen only
as temporary pip-solver constraints to prevent pip replacing Conda files; these
are not permanent dependency-policy pins.

Plan a pip-owned package update and then explicitly apply it:

```sh
/opt/lab314/bin/python -IB update_lab314.py --package urllib3
sudo /opt/lab314/bin/python -IB update_lab314.py --package urllib3 \
    --apply --record-dir /absolute/new/update-records
```

Set `--record-dir` to a new directory outside the environment whose parent exists.
The apply examples require a backup as explained below. `--package` may be
repeated for a selected set, e.g. NumPy and SciPy. The default pip strategy is
`only-if-needed`: selected packages and required dependency changes, not an
unrestricted upgrade of the environment. `--no-deps` offers a package-only pip
operation, followed by the same consistency verification; it is not appropriate
if the fixed release requires new dependencies.

For the snapshot's **Conda-owned pip**, use the same ownership-aware command:

```sh
/opt/lab314/bin/python -IB update_lab314.py --package pip
sudo /opt/lab314/bin/python -IB update_lab314.py --package pip \
    --apply --record-dir /absolute/new/pip-update-records
```

This invokes Conda for pip, not `python -m pip install --upgrade pip`. Conda uses
`--freeze-installed` plus the Python-series constraint. If a dependency also
needs updating, name that existing Conda package explicitly as another
`--package`. The solver may reject the request rather than change frozen
unrelated packages. New Conda dependencies are allowed only after downloading their file manifests
into a temporary cache and rejecting collisions with pip-owned files, including
Conda/PyPI name aliases. A plan crossing an ownership boundary is rejected,
rather than silently converting an installed pip distribution to Conda ownership.
Conda package removals without replacement are rejected as well.

The reviewed plans are applied using the selected exact versions (and Conda
builds), with dependency resolution disabled at apply time to avoid a second
unreviewed solve. These are temporary operation plans, not regenerated snapshot
locks. State records and the plans are saved before changes. Updates are **not
transactional** and verification failure does not automatically restore files.

Only an explicit `--all` requests the whole environment:

```sh
/opt/lab314/bin/python -IB update_lab314.py --all
sudo /opt/lab314/bin/python -IB update_lab314.py --all \
    --apply --record-dir /absolute/new/full-update-records
```

The normal installer's rerun requests this complete update explicitly; it is
not a targeted Spyder-only operation. For targeted requests, the existing
forward dependency closure may change. Other installed packages contribute
only their declared dependency ranges to the temporary pip constraints. Their
installed versions are not frozen. For example, an installed reverse-dependent
Numba requirement may constrain a NumPy-only update; select both packages or
rerun the installer for a full compatible resolution. A full update removes
those old pip-side constraints because all pip-managed packages are selected.

There are no unattended updates and no operations against `/opt/rpi`, the base
Conda prefix or the Scientific Imaging application installation.

## Security update scenario

Identify the affected installed version and its manager first. Set
`FIXED_VERSION` from the actual advisory; the example does not assert a specific
release is a security fix:

```sh
/opt/lab314/bin/python -m pip show urllib3
/opt/lab314/bin/python -IB update_lab314.py --package "urllib3>=${FIXED_VERSION}"
sudo /opt/lab314/bin/python -IB update_lab314.py \
    --package "urllib3>=${FIXED_VERSION}" --apply \
    --record-dir /absolute/new/security-update-records
```

For a Conda-owned package, the same command selects Conda automatically; include
required existing Conda dependencies explicitly if the frozen solve needs them.
Incompatibility fails clearly rather than silently relaxing Python/Spyder
requirements. Neither the update nor subsequent normal verification requires
rewriting the 145-distribution historical snapshot. For a lasting advisory rule,
record the technically justified minimum requirement as a key in the maintained
pip requirement mapping (with its import name as the value), documenting the
advisory. This is a small policy edit, not a transitive snapshot regeneration.
New normal installs resolve
current compatible versions rather than forcing the old snapshot.

## Spyder IDE and kernel maintenance

The IDE and scientific environment have separate update lifecycles. The
current APT candidate is only 6.0.5; it is not a permanent IDE ceiling.
The approved alternative uses the existing Conda infrastructure to manage a
**separate, administrator-chosen** IDE prefix from conda-forge. No IDE is
installed inside lab314 or `/opt/rpi`, and the APT IDE is retained as a fallback.

```sh
IDE_PREFIX=/absolute/administrator/chosen/spyder-ide
/usr/bin/python3 update_lab314.py --ide-prefix "$IDE_PREFIX"
sudo /usr/bin/python3 update_lab314.py --ide-prefix "$IDE_PREFIX" \
    --apply --record-dir /absolute/new/ide-install-records
# Launch the actual application directly, without a wrapper:
"$IDE_PREFIX/bin/spyder"
```

The command creates a missing IDE prefix or updates an existing wholly
Conda-managed IDE to the latest stable compatible release offered by the chosen
conda-forge channel. The selected channel must carry the desired stable release;
there is no hardcoded IDE or Python version in this IDE request. Existing
pip-modified IDE environments are rejected for separate ownership review.
Do not use the scientific environment's --all to update this IDE.

Rerun the same `--ide-prefix` operation for future IDE updates. Its dependency
changes remain inside that IDE prefix. The existing APT IDE can still be
maintained independently with its original APT method when an appropriate
candidate is available; no APT upgrades were performed during development.

Explicitly choose the IDE interpreter for kernel compatibility, then update only
the kernel and its required dependencies:

```sh
export LAB314_SPYDER_PYTHON="$IDE_PREFIX/bin/python"
/opt/lab314/bin/python -IB update_lab314.py --package spyder-kernels
sudo env LAB314_SPYDER_PYTHON="$LAB314_SPYDER_PYTHON" \
    /opt/lab314/bin/python -IB update_lab314.py --package spyder-kernels \
    --apply --record-dir /absolute/new/spyder-kernel-update-records
# Or use the same scientific installer for that targeted operation:
sudo env LAB314_SPYDER_PYTHON="$LAB314_SPYDER_PYTHON" \
    bash create_lab314_env.sh --package spyder-kernels
```

A successful apply saves an explicitly selected IDE interpreter in the target's
`.lab314-ide.json` maintenance record. Later ordinary installer runs and normal
verification read that choice and the IDE's current metadata. An explicit
`LAB314_SPYDER_PYTHON` overrides it; with neither a saved choice nor an override,
APT `/usr/bin/python3` is the fallback. Selecting that fallback explicitly is
an administrator decision, not a silent downgrade. No personal shell startup
files, global PATH or existing application paths are rewritten.

The acceptance scenario changes IDE metadata from Spyder 6.0.5's
`spyder-kernels>=3.0.3,<3.1.0` to Spyder 6.1.8's
`spyder-kernels>=3.1.0,<3.2.0`. Kernel 3.1.7 is accepted under the latter;
3.0.5 is rejected there, and 3.2.0 is also rejected. These are test examples,
not installation pins. Required kernel dependencies may change; unrelated
NumPy/SciPy/OpenCV upgrades are not requested. No environment rebuild, freezing
of the whole stack or snapshot relocking is needed.

**ARM64 verification:** a real Conda dry-run on Trixie ARM64 resolved Spyder
6.1.8, spyder-kernels 3.1.7, Python 3.14.10, Qt 5.15.15, PyQt and PyQtWebEngine
5.15.11 from conda-forge (318 package links). These are observed solve results,
not permanent pins. Only temporary metadata was downloaded into `/dev/shm`,
and it was cleaned. No IDE was installed and no new IDE GUI acceptance is
claimed. The three distinct maintenance operations are covered by isolated tests.

## Recovery

Before applying updates, close Spyder kernels, recording jobs and other users
of the prefix. Take a complete backup to an administrator-selected location
outside it, preserving permissions, symlinks and extended attributes. For example:

```sh
sudo tar --acls --xattrs --numeric-owner -cpf /absolute/backup/lab314-before.tar \
    -C /opt lab314
```

The updater's JSON/explicit/freeze records are diagnostics, **not** a full backup
or a guaranteed pip rollback recipe. If an update fails, stop consumers, preserve
the failed prefix, and restore the complete archive into the vacant **original
absolute prefix** `/opt/lab314`. Verify it before restarting users. Do not treat
a renamed Conda environment as relocatable. Conda revision rollback alone does
not undo pip changes. Do not overwrite working or failed prefixes blindly.
An optional snapshot rebuild is a separate deliberate recovery choice, not an
automatic fallback. Old backups and historical reports are retained.

## Scope and references

No production environment or IDE was updated during development. Tests use
isolated fixtures and mocked package-manager operations; no full environment
reinstallation or scientific hardware regression was run.

The package-manager behavior used here is documented by
[pip install](https://pip.pypa.io/en/stable/cli/pip_install/) and
[Conda install](https://docs.conda.io/projects/conda/en/stable/commands/install.html).
Spyder's [installation guide](https://docs.spyder-ide.org/current/installation.html)
describes separate IDE and external-kernel environments.
