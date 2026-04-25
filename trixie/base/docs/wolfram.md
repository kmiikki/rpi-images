# Wolfram Engine (optional)

Wolfram Engine is available for Raspberry Pi OS and can be installed separately when needed.

It is intentionally **not** included in the base image.

## Why it is optional

Reasons for keeping Wolfram Engine outside the base installation:

- large disk footprint
- not ideal for low-memory Raspberry Pi models
- not needed on most measurement, logging, or control systems
- licensing considerations make it unsuitable as a default package in a generally shared setup script

This follows the same design principle as the rest of the base image: keep the default installation as lean, practical, and reproducible as possible.

## When it may make sense

Install Wolfram Engine only on systems that specifically need it, for example:

- symbolic mathematics
- ad hoc technical calculations
- educational use
- occasional analytical work where Wolfram tools are useful

## Installation

Basic usage:

```bash
./install_optional_wolfram.sh
````

Non-interactive:

```bash
./install_optional_wolfram.sh --yes
```

Dry-run:

```bash
./install_optional_wolfram.sh --dry-run
```

Verbose mode:

```bash
./install_optional_wolfram.sh --verbose
```

Combined example:

```bash
./install_optional_wolfram.sh --yes --verbose
```

The install script:

* checks that the system is suitable for Raspberry Pi Wolfram installation
* prints usage and licensing notes
* warns about low-memory systems
* installs `wolfram-engine` with `apt`
* verifies that `wolframscript` is available

## Removal

Basic usage:

```bash
./uninstall_optional_wolfram.sh
```

Non-interactive:

```bash
./uninstall_optional_wolfram.sh --yes
```

Dry-run:

```bash
./uninstall_optional_wolfram.sh --dry-run
```

Verbose mode:

```bash
./uninstall_optional_wolfram.sh --verbose
```

## Verification

After installation, a quick manual test is:

```bash
wolframscript -code "2+2"
wolframscript -code "Prime[1000]"
```

Expected example output:

```text
4
7919
```

## Notes about memory and storage

Wolfram Engine is relatively heavy compared with the typical software needed for data logging, instrument control, or lightweight analysis.

It may be a poor fit for Raspberry Pi systems with limited RAM, especially 1 GB models.

It also uses a significant amount of disk space, so it should only be installed on systems that actually need it.

## Notes about network speed

Installation speed depends heavily on network speed, because Wolfram Engine is a large package.

In practice, installation may be much faster on a 1000/1000 Mbps wired network than on a 100/10 Mbps connection.

This is one more reason why Wolfram Engine is kept outside the base image and installed only when explicitly needed.

## Licensing note

The Raspberry Pi Wolfram offering may include usage restrictions, including restrictions related to commercial use.

Users are responsible for ensuring that their installation and use comply with the applicable Wolfram and Raspberry Pi licensing terms.
