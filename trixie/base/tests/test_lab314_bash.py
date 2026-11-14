"""User-neutral real interactive Bash tests on disposable /tmp fixtures."""
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest

BASE=Path(__file__).resolve().parents[1]
INSTALL=BASE/'install'

def terminal(args,commands,env):
    master,slave=pty.openpty()
    p=subprocess.Popen(args,stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True)
    os.close(slave)
    output=b''
    try:
        # Wait for the first true prompt before sending test commands.
        until=time.monotonic()+8
        while time.monotonic()<until:
            if select.select([master],[],[],.2)[0]:
                output+=os.read(master,65536)
                if b'PROMPT_END ' in output:break
        else:raise AssertionError('No first prompt: '+repr(output))
        os.write(master,commands.encode()+b'\nexit\n')
        until=time.monotonic()+12
        while time.monotonic()<until:
            if select.select([master],[],[],.2)[0]:
                try:chunk=os.read(master,65536)
                except OSError:break
                if not chunk:break
                output+=chunk
            if p.poll() is not None:break
        p.wait(timeout=3)
        return p.returncode,output.decode(errors='replace')
    finally:
        if p.poll() is None:p.kill();p.wait()
        os.close(master)

class BashTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.prefix=self.root/'lab314'
        subprocess.run(['/usr/bin/python3','-m','venv','--without-pip',self.prefix],check=True)
        self.hook=self.root/'conda.sh'
        self.hook.write_text('''
__conda_reactivate() {
    reactivations=$((${reactivations:-0}+1))
    PS1="${PS1#"${CONDA_PROMPT_MODIFIER:-}"}"
    CONDA_PROMPT_MODIFIER="(lab314) "
    PS1="$CONDA_PROMPT_MODIFIER$PS1"
}
conda() {
    if [[ $1 == activate ]]; then
        activations=$((${activations:-0}+1))
        oldpath=$PATH
        export PATH="$2/bin:$PATH" CONDA_PREFIX="$2" CONDA_SHLVL=1
        __conda_reactivate
    else
        export PATH="${PATH#"$CONDA_PREFIX/bin:"}" CONDA_SHLVL=0
        unset CONDA_PREFIX
        PS1="${PS1#"$CONDA_PROMPT_MODIFIER"}"
        CONDA_PROMPT_MODIFIER=
    fi
}
''')
        self.runtime=self.root/'runtime.sh'
        s=(INSTALL/'lab314-bash.sh').read_text().replace('/opt/conda/etc/profile.d/conda.sh',str(self.hook)).replace('/opt/lab314',str(self.prefix))
        s=s.replace('/etc/profile.d/sci-path.sh',str(INSTALL/'sci-path.sh'))
        self.runtime.write_text(s)

    def shell(self,custom='',name='researcher',login=False,set_prompt=True):
        home=self.root/'unusual'/name;home.mkdir(parents=True,exist_ok=True)
        user=home/'.bashrc';user.write_text(("PS1='USER_PROMPT_END '\n" if set_prompt else "")+custom)
        before=user.read_bytes()
        rc=home/'system'
        rc.write_text(f"PS1='SYSTEM_PROMPT_END '\n"+f'. "{self.runtime}"\n. "{user}"\n')
        profile=home/'.bash_profile'
        profile.write_text(f'. "{rc}"\n')
        # A test login profile file sources the exact same user-independent
        # system fragment. It does not rewrite the host's /etc configuration.
        env={k:v for k,v in os.environ.items() if not k.startswith('CONDA_')}
        env.update(HOME=str(home),USER=name,LOGNAME=name,PATH='/usr/bin:/bin',TERM='xterm')
        commands=f"""[[ $CONDA_PREFIX == {str(self.prefix)!r} && $PS1 == "(lab314) "* ]] || exit 21
[[ $(command -v python) == {str(self.prefix/'bin/python')!r} && $(command -v python3) == {str(self.prefix/'bin/python3')!r} ]] || exit 22
[[ $activations == 1 && $CONDA_SHLVL == 1 ]] || exit 23
original_path=$PATH
conda deactivate
[[ -z ${{CONDA_PREFIX:-}} && $PS1 != "(lab314) "* && $(command -v python3) == /usr/bin/python3 ]] || exit 24
conda activate {str(self.prefix)!r}
[[ $PATH == "$original_path" && $CONDA_SHLVL == 1 ]] || exit 25
conda deactivate
[[ -z ${{CONDA_PREFIX:-}} ]] || exit 26
echo ACCEPTED
"""
        args=['bash','--noprofile','--rcfile',str(rc),'-i']
        # In tests, the login flag uses a dedicated rc loader because bash -l
        # resolves HOME from passwd on some hosts. Real login coverage is on Pi.
        if login:
            rc.write_text(f'. "{self.runtime}"\n. "{user}"\n. "{INSTALL}/sci-path.sh"\n')
        code,text=terminal(args,commands,env)
        self.assertEqual(code,0,text)
        self.assertIn('ACCEPTED',text)
        self.assertEqual(user.read_bytes(),before)
        first=text.split('[[',1)[0]
        self.assertIn('(lab314)',first,text)
        return text

    def test_plain_prompt(self):self.shell()
    def test_user_leaves_ps1_alone(self):self.shell(set_prompt=False)
    def test_other_user(self):self.shell(name='field_operator')
    def test_multiple_users(self):
        self.shell(name='one')
        self.shell(name='two')
    def test_non_home_directory(self):self.shell(name='external')
    def test_late_colored_prompt(self):
        self.shell("PS1='\\[\\e[32m\\]COLOR_PROMPT_END '\n")
    def test_repeated_runtime_source(self):
        self.shell(f'. "{self.runtime}"; . "{self.runtime}"\n')
    def test_empty_prompt_command(self):
        self.shell("PROMPT_COMMAND=''\n")
    def test_scalar_prompt_command(self):
        self.shell("PROMPT_COMMAND='PS1=USER_PROMPT_END\\ '\n")
    def test_array_prompt_command(self):
        self.shell("""PROMPT_COMMAND=('PS1=USER_PROMPT_END\\ ' 'echo user_hook')\n""")
    def test_separate_prompt_script(self):
        other=self.root/'theme';other.write_text("PS1='THEME_PROMPT_END '\nPROMPT_COMMAND=':'\n")
        self.shell(f'. "{other}"\n')
    def test_existing_conda_initialization(self):
        self.shell(f'. "{self.hook}"; conda activate "{self.prefix}"\n')
    def test_custom_path(self):
        self.shell('PATH="/usr/local/bin:$PATH"\n')
    def test_noninteractive(self):
        result=subprocess.run(['bash','--noprofile','--norc','-c',f'PATH=/usr/bin:/bin; . "{self.runtime}"; test -z "${{CONDA_PREFIX:-}}"; test "$PATH" = /usr/bin:/bin'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def install_root(self):
        tree=self.root/'image';(tree/'etc/profile.d').mkdir(parents=True)
        (tree/'etc/bash.bashrc').write_text('# system content\n')
        (tree/'etc/profile.d/conda-path.sh').write_text('export PATH=/opt/conda/bin:$PATH\n')
        return tree

    def test_installer_root_idempotence_and_uninstall(self):
        tree=self.install_root()
        cmd=['bash',str(INSTALL/'enable_lab314_autoactivate_rpi.sh'),'--root',str(tree)]
        subprocess.run(cmd,check=True)
        before={p:p.read_bytes() for p in tree.rglob('*') if p.is_file()}
        subprocess.run(cmd,check=True)
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertEqual(len(list((tree/'etc').glob('bash.bashrc.lab314-before.*'))),1)
        subprocess.run(['bash',INSTALL/'uninstall_rpi_autoactivate.sh','--root',tree],check=True)
        self.assertNotIn('LAB314 BEGIN',(tree/'etc/bash.bashrc').read_text())
        self.assertFalse((tree/'etc/profile.d/lab314-bash.sh').exists())

    def test_sudo_does_not_choose_a_user(self):
        tree=self.install_root()
        env=dict(os.environ,SUDO_USER='another_account',SUDO_UID='9999')
        subprocess.run(['bash',INSTALL/'enable_lab314_autoactivate_rpi.sh','--root',tree],env=env,check=True)
        self.assertFalse((tree/'home').exists())

if __name__=='__main__':unittest.main()
