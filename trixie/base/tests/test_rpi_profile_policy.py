"""Real shell policy execution against temporary files and mocked OS commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]


class ShellPolicyTests(unittest.TestCase):
    def test_profile_ntp_and_ssh_policies_on_temporary_files(self):
        for profile,ntp in [('GENERAL','pool.ntp.org time.cloudflare.com'),('HOME','time.mikes.fi'),('AALTO','ntp.aalto.fi')]:
            with self.subTest(profile=profile),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=(BASE/'install/pre_profile.sh').read_text()
                source=source.replace('[[ $EUID == 0 && $# == 1 ]]','[[ $# == 1 ]]')
                source=source.replace('/etc/systemd/timesyncd.conf.d',str(root/'timesync'))
                file=root/'pre_profile.sh';file.write_text(source)
                env=dict(os.environ,PRIMARY_USER='example',PRE_ACCOUNTS_MANAGED='1',SSH_POLICY='keep')
                env.pop('NTP_PRIMARY',None)
                script='systemctl() { :; }; timedatectl() { if [[ $1 == show ]]; then echo yes; fi; }; apt-get() { exit 88; }; export -f systemctl timedatectl apt-get; bash "$1" "$2"'
                result=subprocess.run(['bash','-c',script,'test',str(file),profile],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('NTP='+ntp+'\n',(root/'timesync/60-rpi-scientific.conf').read_text())

    def policy(self,root,valid=True):
        source=(BASE/'install/account-policy.sh').read_text().replace('/etc/sudoers.d',str(root))
        file=root/'policy.sh';file.write_text(source)
        script='source "$1"; id() { return 0; }; visudo() { return '+('0' if valid else '1')+'; }; configure_passwordless_sudo_user example'
        return subprocess.run(['bash','-c',script,'test',str(file)],capture_output=True,text=True)

    def test_passwordless_policy_and_repeat_preserve_exact_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=self.policy(root);self.assertEqual(result.returncode,0,result.stderr)
            output=root/'010_example-nopasswd';self.assertEqual(output.read_text(),'example ALL=(ALL) NOPASSWD: ALL\n')
            self.assertEqual(output.stat().st_mode & 0o777,0o440);inode=output.stat().st_ino
            self.assertEqual(self.policy(root).returncode,0);self.assertEqual(output.stat().st_ino,inode)

    def test_invalid_policy_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'010_example-nopasswd';output.write_text('old policy\n')
            self.assertNotEqual(self.policy(root,False).returncode,0)
            self.assertEqual(output.read_text(),'old policy\n')
            self.assertFalse(list(root.glob('.rpi-policy.*')))


class LegacyAaltoTests(unittest.TestCase):
    def legacy(self,overrides=None,wrapper=False,arguments=()):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);log=root/'calls';result_file=root/'resolved'
            # Execute the real legacy guard and pure account module. Every possible
            # provisioning target is a temporary recording stub, never host code.
            for name in ('pre_aalto.sh','rpi_accounts.py','run_rpi_aalto.sh'):
                (root/name).write_bytes((BASE/'install'/name).read_bytes())
            (root/'pre_profile.sh').write_text('printf "%s|%s|%s\n" "$1" "$PRIMARY_USER" "$EXTRA_SUDO_USERS" > "$POLICY_RESULT"\nprintf "pre\n" >> "$POLICY_LOG"\n')
            for name in ('install_rpi_base.sh','install_conda_base.sh','create_lab314_env.sh','enable_lab314_autoactivate_rpi.sh','install_envrun.sh','verify_rpi_lab314.sh'):
                (root/name).write_text('printf "%s\n" "'+name+'" >> "$POLICY_LOG"\n')
            env=dict(os.environ,PRIMARY_USER='chem',POLICY_RESULT=str(result_file),POLICY_LOG=str(log),PYTHONDONTWRITEBYTECODE='1')
            for name in ('PRIMARY_USER','EXTRA_SUDO_USERS','PRE_ACCOUNTS_MANAGED','NTP_PRIMARY','SSH_POLICY'):env.pop(name,None)
            env.update(overrides or {})
            result=subprocess.run(['bash',str(root/('run_rpi_aalto.sh' if wrapper else 'pre_aalto.sh')),*arguments],env=env,capture_output=True,text=True)
            return result,result_file.read_text().strip() if result_file.exists() else None,log.read_text().splitlines() if log.exists() else []

    def test_legacy_unsupported_school_arguments_fail_before_any_stage(self):
        for wrapper in (False,True):
            result,plan,calls=self.legacy(wrapper=wrapper,arguments=('--school','custom'))
            self.assertNotEqual(result.returncode,0);self.assertIsNone(plan);self.assertEqual(calls,[])

    def test_legacy_default_policy_includes_maintenance(self):
        result,plan,calls=self.legacy()
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(plan,'AALTO|chem|chem-it');self.assertEqual(calls,['pre'])

    def test_legacy_optional_accounts_complement_required_account(self):
        for extra in ('admin2','chem-it admin2','admin2 chem-it'):
            result,plan,calls=self.legacy({'PRIMARY_USER':'researcher','EXTRA_SUDO_USERS':extra})
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(plan,'AALTO|researcher|chem-it admin2');self.assertEqual(calls,['pre'])

    def test_legacy_invalid_explicit_overrides_fail_before_any_stage(self):
        invalid=[{'EXTRA_SUDO_USERS':''},{'EXTRA_SUDO_USERS':'  '},{'PRIMARY_USER':''},{'PRIMARY_USER':'root'},{'PRIMARY_USER':'chem-it'},{'EXTRA_SUDO_USERS':'bad;user'},{'EXTRA_SUDO_USERS':'admin2 admin2'}]
        for overrides in invalid:
            for wrapper in (False,True):
                with self.subTest(overrides=overrides,wrapper=wrapper):
                    result,plan,calls=self.legacy(overrides,wrapper)
                    self.assertNotEqual(result.returncode,0);self.assertIsNone(plan);self.assertEqual(calls,[])

    def test_legacy_managed_path_cannot_bypass_maintenance_validation(self):
        result,plan,calls=self.legacy({'PRE_ACCOUNTS_MANAGED':'1','EXTRA_SUDO_USERS':''})
        self.assertNotEqual(result.returncode,0);self.assertIsNone(plan);self.assertEqual(calls,[])

    def test_legacy_full_wrapper_starts_with_the_validated_policy(self):
        result,plan,calls=self.legacy(wrapper=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(plan,'AALTO|chem|chem-it')
        self.assertEqual(calls,['pre','install_rpi_base.sh','install_conda_base.sh','create_lab314_env.sh','enable_lab314_autoactivate_rpi.sh','install_envrun.sh','verify_rpi_lab314.sh'])


if __name__=='__main__':unittest.main()
