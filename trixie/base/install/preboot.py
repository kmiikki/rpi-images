"""Configure the Pi 5 boot interfaces and initial keyboard independently of profiles."""

import argparse
from enum import Enum, auto
import filecmp
import fcntl
import gzip
import json
import os
from pathlib import Path
import platform
import re
import runpy
import stat
import struct
import subprocess
import sys
import tempfile

import installation_state as statefiles
from keyboard_ui import choose_layout

SOURCE = Path(__file__).resolve().parents[1] / 'bin/rpi-keyboard'
KEYBOARD = Path('/usr/local/bin/rpi-keyboard')
FIRMWARE = Path('/boot/firmware/config.txt')
MODEL = Path('/proc/device-tree/model')
IMAGE_MARKER = Path('/etc/rpi-issue')
LOCK = Path('/run/rpi-preboot.lock')
REBOOT_MARKER = Path('/run/rpi-preboot.reboot-required')
MODULE_DIRS = tuple(Path(root) / 'modules-load.d' for root in
                    ('/etc', '/run', '/usr/local/lib', '/usr/lib'))
MODULE_FILE = MODULE_DIRS[0] / 'rpi-preboot-i2c.conf'
LEGACY_MODULES = Path('/etc/modules')
DEV = Path('/dev')
LAYOUT = 'fi'
SYSTEM_OWNER = (0, 0)
KEYBOARD_PREFERENCE = statefiles.STATE_DIR/'keyboard.json'
KERNEL_IMAGE = 'kernel8.img'
KERNEL_START = '# BEGIN Scientific Python Environment - Raspberry Pi 5 compatibility'
KERNEL_END = '# END Scientific Python Environment - Raspberry Pi 5 compatibility'

# Documented board filters never combine with one another. Other filter types
# can combine with these and are kept unresolved until an [all] reset.
BOARD_FILTERS = set('pi0 pi0w pi02 pi1 pi2 pi3 pi3+ pi4 pi400 pi5 pi500 '
                    'cm0 cm1 cm3 cm3+ cm4 cm4s cm5'.split())
INTERFACES = {'i2c_arm': 'I²C', 'spi': 'SPI'}
ALIASES = {'i2c': 'i2c_arm', **{key: key for key in INTERFACES}}
ENABLED = {None, 'on', 'true', 'yes', '1'}
DISABLED = {'off', 'false', 'no', '0'}
# The stock Pi OS overlays do not export either of the target override names.
STOCK_OVERLAYS = {'vc4-kms-v3d', 'nospi10'}
DTPARAM = re.compile(r'^\s*(?:dtparam|device_tree_param)\s*=([\s\S]*)$')
OVERLAY = re.compile(r'^\s*(?:dtoverlay|device_tree_overlay)\s*=\s*([^,\s]*)')


class BootStatus(Enum):
    READY = auto()
    REBOOT_REQUIRED = auto()
    DEVICES_MISSING = auto()


def is_pi5_model(model):
    return re.fullmatch(r'Raspberry Pi 5 Model B(?: Rev [\d.]+)?', model) is not None


def check_host(announce=False, firmware=True):
    release = platform.freedesktop_os_release()
    model = MODEL.read_bytes().rstrip(b'\0').decode() if MODEL.exists() else 'unavailable'
    architecture = platform.machine()
    if announce:
        print(f"Detected OS: {release.get('PRETTY_NAME', 'unknown')}; hardware: {model} ({architecture})", flush=True)
    supported = is_pi5_model(model) or (not firmware and model.startswith('Raspberry Pi 4 '))
    if not (supported and architecture == 'aarch64' and struct.calcsize('P') == 8):
        raise ValueError('Preboot requires a 64-bit Raspberry Pi 5 Model B.' if firmware else 'Keyboard setup requires a 64-bit Raspberry Pi 4 or 5.')
    if (release.get('ID') not in {'debian', 'raspbian'} or release.get('VERSION_ID') != '13'
            or release.get('VERSION_CODENAME') != 'trixie' or not IMAGE_MARKER.is_file()):
        raise ValueError('Preboot requires Raspberry Pi OS Trixie (Debian 13).')


