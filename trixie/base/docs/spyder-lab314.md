# Using Spyder with lab314

## Goal

Use Spyder installed outside the environment, while the Python interpreter and packages come from `lab314`.

This avoids maintaining a separate full Spyder installation inside every environment.

---

## Raspberry Pi

On Raspberry Pi OS Trixie:

* Spyder is installed with apt
* `spyder-kernels` is installed inside `/opt/lab314`

Installed packages:

```text
apt install spyder python3-spyder-kernels
```

Environment package:

```text
spyder-kernels==3.0.5
```

The matching interpreter is:

```text
/opt/lab314/bin/python
```

In Spyder:

1. Open Preferences
2. Python Interpreter
3. Select:

```text
Use the following Python interpreter
```

4. Set:

```text
/opt/lab314/bin/python
```

5. Restart Spyder

---

## Ubuntu

On Ubuntu:

* Spyder is kept in a separate `tools` environment
* `lab314` only contains Python packages and `spyder-kernels`

Typical setup:

```text
tools environment:
    spyder
    jupyter
    notebooks
    developer tools

lab314 environment:
    Python 3.14
    scientific packages
    opencv
    spyder-kernels
```

Example:

```bash
micromamba activate tools
spyder
```

Then configure Spyder to use:

```text
lab314 interpreter
```

for example:

```text
~/micromamba/envs/lab314/bin/python
```

or whichever path micromamba uses.

---

## Why This Structure Is Used

Advantages:

* only one Spyder installation
* faster updates
* smaller scientific environments
* easier to rebuild `lab314`
* fewer Qt conflicts

This is especially useful because Raspberry Pi and Ubuntu may use different Spyder versions.

Current known versions:

```text
Raspberry Pi:
    Spyder 6.0.5
    spyder-kernels 3.0.5

Ubuntu:
    Spyder 6.1.3
    spyder-kernels from lab314
```

---

## Verification

Run in Spyder console:

```python
import sys
import spyder_kernels

print(sys.executable)
print(spyder_kernels.__version__)
```

Expected on Raspberry Pi:

```text
/opt/lab314/bin/python
3.0.5
```

If another interpreter appears, Spyder is not using `lab314`.
