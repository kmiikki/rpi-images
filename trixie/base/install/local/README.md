# Local configuration files

This directory is optional.

You may create local override files here if you want to customize usernames for your own machine.

## Example: `pre_home.local.sh`

```bash
export PRIMARY_USER="myuser"
```

## Example: `pre_aalto.local.sh`

```bash
export PRIMARY_USER="labadmin"
export EXTRA_SUDO_USERS_STR="assistant1 assistant2"
```

## Default behavior if these files do not exist

* `pre_home.sh` uses the current user who ran `sudo`
* `pre_aalto.sh` uses the current user who ran `sudo`
* no extra sudo users are created unless `EXTRA_SUDO_USERS_STR` is defined

## Important

Do not upload your real `.local.sh` files to GitHub.
They may contain usernames specific to your own environment.

