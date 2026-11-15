#!/usr/bin/env python3
"""System-Python entrypoint for the existing rpi-share catalog implementation."""
import sys
from rpi_share_catalog import builder_cli

if __name__=='__main__':
    try: builder_cli()
    except (ValueError,OSError,TypeError) as exc: sys.exit('Error: '+str(exc))
