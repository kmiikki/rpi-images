"""Regression checks for the ARM64 lab314 installer."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]

class Lab314Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.bin=self.root/'bin';self.bin.mkdir()
        u=self.bin/'uname';u.write_text('#!/bin/sh\necho aarch64\n');u.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.bin)+':/usr/bin:/bin')

    def run_installer(self,prefix):
        return subprocess.run(['bash',BASE/'install/create_lab314_env.sh','--prefix',prefix],
                              env=self.env,capture_output=True,text=True)

    def test_existing_broken_prefix_preserved(self):
        prefix=self.root/'old';prefix.mkdir()
        marker=prefix/'do-not-delete';marker.write_text('evidence')
        result=self.run_installer(prefix)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(marker.read_text(),'evidence')
        self.assertEqual(list(prefix.iterdir()),[marker])

    def test_existing_prefix_updated_not_recreated(self):
        prefix=self.root/'ok';(prefix/'bin').mkdir(parents=True)
        py=prefix/'bin/python';py.write_text('#!/bin/sh\nexit 0\n');py.chmod(0o755)
        (prefix/'conda-meta').mkdir()
        before=py.stat().st_ctime_ns
        result=self.run_installer(prefix)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Update completed',result.stdout)
        self.assertEqual(py.stat().st_ctime_ns,before)

    def test_wrong_version_prefix_preserved(self):
        prefix=self.root/'old';(prefix/'bin').mkdir(parents=True)
        (prefix/'bin/python').symlink_to('/usr/bin/python3')
        (prefix/'conda-meta').mkdir()
        result=self.run_installer(prefix)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Run with the selected lab314 Python',result.stderr)
        self.assertTrue((prefix/'bin/python').is_symlink())

    def test_invalid_prefix(self):
        self.assertNotEqual(self.run_installer(Path('../invalid')).returncode,0)

    def test_contract_has_required_science(self):
        p=json.loads((BASE/'config/lab314/packages.json').read_text())
        names={n.lower().replace('_','-') for n in p['packages']}
        self.assertTrue(set('shapely numpy scipy sympy statsmodels scikit-learn numba uncertainties pint xarray netcdf4 jupyterlab xlsxwriter'.split())<=names)
        self.assertEqual(p['python'],'3.14.10')
        self.assertEqual(p['packages']['opencv-python'],'5.0.0.93')
        self.assertEqual(p['packages']['spyder-kernels'],'3.0.5')

    def test_all_wheels_have_hashes_and_no_headless(self):
        lines=(BASE/'config/lab314/wheels.txt').read_text().splitlines()
        self.assertGreater(len(lines),100)
        for line in lines:
            self.assertIn(' --hash=sha256:',line)
            self.assertNotIn('x86_64',line)
        self.assertFalse(any(l.startswith('opencv-python-headless ') for l in lines))

    def test_wrong_architecture_rejected_before_creation(self):
        (self.bin/'uname').write_text('#!/bin/sh\necho x86_64\n')
        prefix=self.root/'new'
        self.assertNotEqual(self.run_installer(prefix).returncode,0)
        self.assertFalse(prefix.exists())

if __name__=='__main__':
    unittest.main()
