"""Optional actual LibreOffice round trips, with an isolated temporary profile."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'bin'))
import rpi_share_catalog as c
from test_rpi_share_catalog import equal_typed, legacy_example


@unittest.skipUnless(shutil.which('libreoffice'),'LibreOffice not installed; pure CSV interoperability tests remain available')
class CalcTests(unittest.TestCase):
    def roundtrip(self,name,config):
        with tempfile.TemporaryDirectory(prefix='rpi-share-calc-') as tmp:
            root=Path(tmp);source=root/(name+'.csv');source.write_text(c.export_csv(config),encoding='utf-8')
            sheets=root/'sheets';sheets.mkdir();output=root/'output';output.mkdir()
            runtime=root/'runtime';runtime.mkdir(mode=0o700)
            env=dict(os.environ,GSETTINGS_BACKEND='memory',XDG_RUNTIME_DIR=str(runtime),SAL_USE_VCLPLUGIN='svp')
            office=['libreoffice','-env:UserInstallation='+(root/'profile').as_uri(),'--headless','--norestore','--nodefault','--nofirststartwizard']
            # Both columns are Text. No numeric/date/formula interpretation.
            options='Text - txt - csv (StarCalc):44,34,76,1,1/2/2/2,0,true,false,false,false,false,0,false,false,false'
            first=subprocess.run(office+['--infilter='+options,'--convert-to','ods','--outdir',str(sheets),str(source)],capture_output=True,text=True,timeout=45,env=env)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            sheet=sheets/(name+'.ods');self.assertTrue(sheet.exists(),first.stdout+first.stderr)
            second=subprocess.run(office+['--convert-to','csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,false,false,false,false,0,false,false,false','--outdir',str(output),str(sheet)],capture_output=True,text=True,timeout=45,env=env)
            self.assertEqual(second.returncode,0,second.stdout+second.stderr)
            restored=c.validate(c.import_csv((output/(name+'.csv')).read_text(encoding='utf-8-sig')))
            equal_typed(self,config,restored)

    def test_actual_calc_legacy_roundtrip(self):
        for version in (1, '1.0'):
            with self.subTest(version=version):
                self.roundtrip('legacy',legacy_example(version))

    def test_actual_calc_unicode_types_and_precision(self):
        config=c.loads((BASE/'config/rpi-share.example.json').read_text())
        config['unknown']={'float':1.0,'big_integer':123456789012345678901234567890,'small':1.25e-50,'text':'00123','unicode':'Åäö 漢字','escaped':'comma, semicolon; "quotes"\nnew line','empty':'','null':None,'false':False}
        self.roundtrip('typed',config)


if __name__=='__main__':unittest.main()