def firmware_plan(original):
    """Edit only base parameters in sections known to apply to the Pi 5."""
    if '\0' in original or original.startswith('\ufeff'):
        raise ValueError('Unexpected encoding in firmware config.txt.')
    lines = original.splitlines(keepends=True)
    settings = {name: [] for name in INTERFACES}
    edits = []
    board_matches, other_filter, none, overlay = True, False, False, ''
    for index, line in enumerate(lines):
        number = index + 1
        body = line.rstrip('\r\n')
        raw, separator, comment = body.partition('#')
        code = raw.strip()
        if code.startswith('['):
            section = re.fullmatch(r'\[([^\[\]]+)\]', code)
            if not section or len(code.encode('utf-8', 'surrogateescape')) > 98:
                raise ValueError(f'Malformed firmware filter on line {number}.')
            name = section[1]
            if name == 'all':
                board_matches, other_filter, none = True, False, False
            elif name == 'none':
                none = True
            elif name in BOARD_FILTERS:
                board_matches = name == 'pi5'
            else:
                other_filter = True
            continue
        if none or not board_matches:
            continue
        if re.match(r'^include(?:\s|=|$)', code):
            raise ValueError(f'Firmware include on line {number} requires manual review.')
        if re.match(r'^device_tree\s*=', code):
            raise ValueError(f'Custom Device Tree directive on line {number} requires manual review.')
        if match := OVERLAY.match(raw):
            # Under an unresolved filter the previous overlay may still be active.
            overlay = 'conditional overlay' if other_filter else match[1]
            continue
        match = DTPARAM.fullmatch(raw)
        if not match:
            continue
        fields = match[1].split(',')
        for offset, field in enumerate(fields):
            key, _, value = field.strip().partition('=')
            name = ALIASES.get(key.strip())
            if name is None:
                if re.split(r'\s+', key, maxsplit=1)[0] in ALIASES:
                    raise ValueError(f'Malformed {key!r} parameter on line {number}.')
                continue
            if other_filter or (overlay and overlay not in STOCK_OVERLAYS):
                raise ValueError(f'Ambiguous {name} scope on firmware line {number}; review filters and overlays.')
            value = value.strip() if '=' in field else None
            if value not in ENABLED | DISABLED:
                raise ValueError(f'Unsupported {name} value {value!r} on firmware line {number}.')
            if len(raw.encode('utf-8', 'surrogateescape')) > 98:
                raise ValueError(f'Firmware parameter line {number} exceeds the firmware line limit.')
            enabled = value in ENABLED
            settings[name].append((number, enabled))
            if not enabled:
                fields[offset] = re.sub(r'(=\s*)' + re.escape(value) + r'(?=\s*$)', r'\g<1>on', field)
                edits.append(f'line {number}: {key.strip()}={value} -> {key.strip()}=on')
        updated = raw[:match.start(1)] + ','.join(fields)
        if updated != raw:
            if len(updated.encode('utf-8', 'surrogateescape')) > 98:
                raise ValueError(f'Updated firmware line {number} would exceed the firmware line limit.')
            lines[index] = updated + separator + comment + line[len(body):]

    additions = []
    newline = '\r\n' if '\r\n' in original else '\n'
    for name, entries in settings.items():
        if not entries:
            additions.append(f'dtparam={name}=on{newline}')
            edits.append(f'insert dtparam={name}=on at the start of config.txt')
    return ''.join(additions + lines), settings, edits


