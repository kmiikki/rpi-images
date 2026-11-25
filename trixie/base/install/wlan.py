"""Raspberry Pi OS WLAN country policy and readback."""

from pathlib import Path
import re
import time

from os_upgrade import boot_id

RFKILL = Path('/sys/class/rfkill')
CMDLINE = Path('/boot/firmware/cmdline.txt')


def countries():
    table = Path('/usr/share/zoneinfo/iso3166.tab').read_text()
    return {line.split()[0] for line in table.splitlines() if line and not line.startswith('#')}


def read_state(host):
    def output(*argv):
        result = host.probe(argv)
        if result.returncode:
            raise ValueError(f'{argv[0]} failed: {result.stderr.strip()}')
        return result.stdout.strip()

    stored = [arg.partition('=')[2] for arg in CMDLINE.read_text().split()
              if arg.startswith('cfg80211.ieee80211_regdom=')]
    blocks = []
    for path in RFKILL.glob('rfkill*'):
        if (path/'type').read_text().strip() == 'wlan':
            blocks.append(((path/'soft').read_text().strip(), (path/'hard').read_text().strip()))
    state = dict(stored=stored[-1] if stored else '', blocks=blocks, country='', radio='')
    if blocks and not all(hard == '1' for _, hard in blocks):
        text = output('/usr/sbin/iw', 'reg', 'get')
        global_section = re.split(r'(?m)^phy#', text)[0]
        match = re.search(r'(?m)^country ([A-Z0-9]{2}):', global_section)
        state.update(country=match[1] if match else '',
                     radio=output('env', 'LC_ALL=C', 'nmcli', '-g', 'WIFI', 'radio'))
    return state


def existing_country(state):
    valid = countries()
    return next((value for value in (state['stored'], state['country']) if value in valid), None)


def deferred(state):
    if not state['blocks']:
        return 'DEFERRED WLAN device unavailable'
    if all(hard == '1' for _, hard in state['blocks']):
        return 'DEFERRED WLAN hardware blocked'
    return ''


def ready(state, country):
    return (state['stored'] == state['country'] == country and state['radio'] == 'enabled'
            and all(soft == '0' for soft, hard in state['blocks'] if hard == '0'))


def verify(state, country, data=None):
    if reason := deferred(state):
        return reason
    if not ready(state, country):
        raise ValueError(f"WLAN verification failed: boot={state['stored']}, global={state['country']}, "
                         f"radio={state['radio']}, rfkill={state['blocks']}")
    baseline = (data or {}).get('wlan_configured_boot')
    persisted = baseline and baseline != boot_id() and data.get('wlan_country') == country
    persistence = 'verified after reboot' if persisted else 'post-reboot verification pending'
    return f'WLAN {country}, boot setting and global domain verified, radio enabled and unblocked ({persistence})'


def configure(host, country, *, expected, data=None, preview=False):
    if country not in countries():
        raise ValueError('Choose a valid two-letter WLAN country')
    state = read_state(host)
    previous = existing_country(state)
    if previous and previous not in (expected, country):
        raise ValueError('WLAN country changed since the plan. Review the new setting.')
    if reason := deferred(state):
        return reason
    if preview:
        return f"Enable WLAN in {country} (boot={state['stored'] or 'unset'}, global={state['country']}, radio={state['radio']})"
    changed = not ready(state, country)
    if changed:
        if state['stored'] != country or state['country'] != country:
            host.run(['/usr/bin/raspi-config', 'nonint', 'do_wifi_country', country])
        if any(soft == '1' and hard == '0' for soft, hard in state['blocks']):
            host.run(['/usr/sbin/rfkill', 'unblock', 'wlan'])
        if state['radio'] != 'enabled':
            host.run(['nmcli', 'radio', 'wifi', 'on'])
        for attempt in range(11):
            state = read_state(host)
            if ready(state, country) or deferred(state) or attempt == 10:
                break
            time.sleep(0.2)
    detail = verify(state, country, None if changed else data)
    if data is not None and not deferred(state):
        if changed or data.get('wlan_country') != country or not data.get('wlan_configured_boot'):
            data['wlan_configured_boot'] = boot_id()
        data['wlan_country'] = country
    return detail
