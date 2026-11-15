# Offline rpi-share catalogs and reversible CSV/JSON interchange

`rpi-share` remains the network-share client. `rpi-share-builder.py` supplies
offline validation and **both** CSV→JSON import and JSON→CSV export, using system
Python's standard library. `rpi_share_catalog.py` is shared by the client and the
builder. Neither catalog generation nor navigation contacts a server, mounts a
share, authenticates, scans a directory or queries an ACL.

## Install and choose configuration

```sh
cd trixie/base/install
sudo bash install_rpi_share.sh
# Or preview the software installation only:
bash install_rpi_share.sh --plan
```

The installer installs the client, builder, shared module and generic examples.
It does not choose a production catalog or overwrite user/site configuration.
User-specific configuration is selected by the [unified installer](unified-setup.md)
or maintained directly by its owner.

Runtime precedence, in order:

1. An explicit `--config FILE`; a missing explicit file is an error.
2. `./rpi-share.json` in the current directory.
3. `~/.config/rpi-share.json` for the invoking runtime user.
4. `/etc/rpi-share/rpi-share.json`, if present.
5. `rpi-share.json` next to the client script.

This preserves the earlier current-directory and per-user priority. The new
system fallback comes before the old script-directory fallback. An existing
script-local setup continues unchanged while no system file exists; administrators
introducing a system catalog should use `--config` where that old fallback must
remain selected. Run ordinary network access as the researcher, not through sudo.

Actual site CSV/JSON inventories may live in `/etc/rpi-share/` or a user's own
configuration directory and remain outside Git. Existing public
`config/rpi-share.home.json` and `rpi-share.aalto.json` are retained unchanged.

## Export, edit and regenerate

```sh
python3 ../bin/rpi-share-builder.py --json ../config/rpi-share.home.json \
  --output /absolute/local/rpi-share.home.csv
python3 ../bin/rpi-share-builder.py --csv /absolute/local/rpi-share.home.csv \
  --output /absolute/local/rpi-share.home.roundtrip.json

python3 ../bin/rpi-share-builder.py --json ../config/rpi-share.aalto.json \
  --output /absolute/local/rpi-share.aalto.csv
python3 ../bin/rpi-share-builder.py --csv /absolute/local/rpi-share.aalto.csv \
  --output /absolute/local/rpi-share.aalto.roundtrip.json

# Preview output without a filesystem change:
python3 ../bin/rpi-share-builder.py --csv /absolute/local/shares.csv --plan
# Validate only:
python3 ../bin/rpi-share-builder.py --json /absolute/local/rpi-share.json --validate
# Explicit replacement after review:
python3 ../bin/rpi-share-builder.py --csv /absolute/local/shares.csv \
  --output /absolute/local/rpi-share.json --force
```

Output parents must exist. Existing output is refused unless `--force` is given.
All parsing/validation completes before publication. A sibling temporary file is
flushed and atomically published with mode 0600. Default publication is
no-clobber, including concurrent creation; explicit replacement is atomic.
Generation failure retains the existing configuration. Symlinked output is
refused. No persistent credential storage is introduced.

Without an explicit override, import/export changes no configuration values and
adds no defaults. `--default-group staff` deliberately overrides that one value.
Whitespace and JSON object key order may change; values and JSON types do not.
HOME's string version `"1.0"` and AALTO's numeric version `1` remain distinct.
Unknown optional fields are preserved rather than silently discarded. Unsupported
credential-bearing fields/options produce an explicit validation error.

## CSV schema: two stable columns

CSV has exactly two columns, `path` and `json_value`. Each row represents one JSON
value. `path` is a JSON Pointer: `/` inside a key is escaped as `~1`, and `~` as
`~0`. The empty path represents the root. `json_value` is a complete JSON literal,
so strings retain their JSON quotation marks, numbers remain numbers, and null,
boolean, array and object values remain distinguishable.

Container rows use `{}` or `[]`; descendant rows provide their members. A
container without descendant rows is genuinely empty. Array paths use contiguous
zero-based indices. Row order is irrelevant on import. Duplicate pointers, missing
parents, invalid escapes, conflicting parent values and noncontiguous arrays are
rejected. JSON duplicate keys and non-finite numbers are also rejected. The
implementation bounds practical hierarchy depth to 128 and CSV size to 100,000
values.

Examples as displayed in Calc cells (CSV quoting is handled by the exporter):

| path | json_value |
|---|---|
| *(empty)* | `{}` |
| `/version` | `2` |
| `/defaults` | `{}` |
| `/defaults/group` | `"staff"` |
| `/defaults/gateway` | `"staff-gw"` |
| `/defaults/share` | `"measurements"` |
| `/shares/measurements/name` | `"Measurements — µm"` |
| `/shares/measurements/paths/staff-gw` | `"/srv/example/Project X/Measurements"` |
| `/optional/empty` | `""` |
| `/optional/nullable` | `null` |

Use the complete generic `config/rpi-share.example.csv` as a starting point;
the abbreviated table above omits required parent rows and other definitions.
Exporting an existing JSON is usually the easiest way to create a complete CSV.
Commas, semicolons, quotation marks, newlines and Unicode are encoded using
standard CSV quoting and JSON string escaping. Values are not encoded as lossy
comma/semicolon lists: groups and paths remain actual JSON arrays/objects.

