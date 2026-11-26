# Optional Wolfram Engine and Mathematica

The unified installer selects Wolfram on AALTO and offers it as an optional
component on GENERAL and HOME. Use Customize or `--no-wolfram` to skip it.

## Disk space and license

The plan reads the APT candidate's `Size` and `Installed-Size`. The AALTO
sample package `15.0.1+202608182322` on arm64 required about 2.17 GB to
download and 5.44 GB after installation. Setup checks the download and unpack
space on the relevant filesystems. The Raspberry Pi package can report
`Installed-Size` as fractional KiB. Setup converts it to bytes and rounds up
when needed. The estimates cover the Wolfram package.
APT also checks the overall transaction and its dependencies.

Wolfram's Raspberry Pi bundle terms limit use to personal or educational
purposes and exclude commercial use. Review the terms and the organization's
license before adding Wolfram to a shared workstation. Installing the bundle
signifies acceptance. Interactive setup asks the administrator to approve the
displayed package. It asks again if refreshed APT metadata identifies a
different candidate. Noninteractive use of `--yes` also needs the operator's
explicit `--accept-wolfram-license` for the reviewed Wolfram candidate.
[Wolfram Raspberry Pi Bundle License Agreement](https://www.wolfram.com/legal/agreements/wolfram-mathematica-raspberry-pi/)

## Desktop and terminal commands

| Component | Desktop or terminal entry |
|---|---|
| Mathematica notebook interface | **Wolfram Mathematica (GUI)**. The AALTO sample used `mathematica`. |
| Interactive Wolfram kernel | **Wolfram Language (CLI)**, opens in a terminal. The sample used `wolfram`. |
| WolframScript | `wolframscript` for noninteractive scripts and command-line evaluation. |

Setup reads the installed package's desktop entries and writes managed overrides
with the same desktop IDs under `/usr/local/share/applications`. The chosen
entries keep their vendor icons and an education or science category. Additional
package entries and separately named Raspberry Pi menu entries that invoke
the same commands are hidden by ID. If the package supplies a WolframScript
menu entry, it is hidden and `wolframscript` remains available in the terminal.
The overrides live outside
APT's files. After an APT change that introduces new launcher IDs, run the
installer's update or repair to reconcile them. Local desktop overrides or edits
are preserved and may require review.
[Raspberry Pi desktop search path](https://github.com/raspberrypi-ui/raspberrypi-ui-mods/blob/master/usr/bin/setup_env)

The installer checks the executables and desktop definitions. On new installs
it attempts short local CLI and WolframScript calculations and reports the result
of each. Launch both menu entries as the desktop user for functional acceptance.
Evaluate `2+2` in the CLI and run this in a Mathematica notebook:

```mathematica
Plot[Sin[x], {x, 0, 2 Pi}]
```

Test WolframScript separately with `wolframscript -code '2+2'` if its automatic
calculation was limited. The expected result is `4`.

## Maintenance

Run these from the repository's `trixie/base/install` directory.

```bash
bash install_optional_wolfram.sh --dry-run
sudo bash install_optional_wolfram.sh
sudo bash setup-rpi.sh --manage --action verify --component wolfram
sudo bash setup-rpi.sh --manage --action repair --component wolfram --plan
sudo bash setup-rpi.sh --manage --action update --component wolfram --plan
sudo bash uninstall_optional_wolfram.sh --dry-run
sudo bash uninstall_optional_wolfram.sh
```

Apply a reviewed repair or update by omitting `--plan`. The removal command
uses the unified journal to restore installer-owned desktop overrides and remove
the APT package when its installer ownership and current version are known.
It preserves notebooks, user configuration and local desktop files.
