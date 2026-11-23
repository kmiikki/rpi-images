"""LXTerminal edits use per-user temporary fixtures and never start the terminal."""

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'install'))
import lxterminal_zoom as zoom


class TerminalZoomTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home=Path(temp.name)
        self.path=self.home/'.config/lxterminal/lxterminal.conf'

    def initial(self,text):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(text)
        self.path.chmod(0o640)

    def test_finnish_and_swedish_are_idempotent_and_preserve_file_mode(self):
        original='[general]\nfontname=Monospace 13\n# note\n[shortcut]\nzoom_in_accel=actual\nbutton=copy\n'
        self.initial(original)
        initial=self.path.stat()
        with patch.object(zoom,'selected',return_value=True):
            self.assertEqual(zoom.configure(self.home,'fi',preview=True),'changed')
            self.assertEqual(self.path.read_text(),original)
            self.assertEqual(zoom.configure(self.home,'fi'),'changed')
            data=self.path.read_text()
            self.assertEqual(zoom.configure(self.home,'se',tracked=True),'managed')
            self.assertEqual(self.path.read_text(),data)
        self.assertIn('# rpi-images: original zoom_in_accel=actual\n',data)
        self.assertIn('# rpi-images: originally absent zoom_reset_accel\n',data)
        self.assertIn('fontname=Monospace 13\n# note\n',data)
        self.assertIn('button=copy\n',data)
        self.assertEqual(data.count(zoom.BEGIN),1)
        for key,value in zoom.ZOOM.items():
            self.assertEqual(data.splitlines().count(f'{key}={value}'),1)
        info=self.path.stat()
        self.assertEqual((info.st_uid,info.st_gid),(initial.st_uid,initial.st_gid))
        self.assertEqual(stat.S_IMODE(info.st_mode),0o640)
        self.assertEqual(zoom.configure(self.home,'de',restore=True,tracked=True),'changed')
        self.assertEqual(self.path.read_text(),original)

    def test_other_layout_and_nonselected_terminal_are_noops(self):
        with patch.object(zoom,'selected',return_value=True):
            for layout in ('de','us','gb'):
                self.assertEqual(zoom.configure(self.home,layout),'skipped')
        with patch.object(zoom,'selected',return_value=False):
            self.assertEqual(zoom.configure(self.home,'fi'),'skipped')
        self.assertFalse(self.path.parent.exists())

    def test_default_terminal_and_explicit_user_preference(self):
        terminal=self.home/'lxterminal'
        terminal.touch(mode=0o755)
        alternative=self.home/'x-terminal-emulator'
        alternative.symlink_to(terminal)
        self.assertTrue(zoom.selected(self.home,terminal,alternative))
        preference=self.home/'.config/xdg-terminals.list'
        preference.parent.mkdir()
        preference.write_text('# default\nfoot.desktop\nlxterminal.desktop\n')
        self.assertFalse(zoom.selected(self.home,terminal,alternative))
        terminal.chmod(0o644)
        self.assertFalse(zoom.selected(self.home,terminal,alternative))

    def test_new_file_is_private_and_reset_restores_absence(self):
        with patch.object(zoom,'selected',return_value=True):
            self.assertEqual(zoom.configure(self.home,'se'),'changed')
        self.assertEqual(self.path.stat().st_uid,os.geteuid())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)
        self.assertEqual(zoom.configure(self.home,None,restore=True,tracked=True),'changed')
        self.assertFalse(self.path.exists())

    def test_user_change_of_managed_value_or_markers_blocks_rewrite_and_reset(self):
        self.initial('[shortcut]\nzoom_reset_accel=original\n')
        with patch.object(zoom,'selected',return_value=True):
            zoom.configure(self.home,'fi')
            self.path.write_text(self.path.read_text().replace('<Primary>0','<Primary>period'))
            changed=self.path.read_bytes()
            for restore in (False,True):
                with self.assertRaisesRegex(ValueError,'customized'):
                    zoom.configure(self.home,'fi',restore=restore,tracked=True)
                self.assertEqual(self.path.read_bytes(),changed)
            self.path.write_text('[shortcut]\nzoom_reset_accel=user-binding\n')
            with self.assertRaisesRegex(ValueError,'markers'):
                zoom.configure(self.home,'se',tracked=True)

    def test_reset_keeps_unrelated_user_edits_and_restores_original_duplicates(self):
        original='[shortcut]\nzoom_in_accel=one\nzoom_in_accel=two\n[general]\nfont=initial\n'
        managed,_=zoom.edit(original)
        self.assertEqual(managed.splitlines().count('zoom_in_accel=<Primary>plus'),1)
        edited=managed.replace(zoom.END,'# user comment\ncopy=custom\n'+zoom.END).replace('font=initial','font=changed')
        restored,_=zoom.edit(edited,restore=True)
        self.assertEqual(restored,'[shortcut]\n# user comment\ncopy=custom\nzoom_in_accel=one\nzoom_in_accel=two\n[general]\nfont=changed\n')

    def test_symlink_destination_is_refused(self):
        self.path.parent.mkdir(parents=True)
        other=self.home/'other.conf'
        other.write_text('[shortcut]\n')
        self.path.symlink_to(other)
        with patch.object(zoom,'selected',return_value=True),self.assertRaises(OSError):
            zoom.configure(self.home,'fi')
        self.assertEqual(other.read_text(),'[shortcut]\n')

    def test_migrate_unmodified_old_block_and_restore_original_after_migration(self):
        original='[shortcut]\nzoom_reset_accel=original\n[general]\nfont=keep\n'
        current,_=zoom.edit(original)
        old=current.replace(zoom.VERSION+'\n','').replace('<Primary>0','<Primary>period')
        self.initial(old)
        with patch.object(zoom,'selected',return_value=True):
            self.assertEqual(zoom.configure(self.home,'us',tracked=True),'skipped')
            self.assertEqual(self.path.read_text(),old)
            self.assertEqual(zoom.configure(self.home,'se',preview=True,tracked=True),'changed')
            self.assertEqual(zoom.configure(self.home,'se',tracked=True),'changed')
            self.assertEqual(self.path.read_text(),current)
            self.assertEqual(zoom.configure(self.home,'fi',tracked=True),'managed')
        self.assertEqual(zoom.edit(old,restore=True),(original,False))
        self.assertEqual(zoom.edit(current,restore=True),(original,False))