## LibreOffice Calc

On opening the CSV, use UTF-8, separator comma, text delimiter `"`, and select
**both columns as Text** in the import preview. Disable special-number/scientific
number detection and formula interpretation. Preserve the JSON quotation marks
inside string-value cells. For example, edit `"00123"` as quoted JSON text;
`00123` is not a valid JSON number, and `123` would intentionally mean a number.

Both columns must remain Text to retain large integers and numeric literals such
as `1.0` exactly. Do not let Calc auto-detect dates/numbers and then expect a CSV
export to recover the earlier value. Save as UTF-8 CSV with standard double-quote
escaping. Comma, semicolon or tab delimiters and an optional BOM are accepted.
Keep the column names unchanged and keep the empty-path root row.

The automated local Calc acceptance imports both columns as Text, converts to
ODS, exports CSV, and performs recursive type-aware JSON comparison. It covers
both original configurations and additional Unicode, large-integer, float,
boolean, null, empty-string and quotation cases. GUI interaction is a separate
user workflow. See the official [CSV filter parameters](https://help.libreoffice.org/latest/en-US/text/shared/guide/csv_params.html)
and [Text Import controls](https://help.libreoffice.org/latest/en-US/text/shared/00/00000208.html).

## JSON version 2 and hierarchy

Version 1 remains accepted, including string version `"1.0"`. Its existing fields
are retained without migration. Version 2 uses the same `gateways`, `shares` and
`paths` mechanisms and adds:

- `nodes`: navigation-only categories, keyed by unique identifiers.
- `parent`: category/destination parent, or absent/null for a root.
- `name`: optional friendly label.
- `groups`: an array of navigation labels on a category/destination.
- top-level `groups`: administrator-defined group metadata.
- `defaults.group` and `defaults.additional_groups`: primary and additional
  default navigation labels.

Built-in navigation labels are `all`, `staff` and `students`. Custom examples
include `research-a` and `project-x`. Identifier syntax is letters/digits followed
by letters/digits/underscore/dot/hyphen, excluding `.` and `..`. Node and share IDs
must be distinct. Parent references and cycles are checked locally. A parent may
be a category or another destination; hierarchy does not imply path concatenation.
Every actual remote path is supplied explicitly. Multiple navigation groups use
union semantics. No `groups` field means visible in every navigation view; `all`
selects unfiltered navigation. `allowed_groups` remains audience metadata, not a
local authorization mechanism.

The public generic JSON/CSV examples include multiple gateways, staff/students,
custom/multiple groups, a deep SSHFS destination with different gateway paths,
CIFS subdirectories, SMB browse and an explicit-only maintenance destination.
`rpi-share.schema.json` documents the general shape; Python validation additionally
checks references, hierarchy, paths and credential restrictions.

```sh
rpi-share --config /etc/rpi-share/rpi-share.json --tree
rpi-share --config /etc/rpi-share/rpi-share.json --tree --group students
rpi-share --config /etc/rpi-share/rpi-share.json --tree --group staff --group research-a
rpi-share --config /etc/rpi-share/rpi-share.json --tree-all
rpi-share --config /etc/rpi-share/rpi-share.json -g staff-gw -s measurements -u researcher
```

`--tree-all` shows every configured node, including explicit-only destinations
marked as such. It makes no connection. Group-filtered trees retain context for
visible children whose parent is filtered. Categories are not mount targets.
Version-2 interactive selection offers the same direct deep destinations without
mounting their parents. `--list`, `--all` and `--admin` preserve their existing
explicit-only behavior: `--all` expands listing; `--admin` also expands guided
selection. An explicit `-g/-s` selection is not an authorization bypass: it merely
requests a real connection through the existing backend.

## Backend paths and authorization boundaries

SSHFS receives the selected absolute remote directory as one argument, preserving
spaces. `paths` may define a different directory for each gateway. Missing gateway
paths are reported rather than invented. CIFS separates `//host/share` from a
relative subdirectory using `prefixpath`; an administrator may supply either a
deep `remote_path` or `share_root` plus `subdir`. Traversal and option-delimiter
injection are rejected. See the [Samba mount.cifs documentation](https://www.samba.org/samba/docs/3.5/man-html/mount.cifs.8.html)
for the share-root/subdirectory distinction. Browse targets use SMB URLs;
derived URLs percent-encode path components.

There are three independent layers:

1. The local catalog and navigation groups describe destinations and display
   preferences. A visible directory is not necessarily accessible.
2. The gateway authenticates the authorized person's remote identity and decides
   whether that identity may log in. Choosing `staff` locally grants no status.
3. The remote filesystem applies its own permissions and ACLs after login.

A local Pi account is not assumed to possess remote Aalto access.
Researchers authenticate using their own authorized credentials. The builder
never verifies remote existence, authentication or ACL behavior. Runtime failures
report tool diagnostics without inventing an authentication/ACL diagnosis when
the underlying tool does not distinguish it.

The existing SSHFS/CIFS lifecycle is retained. CIFS passwords are read securely
from a terminal, never passed in argv/environment, and written only to a mode-0600
temporary credential file. It is deleted after mounting or by failure/signal
cleanup. Shell tracing is refused before credential input. No CSV/JSON password,
token, key or persistent credential file is supported. Existing safe unmount,
busy-mount handling, cleanup and mount ownership remain in the single client.