def boot_settings(original, model):
    """Resolve the stock boot settings that apply to a particular Model B."""
    if '\0' in original or original.startswith('\ufeff'):
        raise ValueError('Unexpected encoding in firmware config.txt.')
    board, conditional, disabled = True, False, False
    settings = {}
    for number, line in enumerate(original.splitlines(), 1):
        code = line.partition('#')[0].strip()
        if code.startswith('['):
            filter_match = re.fullmatch(r'\[([^\[\]]+)\]', code)
            if not filter_match or len(code.encode('utf-8','surrogateescape')) > 98:
                raise ValueError(f'Malformed firmware filter on line {number}.')
            section = filter_match[1]
            if section == 'all':
                board, conditional, disabled = True, False, False
            elif section == 'none':
                disabled = True
            elif section in BOARD_FILTERS:
                board = section == model
            else:
                conditional = True
            continue
        if disabled or not board:
            continue
        if re.match(r'^include(?:\s|=|$)',code):
            raise ValueError(f'Firmware include on line {number} requires manual review.')
        key, equals, value = code.partition('=')
        key = key.strip()
        if key in {'initramfs', 'ramfsfile'} or re.match(r'^initramfs\s', code):
            raise ValueError(f'Custom initramfs on firmware line {number} requires manual review.')
        if key not in {'kernel','auto_initramfs','arm_64bit','os_prefix','device_tree','cmdline',
                       'start_file','fixup_file','start_x','start_debug','armstub','kernel_address'}:
            continue
        if not equals or conditional or key in settings or len(code.encode('utf-8','surrogateescape')) > 98:
            raise ValueError(f'Ambiguous or custom {key} setting on firmware line {number}; review before switching kernels.')
        settings[key] = value.strip()
    stock_optional={'cmdline':'cmdline.txt','start_x':'0','start_debug':'0'}
    for key,value in settings.items():
        if key not in {'kernel','auto_initramfs','arm_64bit'} and stock_optional.get(key)!=value:
            raise ValueError(f'Custom {key} setting for {model} requires manual review.')
    if settings.get('auto_initramfs') != '1' or settings.get('arm_64bit', '1') != '1':
        raise ValueError('The 4 KiB kernel requires automatic initramfs loading and 64-bit boot mode.')
    return settings


def kernel_plan(original):
    """Select the stock 4 KiB image only in a boot configuration we can resolve."""
    settings = boot_settings(original, 'pi5')
    if 'kernel' in settings:
        if settings['kernel'] != KERNEL_IMAGE:
            raise ValueError(f'Existing Pi 5 kernel={settings["kernel"]} requires manual review; it was preserved.')
        return original
    if KERNEL_START in original or KERNEL_END in original:
        raise ValueError('Incomplete installer kernel block; review before changing boot settings.')
    newline = '\r\n' if '\r\n' in original else '\n'
    lines = [
        '', KERNEL_START, '[all]', '[pi5]',
        '# Use the stock 4 KiB kernel for Spyder formatted Help (Qt5 WebEngine).',
        '# No explicit kernel= setting applied to Raspberry Pi 5 before this change.',
        '# To restore the firmware default, remove this entire marked block.',
        f'kernel={KERNEL_IMAGE}', '[all]', KERNEL_END, '',
    ]
    return original + (newline if original and not original.endswith('\n') else '') + newline.join(lines)


