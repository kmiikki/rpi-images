"""Fresh setup, repair and boot verification without a wireless device."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'install'))
import lifecycle
import setup_rpi
import wlan
from test_rpi_setup import FakeHost

FRESH = dict(stored='', country='00', blocks=[('1', '0')], radio='disabled')
READY = dict(stored='FI', country='FI', blocks=[('0', '0')], radio='enabled')


class WirelessTests(unittest.TestCase):
    def test_all_profiles_plan_existing_country_and_international_choice(self):
        for profile in ('GENERAL','HOME','AALTO'):
            for state, options, expected in (
                    (FRESH, [], 'FI'), (dict(READY,stored='DE'), [], 'DE'),
                    (READY, ['--wlan-country', 'se'], 'SE')):
                with self.subTest(profile=profile,expected=expected), redirect_stdout(io.StringIO()) as out:
                    host=FakeHost()
                    host.wlan_state=lambda:state
                    result=setup_rpi.main(['--profile',profile,'--plan','--share-later',*options],host)
                    self.assertEqual(result,0)
                    self.assertIn('enable WLAN in '+expected,out.getvalue())
                    self.assertFalse(host.calls)

    def test_fresh_apply_rerun_and_post_reboot_readback(self):
        store={}
        host=Mock()
        with patch.object(wlan,'read_state',side_effect=[FRESH,READY,READY]), patch.object(wlan,'boot_id',return_value='one'):
            self.assertIn('pending',wlan.configure(host,'FI',expected=None,data=store))
            self.assertEqual(host.run.call_args_list,[
                call(['/usr/bin/raspi-config','nonint','do_wifi_country','FI']),
                call(['/usr/sbin/rfkill','unblock','wlan']),call(['nmcli','radio','wifi','on'])])
            host.reset_mock()
            self.assertIn('pending',wlan.configure(host,'FI',expected='FI',data=store))
            host.run.assert_not_called()
        with patch.object(wlan,'boot_id',return_value='two'):
            self.assertIn('verified after reboot',wlan.verify(READY,'FI',store))
            with self.assertRaisesRegex(ValueError,'verification failed'):
                wlan.verify(dict(READY,radio='disabled'),'FI',store)

    def test_absent_and_hard_blocked_adapters_are_deferred(self):
        for blocks,reason in (([], 'unavailable'),([('1','1')], 'hardware blocked')):
            host=Mock()
            with patch.object(wlan,'read_state',return_value=dict(FRESH,blocks=blocks)):
                self.assertIn(reason,wlan.configure(host,'FI',expected=None))
                host.run.assert_not_called()

    def test_repair_plan_is_read_only_and_rechecks_country(self):
        store,host=Mock(data={'profile':'HOME'}),Mock()
        with patch.object(wlan,'read_state',return_value=READY), redirect_stdout(io.StringIO()):
            plan=lifecycle.software_action(store,host,'repair','wlan',[],True,wlan_country='SE')
            self.assertEqual(plan,('FI','SE'))
            host.run.assert_not_called()
        with patch.object(wlan,'read_state',return_value=dict(READY,stored='DE')):
            with self.assertRaisesRegex(ValueError,'changed since'):
                lifecycle.software_action(store,host,'repair','wlan',[],False,plan)
        host.run.assert_not_called()

    def test_global_domain_is_independent_of_phy_and_bluetooth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cmdline=root/'cmdline.txt'
            cmdline.write_text('rootwait cfg80211.ieee80211_regdom=FI\n')
            for number,kind in enumerate(('wlan','bluetooth')):
                path=root/f'rfkill{number}'
                path.mkdir()
                for name,value in [('type',kind),('soft',str(number)),('hard',str(number))]:
                    (path/name).write_text(value+'\n')
            host=Mock()
            host.probe.side_effect=[Mock(returncode=0,stdout='global\ncountry FI: DFS-ETSI\nphy#0\ncountry 99: DFS-UNSET'),
                                    Mock(returncode=0,stdout='enabled\n')]
            with patch.object(wlan,'CMDLINE',cmdline), patch.object(wlan,'RFKILL',root):
                self.assertEqual(wlan.read_state(host),READY)
