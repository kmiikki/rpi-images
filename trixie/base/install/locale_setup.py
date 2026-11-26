"""Provision Debian locales without changing language or numeric defaults."""

from dataclasses import dataclass
from pathlib import Path
import re
import runpy
import stat

from preboot import optional_file, replace_file

GEN_CONFIG = '/etc/locale.gen'
GEN_COMMAND = '/usr/sbin/locale-gen'
SUPPORTED = '/usr/share/i18n/SUPPORTED'
DEFAULTS = ('en_GB.UTF-8', 'fi_FI.UTF-8', 'sv_FI.UTF-8', 'sv_SE.UTF-8')
SYSTEM_CONFIGS = ('/etc/default/locale', '/etc/locale.conf')
CLEAN_ENV = ('/usr/bin/env', '-u', 'LOCPATH', '-u', 'I18NPATH', 'LC_ALL=C')
keyboard = runpy.run_path(str(Path(__file__).resolve().parents[1]/'bin/rpi-keyboard'))
REQUEST_KEYS = keyboard['LOCALE_KEYS'] | {'LANGUAGE'}


def requests(environ):
    return {key: value for key, value in environ.items() if key in REQUEST_KEYS and value}


def normalized(name):
    return name.lower().replace('utf-8', 'utf8')


def entries(text):
    return {normalized(fields[0]): ' '.join(fields) for line in text.splitlines()
            if len(fields := line.partition('#')[0].split()) == 2}


def language_locales(value):
    # LANGUAGE is a gettext preference list. Only territory-specific entries
    # suggest a libc locale, with UTF-8 as the default encoding.
    for item in value.split(':'):
        if re.fullmatch(r'[a-zA-Z]{2,3}_[a-zA-Z]{2}(?:@[\w-]+)?', item, re.ASCII):
            name, separator, modifier = item.partition('@')
            yield name + '.UTF-8' + separator + modifier
        elif '.' in item:
            yield item


@dataclass(frozen=True)
class Plan:
    locales: tuple
    enable: tuple
    generate: tuple
    fallback: tuple
    unavailable: tuple


def inventory(host):
    result = host.probe([*CLEAN_ENV, '/usr/bin/locale', '-a'])
    if result.returncode:
        raise ValueError('Cannot read installed locales with locale -a.')
    return {normalized(name) for name in result.stdout.split()}


def plan(host, store):
    supported_file = store.path(SUPPORTED)
    supported = entries(supported_file.read_text()) if supported_file.is_file() else {}
    existing_file = optional_file(store.path(GEN_CONFIG))
    enabled = entries(existing_file[0].decode(errors='surrogateescape')) if existing_file else {}
    installed = inventory(host)
    session = requests(getattr(host, 'locale_requests', {}))
    selected = set(DEFAULTS)
    selected.update((store.data or {}).get('locales', ()))
    system = [keyboard['settings'](store.path(path), REQUEST_KEYS) for path in SYSTEM_CONFIGS]
    for setting in (*system, session):
        selected.update(value for key, value in setting.items() if key != 'LANGUAGE' and value)
        selected.update(language_locales(setting.get('LANGUAGE') or ''))
    wanted = {normalized(name) for name in selected}
    known = {key: supported[key] for key in wanted & supported.keys()}
    # Persist package-supported names, never arbitrary session strings.
    locales = tuple(sorted(row.split()[0] for row in known.values()))
    enable = tuple(sorted(known[key] for key in known.keys() - enabled.keys()))
    generate = tuple(sorted(known[key].split()[0] for key in known.keys() - installed))
    available = installed | supported.keys()
    unsupported = {name for name in selected if normalized(name) not in available
                   and not keyboard['locale_alias_available'](name)}
    fallback = tuple((key, value) for key, value in sorted(session.items())
                     if key != 'LANGUAGE' and value in unsupported)
    unavailable = tuple(sorted(unsupported - {value for _, value in fallback}))
    return Plan(locales, enable, generate, fallback, unavailable)


def describe(proposal):
    if proposal.locales:
        print('Locales selected:', ', '.join(proposal.locales))
    if proposal.enable:
        print('Locales to enable in /etc/locale.gen:', ', '.join(row.split()[0] for row in proposal.enable))
    if proposal.generate:
        print('Locales to generate:', ', '.join(proposal.generate))
    if proposal.unavailable:
        print('LIMITED locale templates unavailable:', ', '.join(map(repr, proposal.unavailable)))
    for key, value in proposal.fallback:
        print(f'LIMITED {key}={value!r} is unavailable; installer commands use the local fallback.')


def verify(host, store):
    proposal = plan(host, store)
    describe(proposal)
    ready = not (proposal.enable or proposal.generate or proposal.unavailable or proposal.fallback)
    if ready:
        print('PASS locale selections and generated locales match.')
    return ready


def apply(host, store, proposal):
    if proposal.generate and not store.path(GEN_COMMAND).is_file():
        raise ValueError('locale-gen is unavailable. The Debian locales package provides it.')
    if proposal.enable:
        path = store.trusted_parents(GEN_CONFIG)
        before = optional_file(path)
        original, metadata = before or (b'', None)
        enabled = entries(original.decode(errors='surrogateescape'))
        rows = [row for row in proposal.enable if normalized(row.split()[0]) not in enabled]
        if rows:
            separator = b'\n' if original and not original.endswith(b'\n') else b''
            content = original + separator + ('\n'.join(rows) + '\n').encode()
            mode = stat.S_IMODE(metadata.st_mode) if metadata else 0o644
            owner = (metadata.st_uid, metadata.st_gid) if metadata else (0, 0)
            replace_file(path, before, content, mode, *owner)
            print('Enabled in /etc/locale.gen:', ', '.join(row.split()[0] for row in rows))
    if proposal.generate:
        host.run([*CLEAN_ENV, GEN_COMMAND, '--keep-existing'])
        missing = set(map(normalized, proposal.generate)) - inventory(host)
        if missing:
            raise ValueError('locale-gen did not generate: '+', '.join(sorted(missing)))
        print('Generated and verified:', ', '.join(proposal.generate))
    if not (proposal.enable or proposal.generate):
        print('Locale definitions already current.')
