# Locale and Wolfram repair on an existing tr3 R2 installation

Apply this to the completed R2 installation. The locale repair uses the
existing journal. The optional Wolfram installer retries only Wolfram and
reconciles its desktop launchers.

## Copy the corrected installer files

Run this on the development machine. This example assumes the extracted R2
tree is `~/rpi-images-main` on tr3. Adjust the destination if you extracted
it elsewhere.

```bash
tar -C /home/kim/projects/rpi-images -cf - \
  trixie/base/bin/rpi-keyboard \
  trixie/base/install/setup_rpi.py \
  trixie/base/install/lifecycle.py \
  trixie/base/install/locale_setup.py \
  trixie/base/install/wolfram.py |
  ssh kim@tr3 'cd "$HOME/rpi-images-main" && tar -xf -'
```

## Repair locales and retry Wolfram

Run on tr3 in the same R2 tree. The first command shows which locales require
generation. The second uses the installer’s normal maintenance approval.

```bash
cd ~/rpi-images-main/trixie/base/install
sudo bash setup-rpi.sh --manage --action repair --component locales --plan
sudo bash setup-rpi.sh --manage --action repair --component locales
sudo bash setup-rpi.sh --manage --action verify --component locales
bash install_optional_wolfram.sh --dry-run
sudo bash install_optional_wolfram.sh
sudo bash setup-rpi.sh --manage --action verify --component wolfram
```

The Wolfram preview for the candidate observed on tr3 should report roughly
2.17 GB download and 5.44 GB installed. Review the available disk space
and linked license terms before approving. APT may offer a different version
after refreshing its lists. Review that candidate if asked.

## Verify the affected features

From the client, open a fresh SSH session that sends the Finnish time locale.
Check that `locale` and `locale -a` exit successfully without warnings.

```bash
LC_TIME=fi_FI.UTF-8 ssh -o ControlPath=none -o SendEnv=LC_TIME kim@tr3 \
  'set -e; locale; locale -a; locale -k decimal_point'
```

On the reported tr3 configuration, `LANG` and `LC_NUMERIC` should still
resolve to `en_GB.UTF-8`, `LC_TIME` should show `fi_FI.UTF-8`, and
`decimal_point` should be `"."`. The generated locale list should include
`en_GB.utf8`, `fi_FI.utf8`, `sv_FI.utf8` and `sv_SE.utf8`. Repeating
the maintenance plan should show no further generation changes. A fresh
SSH session is sufficient after successful repair.

From the tr3 desktop, launch **Wolfram Language (CLI)**, evaluate `2+2` and
expect `4`. Launch **Wolfram Mathematica (GUI)** and evaluate
`Plot[Sin[x], {x, 0, 2 Pi}]` in a notebook. If the installer reports a limited
WolframScript check, run `wolframscript -code '2+2'` as the desktop user.

[Debian locale-gen manual](https://manpages.debian.org/trixie/locales/locale-gen.8.en.html)