def kernel_release(firmware, modules=Path('/lib/modules')):
    """Verify the image page size and identify its matching installed boot artifacts."""
    image = firmware.parent / KERNEL_IMAGE
    initramfs = firmware.parent / 'initramfs8'
    for path in (image, initramfs):
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Missing or invalid Raspberry Pi kernel artifact: {path}')
    with image.open('rb') as stream:
        compressed = stream.read(2) == b'\x1f\x8b'
    with (gzip.open(image, 'rb') if compressed else image.open('rb')) as stream:
        header = stream.read(64)
    if header[56:60] != b'ARM\x64' or ((struct.unpack_from('<Q', header, 24)[0] >> 1) & 3) != 1:
        raise ValueError(f'{image} is not an ARM64 image declaring 4 KiB pages.')
    boot = firmware.parent.parent
    for candidate in sorted(boot.glob('vmlinuz-*-rpi-v8')):
        release = candidate.name.removeprefix('vmlinuz-')
        matching_initrd = boot / f'initrd.img-{release}'
        dep = modules / release / 'modules.dep'
        if (candidate.is_file() and matching_initrd.is_file() and dep.is_file()
                and filecmp.cmp(image, candidate, shallow=False)
                and filecmp.cmp(initramfs, matching_initrd, shallow=False)
                and dep.stat().st_size > 0):
            listing = subprocess.run(['lsinitramfs', str(initramfs)], capture_output=True, text=True, check=True).stdout
            module_path = re.compile(r'^(?:\./)?(?:usr/)?lib/modules/' + re.escape(release) + r'(?:/|$)')
            if any(module_path.match(line) for line in listing.splitlines()):
                return release
    raise ValueError(f'No installed Raspberry Pi v8 kernel, matching initramfs and kernel modules for {image}.')


def kernel_status(pending, boot_id):
    if not FIRMWARE.parent.is_mount():
        return f'Verification pending: expected boot partition at {FIRMWARE.parent}'
    try:
        original = file_state(FIRMWARE)[0].decode('utf-8','surrogateescape')
        change = kernel_plan(original) != original
        release = kernel_release(FIRMWARE)
    except (PermissionError,FileNotFoundError) as exc:
        return 'Verification pending: '+str(exc)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        return 'Unexpected boot configuration: '+str(exc)
    if change:
        return 'Kernel selection change required (approval required)'
    if os.sysconf('SC_PAGE_SIZE') == 4096 and platform.release() == release:
        return 'Ready – stock v8 kernel, 4096 byte pages'
    if pending and pending != boot_id:
        return 'Unexpected running kernel after reboot'
    return 'Reboot required to verify '+release


def configure_kernel(*, approve, pending, boot_id):
    if not FIRMWARE.parent.is_mount():
        raise ValueError(f'Expected a mounted Raspberry Pi boot partition at {FIRMWARE.parent}.')
    before = file_state(FIRMWARE)
    original = before[0].decode('utf-8', 'surrogateescape')
    updated = kernel_plan(original)
    release = kernel_release(FIRMWARE)
    pages = os.sysconf('SC_PAGE_SIZE')
    running = platform.release()
    print(f'Pi 5 kernel: running {running}, {pages} byte pages; verified {KERNEL_IMAGE} on disk ({release}).')
    if updated != original:
        print(f'Proposed boot change: kernel={KERNEL_IMAGE} in {FIRMWARE}; reboot required.')
        if not approve():
            print('LIMITED: boot change deferred. Spyder formatted Help can fail with 16 KiB pages. Use Plain Text Help or an external browser.')
            return 'deferred'
        metadata = before[1]
        replace_file(FIRMWARE, before, updated.encode('utf-8', 'surrogateescape'),
                     stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid, backup=True)
        return 'changed'
    if pages == 4096 and running == release:
        print('PASS Pi 5 kernel: running the verified stock v8 kernel with 4096 byte pages.')
        return 'ready'
    if pending and pending == boot_id:
        return 'reboot'
    if pending:
        raise ValueError(f'After reboot, expected {release} with 4096 byte pages. Review boot configuration and backup before proceeding.')
    print(f'LIMITED: the configured kernel differs from the running kernel. Reboot to verify {release} and 4096 byte pages.')
    return 'reboot'


