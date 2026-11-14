# Lab314 rolling maintenance correction

## Cause and resulting behavior

The November 2026 acceptance snapshot had become the default installer input
and the normal verification contract. Exact equality rejected valid updates,
and the existing-prefix KEEP branch did not provide normal maintenance.
That mixed reproducibility with the long-term dependency policy.

The existing `create_lab314_env.sh` now creates a missing environment using
current compatible dependencies, or updates an existing one when explicitly
rerun. It does not recreate an existing prefix. Already-current packages are
not reinstalled. `--package REQUIREMENT` selects a targeted operation and
`--plan` previews an existing prefix. `--snapshot` is an explicit, separate
historical reproduction mode and does not silently downgrade an existing prefix.
HOME/AALTO continue to call the same installer with the same ordering.

The authoritative `requirements.json` describes 36 intended pip distributions
and imports plus Conda Python 3.14, pip and packaging. The scientific libraries
are not permanently pinned to current versions. Direct requirements come from
the existing product package selection and functional workloads, not all 145
historical distribution records. Ordinary transitive requirements remain the
package managers' responsibility. No guessed minimum versions were introduced.

Python's 3.14 series and the actual selected Spyder IDE's kernel range are the
technical compatibility constraints. Current APT Spyder 6.0.5 declares
`spyder-kernels>=3.0.3,<3.1.0`; the newer IDE 6.1.8 requires
`spyder-kernels>=3.1.0,<3.2.0`. Neither IDE/kernel version is hardcoded as a
permanent target. IPython/ipykernel constraints follow kernel metadata.
The GUI `opencv-python` distribution is preserved; alternate headless/contrib
distributions are rejected. The existing functional workloads remain useful.

The original four snapshot files, including SHA256SUMS, are byte-identical.
Normal verification checks requirements, imports, isolation, GUI capability,
fonts and pip consistency instead of the exact historical version list.
Snapshot verification retains exact Python/distribution/OpenCV checks.
No exact scientific version pins remain in the normal policy. Per-operation
resolved versions/builds and temporary Conda-ownership constraints do not become
permanent dependency requirements or a regenerated snapshot.

## Implemented maintenance operations

1. **Spyder IDE and matching kernel:** `--ide-prefix` creates or updates a
   separate, administrator-chosen, wholly Conda-managed IDE prefix. It does not
   touch lab314 packages. Launch `bin/spyder` directly; APT Spyder remains a
   fallback. Select that IDE's Python for a targeted kernel update. An explicitly
   selected interpreter is saved after successful apply in `.lab314-ide.json`,
   so later normal reruns do not accidentally revert compatibility to APT.
2. **Selected scientific libraries/security fixes:** `--package` selects known
   pip/Conda ownership automatically. pip plans use only-if-needed dependency
   handling. Unselected installed dependents contribute their declared ranges,
   not exact installed versions. Selected forward dependencies may change.
   Ownership conflicts fail before linking. Security version requirements do
   not require regeneration of the 145-distribution snapshot.
3. **Whole scientific environment:** a plain installer rerun, or explicit helper
   `--all`, requests current compatible versions of all installed scientific
   packages and any missing maintained direct requirements. Conda's full-update
   request is restricted to this operation. Scientific packages are independently
   maintainable rather than frozen by a Spyder-only update rule.

The lifecycle helper shares planning/verification with the existing installer;
it is not an application wrapper, separate scientific installation architecture
or unattended updater. The small policy module prevents duplicated dependency
and ownership definitions. It does not create or change `/opt/rpi`, base Conda,
Scientific Imaging application paths, shell startup files or application code.

Conda file ownership takes precedence over INSTALLER labels. pip cannot replace
Conda distributions. New Conda dependencies are downloaded into a temporary
cache and their file manifests are inspected for pip collisions, including
name aliases/noarch paths. Reviewed versions/builds are applied without a new
dependency solve. Package removals without replacement and explicit ownership
migrations are conservatively rejected for separate review. This can block
unusual package-layout migrations; it does not promise universal mixed-manager
transaction support. Full updates remain subject to real dependency compatibility.

Updates are not transactional. Before applying, stop consumers and take a full
external prefix backup. Saved plans/metadata are diagnostics, not a full backup.
Failure does not imply automatic rollback or snapshot restoration. Restore a
backup into the original absolute prefix after preserving the failed one.
Missing Qt font links are repaired; existing font/configuration files are retained.

## Verification performed

- **41 focused tests PASS:** installer normal/snapshot branching, existing-prefix
  maintenance, Python-series and kernel incompatibility, updated scientific
  version acceptance, snapshot deviation detection, selected pip and Conda
  operations, reverse-dependent ranges, Conda file ownership and collisions,
  security-update plan/apply/verify, current-package no-op, separate IDE operation,
  persisted IDE selection and explicit full scientific updates. Existing focused
  lab314/activation tests were included; the 103-test scientific suite was not run.
- The Spyder acceptance scenario changes 6.0.5 metadata to 6.1.8 metadata,
  accepts kernel 3.1.7 and rejects both the old incompatible kernel and 3.2.0.
  The targeted kernel application does not request NumPy/SciPy/OpenCV updates.
- A real **Trixie ARM64 Conda dry-run** resolved Spyder 6.1.8, kernel 3.1.7,
  Python 3.14.10, Qt 5.15.15 and PyQt/PyQtWebEngine 5.15.11 from conda-forge,
  with 318 LINK actions. These observations are not installation pins. Metadata
  was kept in an automatically removed `/dev/shm` directory. No IDE was installed.
- Current APT metadata was read: its Spyder candidate remains 6.0.5+ds-6. The
  approved external IDE option removes that distribution ceiling.
- Python/Bash/JSON syntax, snapshot-byte preservation, public documentation
  links/anchors and `git diff --check` were checked separately.

Package-operation tests use isolated temporary fixtures and mocks. No real pip
or Conda update was applied to a production prefix. No complete scientific
environment was reinstalled. The new IDE GUI and a fresh rolling installation
remain NOT RUN, in accordance with the development restrictions.

## Files and scope

Changed: `create_lab314_env.sh`, `verify_rpi_lab314.sh`, `check_lab314.py`, focused
installer tests, public README/Spyder guidance and the historical finalization
report's policy banner. Added: `requirements.json`, `lab314_policy.py`,
`update_lab314.py`, focused rolling tests, this report and the maintenance guide.
The [guide](lab314-maintenance.md) contains the concrete normal, selected pip,
Conda, security, full-environment, independent IDE and recovery commands.

Commit `c6e9667`, the index, MIT LICENSE draft, excluded local development
reports and unrelated work are preserved. No files were staged, committed or
pushed. The existing production environments and APT installation remain
unchanged. There are no new public card-size or disk-imaging requirements.

The user explicitly approved the separate external IDE environment support.
The administrator selects its path; no new fixed application prefix or wrapper
was introduced. Other agreed paths/environment boundaries remain unchanged.

## Publication status

Rolling maintenance and optional snapshots are implemented and covered by the
focused checks above. Actual package/IDE GUI acceptance follows an explicitly
authorized installation, not an unperformed development deployment. Independent
of this policy correction, the preserved MIT draft still contains an unconfirmed
copyright-holder field. That approval remains necessary before final licensing
and GitHub release; it is not silently resolved by these package tests.
