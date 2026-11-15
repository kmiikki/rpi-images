#!/usr/bin/env python3
"""Explicit account maintenance, separate from normal setup."""
import subprocess
import sys
from rpi_accounts import main
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as exc:sys.exit('Error: '+str(exc))
