"""Check and prepare a Raspberry Pi OS Trixie card for Pi 4B or Pi 5B."""

import argparse
from contextlib import nullcontext
import fcntl
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import preboot


BOARD = {
    'pi4': ('Raspberry Pi 4 Model B', 'bcm2711-rpi-4-b.dtb', b'raspberrypi,4-model-b'),
    'pi5': ('Raspberry Pi 5 Model B', 'bcm2712-rpi-5-b.dtb', b'raspberrypi,5-model-b'),
}
BACKUP_TAG = 'adapt-model'


def model_id(description):
    for model,(name, _, _) in BOARD.items():
        if re.fullmatch(re.escape(name)+r'(?: Rev [\d.]+)?',description):
            return model
    raise ValueError(f'Expected Raspberry Pi 4 Model B or Raspberry Pi 5 Model B, found {description!r}.')


def verify_firmware(boot, model):
    name,dtb,compatible=BOARD[model]
    files=['cmdline.txt',dtb]
    if model=='pi4':
        files.extend(['start4.elf','fixup4.dat'])
    for filename in files:
        path=boot/filename
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Missing or invalid firmware file for {name}: {path}.')
    header=(boot/dtb).read_bytes()
    if not header.startswith(b'\xd0\x0d\xfe\xed') or compatible+b'\0' not in header:
        raise ValueError(f'{dtb} does not identify {name}.')
    print(f'Firmware for {name}: '+', '.join(files))


def adaptation(original,target):
    if target=='pi5':
        return preboot.kernel_plan(original)
    if preboot.boot_settings(original,'pi4').get('kernel',preboot.KERNEL_IMAGE)!=preboot.KERNEL_IMAGE:
        raise ValueError('The existing Pi 4 kernel override requires manual review; it was preserved.')
    return original


def rollback_content(firmware,current,backup):
    expected=rf'{re.escape(firmware.name)}\.{BACKUP_TAG}\.bak\.[A-Za-z0-9_]+'
    if not re.fullmatch(expected,backup):
        raise ValueError('Use the backup basename printed by this tool.')
    saved=preboot.file_state(firmware.parent/backup)[0]
    original=saved.decode('utf-8','surrogateescape')
    if saved==current:
        return saved
    if preboot.kernel_plan(original).encode('utf-8','surrogateescape')!=current:
        raise ValueError('Boot configuration changed since this backup was made; review the differences manually.')
    return saved


def approved(args):
    return args.yes or (sys.stdin.isatty() and input('Apply this boot configuration change? [y/N] ').strip().lower() in {'y','yes'})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=BOARD,help='model that will boot the card; defaults to the running model')
    parser.add_argument('--prepare',action='store_true',help='validate and, if needed, prepare the card before moving it')
    parser.add_argument('--plan',action='store_true',help='inspect files and print proposed changes without writing')
    parser.add_argument('--yes',action='store_true',help='approve the displayed boot configuration change')
    parser.add_argument('--rollback',metavar='BACKUP',help='restore a backup created by this tool when the current file still matches the result')
    args=parser.parse_args(argv)
    if args.rollback and (args.target or args.prepare):
        parser.error('--rollback cannot be combined with --target or --prepare')
    source=model_id(preboot.MODEL.read_bytes().rstrip(b'\0').decode())
    preboot.check_host(firmware=source=='pi5')
    target=args.target or source
    if target!=source and not (args.prepare or args.plan):
        parser.error('use --prepare on the source Pi before moving a card to the specified target')
    print(f'Running: {BOARD[source][0]}, {platform.release()}, {os.sysconf("SC_PAGE_SIZE")} byte pages.')
    print(f'Target: {BOARD[target][0]}.')
    firmware=preboot.FIRMWARE
    if not firmware.parent.is_mount():
        raise ValueError(f'Expected a mounted Raspberry Pi boot partition at {firmware.parent}.')
    if not args.plan and os.geteuid()!=0:
        raise ValueError('Run through sudo to apply changes, or use --plan.')
    with (nullcontext() if args.plan else preboot.LOCK.open('a')) as lock:
        if lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
        before=preboot.file_state(firmware)
        verify_firmware(firmware.parent,target)
        release=preboot.kernel_release(firmware)
        print(f'Verified stock {preboot.KERNEL_IMAGE}, initramfs8 and installed modules for {release}.')
        if args.rollback:
            updated=rollback_content(firmware,before[0],args.rollback)
        else:
            updated=adaptation(before[0].decode('utf-8','surrogateescape'),target).encode('utf-8','surrogateescape')
        changed=updated!=before[0]
        if changed:
            print(f'Boot change: {"restore the reviewed backup" if args.rollback else "select kernel8.img in the Pi 5 section"} of {firmware}.')
            if not args.plan:
                if not approved(args):
                    print('Boot configuration preserved.')
                    return 1
                info=before[1]
                backup=preboot.replace_file(firmware,before,updated,stat.S_IMODE(info.st_mode),
                                            info.st_uid,info.st_gid,backup=True,backup_tag=BACKUP_TAG)
                if not args.rollback:
                    print(f'Rollback: bash adapt-rpi-model.sh --rollback {backup.name} --plan')
        else:
            print('No boot configuration edits needed.')
        if target!=source:
            print(f'After applying this plan, shut down, move the card to {BOARD[target][0]}, boot and rerun the tool with --plan.')
        elif changed or not args.rollback and (platform.release()!=release or os.sysconf('SC_PAGE_SIZE')!=4096):
            print('Reboot to verify the expected kernel. Check uname -r and getconf PAGESIZE.')
        elif not args.rollback:
            print('Live kernel verified: stock v8 and 4096 byte pages.')
        print('Scientific Python, the hardware bridge, Wolfram and installed packages are preserved.')
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        sys.exit(f'Adaptation error: {error}')
