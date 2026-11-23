# lab314 installation, updates and recovery

## Policy and package ownership

**Lab314 is a continuously maintainable, modern Scientific Python environment for research, not a permanently frozen software distribution.**

New unified installations resolve Python 3.14, Scientific Python, Spyder and
its kernel in a single Conda-forge environment. The direct package list and
current OpenCV 5.1.0 Qt6, HDF5 1.14.6 and Spyder 6.1.8 targets are in
`config/lab314/requirements.json`. Conda selects compatible ARM64 builds
for `h5py`, `netCDF4` and their native libraries. Spyder declares the supported
range for `spyder-kernels`, which constrains IPython and ipykernel.

Older lab314 environments retain their original ownership. They use Conda for
Python and native dependencies and PyPI/piwheels for the scientific wheels.
When maintained with their legacy IDE workflow, the kernel constraint comes
from the external IDE. The unified installer keeps an existing valid prefix
and reports a missing integrated IDE as deferred. To migrate, create and test a
new integrated environment at a vacant prefix before replacing or retiring an
old environment through an explicit backup and recovery decision.

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

For ordinary installation, use the unified installer. It keeps valid existing
prefixes unless you explicitly request an update.

### Upgrade OpenCV 5.0.0 to 5.1.0

From `trixie/base/install`, preview the transaction, then run the same command
without `--plan` to review and approve it.

```sh
sudo bash setup-rpi.sh --manage --action update --component lab314 --package opencv --plan
sudo bash setup-rpi.sh --manage --action update --component lab314 --package opencv
```

The plan lists every package to be replaced, including an HDF5 downgrade and any
build changes for `h5py` and `netCDF4`. If the package plan changes after approval,
the installer stops before applying it. Verification checks OpenCV 5.1.0 and
Qt6, reads and writes HDF5 and NetCDF files, and checks the Spyder kernel.
The lifecycle record keeps the resulting versions. The update is limited to
`/opt/lab314`.

Before updating an environment that has written files with HDF5 2.2's latest
format, retain an external backup and check representative files read-only with
HDF5 1.14.6. Some newer-format files may require the newer runtime for reading.

### Other maintenance

For direct component maintenance, rerunning `create_lab314_env.sh` updates an
existing environment to the latest compatible packages. A current environment completes without
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
Spyder compatibility, imports, isolation, GUI-capable OpenCV and `pip check`.
The native layout also checks an offscreen HighGUI window, Qt/PyQtWebEngine
loading and an actual IPython kernel. The existing scientific/geometry/file/video
functional checks remain. Legacy wheel builds retain their font checks.
The new update command runs normal functional verification after applying an
update. Display/Spyder GUI interaction still needs the existing manual acceptance.

### 16 KiB kernel verification

Raspberry Pi 5 uses 16 KiB pages with its default kernel. On a Debian ARM64
16 KiB QEMU guest, the original detached Jupyter client reported the kernel had
died while the process was still running. The updated check uses Jupyter's local
kernel manager to check process liveness directly. It captures the kernel's
stderr, stdout and return code or terminating signal on failure.

The allocator warning was reproduced independently on the same guest by
importing PyArrow with Conda-forge `libarrow` build `26.0.1-hb5aa228_8_cpu`.
That library embeds a private jemalloc. PyArrow successfully allocated memory
with its default mimalloc and with `ARROW_DEFAULT_MEMORY_POOL=system`.
The private jemalloc message can still appear when the library loads. On large-page
ARM64, verification uses the system pool if Arrow would otherwise use jemalloc.
For scripts that explicitly select jemalloc, use the system pool instead.
Apache Arrow's separate PyPI `26.0.1` wheel for CPython 3.14 and manylinux
AArch64 also allocated successfully on 16 KiB pages. That wheel exposes mimalloc
and the system pool. Keep the Conda packages in the existing lab314 installation.

Run the read-only kernel diagnostic on the existing prefix:

```sh
/opt/lab314/bin/python -IB check_lab314.py --prefix /opt/lab314 --kernel-only
```

To run the native regression on a 16 KiB ARM64 host or guest, use the target
Python from the repository root:

```sh
LAB314_ARM64_16K_PREFIX=/opt/lab314 /opt/lab314/bin/python -B -m unittest discover \
  -s trixie/base/tests -p test_lab314_kernel.py -v
```

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

The normal Raspberry Pi installer rerun keeps installed scientific package
versions. Use `sudo bash setup-rpi.sh --manage` and **Update All** for routine
package maintenance. For targeted requests, the existing
forward dependency closure may change. Other installed packages contribute
only their declared dependency ranges to the temporary pip constraints. Their
installed versions are not frozen. For example, an installed reverse-dependent
Numba requirement may constrain a NumPy-only update; select both packages or
review a full update in the maintenance interface. A full update removes
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

For a current integrated lab314, use the normal Conda-owned update route.
For example, `create_lab314_env.sh --package spyder --plan` previews changes
to the IDE and its dependencies in that environment.

### Legacy external IDE maintenance

Older mixed Conda/pip environments can maintain a separate, administrator-chosen
IDE prefix. Existing APT or external IDE installations retain their own
lifecycle.

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