def file_state(path):
    """Read a regular, non-symlinked file and its metadata."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f'Expected a regular file at {path}.')
        return stream.read(), metadata


def optional_file(path):
    try:
        return file_state(path)
    except FileNotFoundError:
        return None


def write_temp(path, data, mode, uid, gid, prefix):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=prefix, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            descriptor = stream.fileno()
            metadata = os.fstat(descriptor)
            if (metadata.st_uid, metadata.st_gid) != (uid, gid):
                os.fchown(descriptor, uid, gid)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != mode:
                os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    return temporary


def current_file(path, expected):
    actual = optional_file(path)
    if actual is None or expected is None:
        return actual is expected
    data, metadata = actual
    original, old = expected
    return data == original and (metadata.st_ino, metadata.st_dev, metadata.st_mtime_ns,
                                 metadata.st_ctime_ns) == (old.st_ino, old.st_dev, old.st_mtime_ns,
                                                           old.st_ctime_ns)


def sync_parent(path):
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replace_file(path, before, data, mode, uid, gid, backup=False, backup_tag='preboot'):
    temporary = write_temp(path, data, mode, uid, gid, f'.{path.name}.')
    try:
        if not current_file(path, before):
            raise ValueError(f'{path} changed during preboot; rerun after reviewing the file.')
        if backup:
            original = before[1]
            saved = write_temp(path, before[0], stat.S_IMODE(original.st_mode), original.st_uid,
                               original.st_gid, f'{path.name}.{backup_tag}.bak.')
            sync_parent(path)
            print(f'Configuration backup saved at {saved}.')
            if not current_file(path, before):
                raise ValueError(f'{path} changed during backup; rerun after reviewing the file.')
        os.replace(temporary, path)
        sync_parent(path)
        return saved if backup else None
    finally:
        temporary.unlink(missing_ok=True)


def module_configured():
    # Respect directory precedence, including masks using symlinks to /dev/null.
    configurations = {}
    for directory in MODULE_DIRS:
        for path in directory.glob('*.conf'):
            configurations.setdefault(path.name, path)
    for path in (*configurations.values(), LEGACY_MODULES):
        if path.resolve() == Path('/dev/null'):
            continue
        try:
            lines = path.read_text().splitlines()
        except FileNotFoundError:
            continue
        if any(line.split('#', 1)[0].strip().replace('_', '-') == 'i2c-dev' for line in lines):
            return True
    return False


def describe_firmware(settings):
    statuses = {frozenset(): 'not explicitly configured', frozenset({True}): 'enabled',
                frozenset({False}): 'disabled', frozenset({True, False}): 'conflicting on/off'}
    for name, entries in settings.items():
        status = statuses[frozenset(enabled for _, enabled in entries)]
        details = ', '.join(f"line {number} {'on' if enabled else 'off'}" for number, enabled in entries)
        if len(entries) > 1:
            details = 'multiple active entries: ' + details
        print(f'{INTERFACES[name]} firmware setting: {status}' + (f' ({details})' if details else ''))


def keyboard_installed(installed, source):
    if installed is None:
        return False
    data, metadata = installed
    return (data == source and stat.S_IMODE(metadata.st_mode) == 0o755
            and (metadata.st_uid, metadata.st_gid) == SYSTEM_OWNER)


def active_layout():
    keyboard = runpy.run_path(str(SOURCE))
    return keyboard['settings'](keyboard['SYSTEM'], keyboard['SYSTEM_KEYS']).get('XKBLAYOUT')


def configure_keyboard(plan, show_plan, override, interactive):
    source = SOURCE.read_bytes()
    installed = optional_file(KEYBOARD)
    install_pending = not keyboard_installed(installed, source)
    keyboard = runpy.run_path(str(SOURCE))
    layouts = keyboard['layouts']()
    current = keyboard['settings'](keyboard['SYSTEM'], keyboard['SYSTEM_KEYS']).get('XKBLAYOUT')
    saved = None
    private_preference = False
    if statefiles.secure_directory(KEYBOARD_PREFERENCE.parent, uid=SYSTEM_OWNER[0]):
        try:
            preference = json.loads(statefiles.private_read(KEYBOARD_PREFERENCE, uid=SYSTEM_OWNER[0]))
            if preference.get('version') != 1 or not isinstance(preference.get('layout'), str):
                raise ValueError('Unrecognized saved keyboard preference')
            saved = preference['layout']
        except FileNotFoundError:
            pass
        except PermissionError:
            if not plan:
                raise
            private_preference = True
    if override is not None and override not in layouts:
        raise ValueError(f'Unknown XKB keyboard layout: {override!r}')
    current_valid = bool(current and all(code in layouts for code in current.split(',')))
    reuse = override is None and current_valid and (saved is not None or private_preference
            or installed is not None and installed[0]!=source)
    if override is not None:
        selected = override
    elif reuse:
        # A successful standalone or external layout change takes precedence over the saved initial choice.
        selected = current
    elif saved in layouts:
        selected = saved
    elif interactive and not plan:
        selected = choose_layout(layouts, input)
    else:
        selected = LAYOUT
    if selected not in layouts and not (current_valid and selected == current):
        raise ValueError(f'Keyboard layout {selected!r} is unavailable. Select --keyboard-layout explicitly.')
    keyboard_pending = not reuse and selected in layouts and keyboard['layout_pending'](selected)
    if keyboard_pending:
        keyboard['keyboard_backend']()
    if show_plan:
        print(f'Keyboard utility: {"install" if install_pending else "already installed at"} {KEYBOARD}.')
        print(f'Keyboard layout: {layouts.get(selected,selected)} ({selected})' +
              (' · initial default; interactive setup offers a choice' if saved is None and installed is None and override is None and plan else ''))
    if plan:
        return selected, False
    if install_pending:
        replace_file(KEYBOARD, installed, source, 0o755, *SYSTEM_OWNER, backup=installed is not None)
        print(f'Installed {KEYBOARD}.')
    if not keyboard_installed(file_state(KEYBOARD), source):
        raise ValueError(f'Could not verify installation of {KEYBOARD}.')
    if not reuse and selected in layouts:
        print(f'Checking keyboard configuration ({selected}).', flush=True)
        subprocess.run([str(KEYBOARD), selected], check=True)
    else:
        print(f'Keeping the stored keyboard layout ({selected}); active layout unconfirmed.')
    if selected != saved:
        statefiles.secure_directory(KEYBOARD_PREFERENCE.parent, create=True, uid=SYSTEM_OWNER[0])
        statefiles.atomic_write(KEYBOARD_PREFERENCE, (json.dumps({'version': 1, 'layout': selected})+'\n').encode())
    return selected, install_pending or keyboard_pending or selected != saved


def _configure(plan, show_plan, layout, interactive, firmware, approve_firmware=None):
    if not firmware:
        return BootStatus.READY, configure_keyboard(plan, show_plan, layout, interactive)[0]
    if not FIRMWARE.parent.is_mount():
        raise ValueError(f'Expected a mounted Raspberry Pi boot partition at {FIRMWARE.parent}.')
    firmware = file_state(FIRMWARE)
    original, metadata = firmware
    updated, settings, edits = firmware_plan(original.decode('utf-8', 'surrogateescape'))
    if show_plan:
        describe_firmware(settings)
        for edit in edits:
            print(f'{"Would change" if plan else "Planned firmware change"}: {edit}')
        if not edits:
            print('No firmware edits needed.')

    module_pending = not module_configured()
    if module_pending and optional_file(MODULE_FILE) is not None:
        raise ValueError(f'{MODULE_FILE} already exists without an effective i2c-dev entry; review it.')

    selected, keyboard_changed = configure_keyboard(plan, show_plan, layout, interactive)

    if not plan and (edits or module_pending) and approve_firmware is not None:
        for edit in edits:
            print(f'Proposed boot change: {edit}')
        if module_pending:
            print(f'Proposed boot change: load i2c-dev via {MODULE_FILE}')
        if not approve_firmware():
            raise ValueError('I²C/SPI boot changes were not approved. Run setup again to review them.')

    i2c_live = (DEV / 'i2c-1').is_char_device()
    spi_live = any(path.is_char_device() for path in DEV.glob('spidev0.*'))
    if show_plan:
        print(f'I²C userspace driver: {"schedule i2c-dev at boot" if module_pending else "already configured at boot"}.')
        print(f'Current device nodes: I²C {"present" if i2c_live else "missing"}, '
              f'SPI {"present" if spi_live else "missing"}.')
    needs_activation = bool(edits or (module_pending and not i2c_live))
    if needs_activation or REBOOT_MARKER.exists():
        status = BootStatus.REBOOT_REQUIRED
    elif i2c_live and spi_live:
        status = BootStatus.READY
    else:
        status = BootStatus.DEVICES_MISSING

    if plan:
        return status, selected

    if module_pending:
        replace_file(MODULE_FILE, None, b'i2c-dev\n', 0o644, *SYSTEM_OWNER)
        print(f'Scheduled i2c-dev at boot via {MODULE_FILE}.')
    if not module_configured():
        raise ValueError('Could not verify persistent i2c-dev loading.')

    if edits:
        replace_file(FIRMWARE, firmware, updated.encode('utf-8', 'surrogateescape'),
                     stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid, backup=True)
        for edit in edits:
            print(f'Changed: {edit}')
    if needs_activation:
        # /run is cleared on reboot, allowing the next invocation to verify the live devices.
        REBOOT_MARKER.touch()
    if firmware_plan(file_state(FIRMWARE)[0].decode('utf-8', 'surrogateescape'))[2]:
        raise ValueError(f'Could not verify enabled I²C and SPI firmware settings in {FIRMWARE}.')
    print('Verified I²C and SPI boot settings, i2c-dev loading configuration, and the keyboard utility.')
    if not any((edits, module_pending, keyboard_changed)):
        print('No changes needed.')
    return status, selected


def report_reboot(status):
    if status is BootStatus.REBOOT_REQUIRED:
        print('Reboot required for preboot hardware settings.')
        print('After reboot, check: ls -l /dev/i2c-1 /dev/spidev0.*')
        print('Check the stored keyboard layout with rpi-keyboard --current and test typing on the desktop.')
    elif status is BootStatus.READY:
        print('No reboot required for preboot hardware settings. Both interface device nodes are present.')
    else:
        print('I²C or SPI device nodes are missing even though the boot settings are enabled.')
        print('Check: ls -l /dev/i2c-1 /dev/spidev0.*. Review the boot configuration and kernel logs.')
        print('If the boot settings were changed outside setup during this boot, reboot once manually.')


def run(*, plan, show_plan=True, announce_host=False, layout=None, interactive=False, firmware=True,
        approve_firmware=None):
    """Preview or apply the same initialization and return the hardware status."""
    check_host(announce=announce_host, firmware=firmware)
    if plan:
        return _configure(True, show_plan, layout, interactive, firmware)
    if os.geteuid() != 0:
        raise ValueError('Run setup through sudo to apply preboot; --plan needs no root.')
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _configure(False, show_plan, layout, interactive, firmware, approve_firmware)


def main(argv, runner=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--preboot', action='store_true', required=True, help='configure first-boot prerequisites')
    parser.add_argument('--plan', '--dry-run', action='store_true', help='preview without making changes')
    parser.add_argument('--keyboard-layout', help='select an installed XKB layout code')
    args = parser.parse_args(argv)
    if runner:
        status, _=runner(args)
    else:
        status, _=run(plan=args.plan,announce_host=True,layout=args.keyboard_layout,interactive=sys.stdin.isatty())
    if args.plan:
        print(f'Reboot expected: {"yes" if status is BootStatus.REBOOT_REQUIRED else "no"}. PLAN ONLY: no changes made.')
        if status is BootStatus.DEVICES_MISSING:
            report_reboot(status)
    else:
        report_reboot(status)
        if status is BootStatus.REBOOT_REQUIRED:
            print('Run sudo reboot when ready.')
        elif status is BootStatus.DEVICES_MISSING:
            return 1
    return 0
