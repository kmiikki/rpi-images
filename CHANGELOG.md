# Changelog

## Unreleased · Raspberry Pi OS Trixie

- **A01–A03** Prompt for the hostname before approval, identify accounts before password entry and resume with approved WLAN and installation settings after reboot.
- **A04** Show Wolfram package size, free disk space and license terms before installation. Accept the Raspberry Pi package's fractional installed size and require explicit approval for package changes covered by the terms.
- **A05** Document how to load FI/SE LXTerminal zoom bindings in a separate window during the current desktop login.
- **A06** Offer personal and shared Chromium policies in every profile. Shared mode keeps the regular browser profile and uses the keyring-free backend with password saving disabled. AALTO defaults to shared. GENERAL and HOME default to personal.
- **A07** Use vendor desktop entry IDs and icons for the Mathematica GUI and Wolfram CLI. Hide additional package and Raspberry Pi entries for the same launch commands.
- **A08** Report SSH policy, service state, startup state and socket activation separately. Default HOME to keeping its current SSH settings.
- **A09** Enable and generate required regional locales and supported SSH-forwarded locales while preserving language and numeric defaults. Provide targeted repair and verification for existing installations.
- Document the scope of Raspberry Pi CSI camera acceptance, the Scientific Imaging integration and the standalone QtWebEngine limitation.
