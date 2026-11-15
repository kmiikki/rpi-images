# Installation customization

Use the unified installer's profile builder to customize installation preferences.
The installers do not load override scripts from this directory.
Keep site-specific profiles outside the repository and store no credentials in them.

From the repository root, open the builder's menu:

```bash
cd trixie/base/install
python3 -B profile-builder.py
```

Create a profile from GENERAL, HOME or AALTO, edit its settings, preview the plan
and save it outside Git. GENERAL is the independent base for custom installations;
HOME and AALTO retain their predefined deployment policies.

For a command-line alternative, choose a new output filename:

```bash
python3 -B profile-builder.py --export GENERAL --output ~/workstation.json
python3 -B profile-builder.py --validate ~/workstation.json
bash setup-rpi.sh --profile-file ~/workstation.json --plan
sudo bash setup-rpi.sh --profile-file ~/workstation.json
```

To edit a saved profile, reopen the menu and choose **Load JSON**, then **Edit
setting**, validate and save. Existing output files are protected from accidental
overwrite. Explicit installer CLI options override corresponding profile settings:

```bash
bash setup-rpi.sh --profile-file ~/workstation.json --hostname rpi-workstation --plan
```

Review the displayed accounts, privileges and components before applying changes.
Profile files do not authorize account recovery, password setup or installation
confirmation. Existing account and sudo policies remain in force.

See the [profile builder guide](../../docs/profile-builder.md) for the format and
supported settings, and the [unified setup reference](../../docs/unified-setup.md)
for account recovery, safeguards and maintenance.
