"""Exercise existing Bash backend construction with all connections mocked."""
import json
import os
from pathlib import Path
import pty
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]


class BackendTests(unittest.TestCase):
    def script(self,body,password=False):
        with tempfile.TemporaryDirectory(prefix='rpi-share-backend-') as tmp:
            root=Path(tmp)
            script=r'''
source "$1"
CONFIG_FILE=$2
export TMPDIR=$3
TARGET_MP="$3/mock-mount"
BASE_MOUNT_DIR="$3/mock-base"
REMOTE_USER=example-user
TRACE="$3/trace.json"
prompt_remote_user_if_needed() { :; }
safe_unmount() { :; }
id() { echo 1000; }
sshfs() { /usr/bin/python3 -c 'import json,sys;json.dump(sys.argv[2:],open(sys.argv[1],"w"))' "$TRACE" "$@"; }
mount.cifs() { :; }
sudo() {
  /usr/bin/python3 -c 'import json,sys;json.dump(sys.argv[2:],open(sys.argv[1],"w"))' "$TRACE" "$@"
  if [[ $1 == mount ]]; then
    options=$7
    credential=${options#credentials=};credential=${credential%%,*}
    [[ $(stat -c %a "$credential") == 600 ]] || exit 22
    [[ -f $credential ]] || exit 23
    printf '%s' "$credential" > "$TMPDIR/credential-path"
  fi
}
open_path_or_url() { printf '%s' "$1" > "$TMPDIR/opened"; }
trap cleanup_current_session EXIT
''' + body
            master=slave=None
            try:
                if password:master,slave=pty.openpty()
                proc=subprocess.Popen(['bash','-c',script,'test',str(BASE/'bin/rpi-share'),str(BASE/'config/rpi-share.example.json'),tmp],stdin=slave if password else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                if password:
                    os.close(slave);slave=None;os.write(master,b'unit-test-password\n')
                stdout,stderr=proc.communicate(timeout=15)
                self.assertEqual(proc.returncode,0,stdout+stderr)
                trace=json.loads((root/'trace.json').read_text()) if (root/'trace.json').exists() else None
                if (root/'credential-path').exists():
                    credential=Path((root/'credential-path').read_text());self.assertFalse(credential.exists())
                    self.assertNotIn('unit-test-password',stdout+stderr+str(trace))
                opened=(root/'opened').read_text() if (root/'opened').exists() else None
                return trace,opened
            finally:
                if master is not None:os.close(master)
                if slave is not None:os.close(slave)

    def test_sshfs_direct_deep_destination_with_spaces(self):
        args,_=self.script('validate_config\nmount_sshfs staff-gw measurements\n')
        self.assertEqual(args[0],'example-user@staff-gateway.example.invalid:/srv/example/research/Project X/Measurements')

    def test_cifs_mounts_root_with_prefixpath_and_cleans_credentials(self):
        args,_=self.script('validate_config\nmount_cifs staff-gw smb-measurements\n',password=True)
        self.assertEqual(args[:4],['mount','-t','cifs','//staff-gateway.example.invalid/Research'])
        self.assertIn('prefixpath=Project X/Measurements',args[-1])

    def test_browse_uses_existing_smb_url(self):
        _,opened=self.script('validate_config\nmount_browse staff-gw browse\n')
        self.assertEqual(opened,'smb://storage.example.invalid/Research/')

    def test_existing_direct_cli_selection(self):
        _,opened=self.script('main --config "$CONFIG_FILE" -g staff-gw -s browse\n')
        self.assertEqual(opened,'smb://storage.example.invalid/Research/')

    def test_default_mapping_and_graphical_launch_failures(self):
        from test_rpi_share_catalog import legacy_example
        config=legacy_example()
        config['shares']['files']=dict(mount_type='browse',browse_url='smb://lab.example.invalid/Research/')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'catalog.json'
            path.write_text(json.dumps(config))
            path.chmod(0o600)
            for display,code,error in [('',1,'No graphical session'),(':1',1,'launch failed'),(':2',0,'')]:
                env=dict(os.environ,DISPLAY=display,WAYLAND_DISPLAY='')
                script='source "$1"; nemo() { [[ $DISPLAY == :2 ]]; }; main --config "$2"'
                result=subprocess.run(['bash','-c',script,'test',str(BASE/'bin/rpi-share'),path],
                                      input='\n',capture_output=True,text=True,env=env)
                self.assertEqual(result.returncode,code,result.stderr)
                self.assertEqual(result.stdout.count('Selected mapping:'),1,result.stdout)
                self.assertIn('Catalog visibility grants no access',result.stdout)
                self.assertIn('Opening browse view:',result.stdout)
                self.assertIn('smb://lab.example.invalid/Research/',result.stdout)
                self.assertIn(error,result.stderr)
                self.assertNotIn('Mounted successfully',result.stdout)

    def test_invalid_cli_ids_rejected_before_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            script='source "$1"; CONFIG_FILE=$2; validate_selection "bad\\\"name" root'
            result=subprocess.run(['bash','-c',script,'test',str(BASE/'bin/rpi-share'),str(BASE/'config/rpi-share.example.json')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('invalid gateway/share',result.stderr)


if __name__=='__main__':unittest.main()
