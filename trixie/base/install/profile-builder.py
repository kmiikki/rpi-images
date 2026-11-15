#!/usr/bin/env python3
"""Create and inspect reusable installation preferences without provisioning."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

import installation_profiles as profiles
import setup_rpi as setup


def preview(data,host=None):
    host=host or setup.Host()
    # Creation is simulated only. This choice is never stored or used for apply.
    a=setup.parser().parse_args(profiles.arguments(data)+['--plan','--recovery','create'])
    state=host.snapshot();plan=setup.resolve(a,state,host)
    print('PREVIEW ONLY; missing accounts are shown as planned creations, not authorized.')
    print(json.dumps(plan,indent=2,ensure_ascii=False,default=str))
    print('Primary administrator: existing approved NOPASSWD: ALL policy.')
    print('Additional accounts: sudo group; no new per-user NOPASSWD rule.')
    for name,detail in setup.stages(a,plan):print(name+': '+detail)
    return plan


def leaves(value,prefix=()):
    for key,item in value.items():
        path=prefix+(key,)
        if isinstance(item,dict):yield from leaves(item,path)
        else:yield path,item


def edit(data):
    rows=[(('name',),data['name']),(('base',),data['base'])]+list(leaves(data['settings'],('settings',)))
    print('Select a setting. null means the original base/host default; lists use JSON arrays.')
    for i,(path,value) in enumerate(rows,1):print(f'{i}. {".".join(path)} = {json.dumps(value,ensure_ascii=False)}')
    choice=input('Setting number (Enter cancels): ').strip()
    if not choice:return data
    index=int(choice)-1
    if not 0<=index<len(rows):raise ValueError('unknown setting number')
    path,_=rows[index];raw=input('New value (JSON, or unquoted text for a string): ')
    try:value=json.loads(raw)
    except json.JSONDecodeError:value=raw
    result=copy.deepcopy(data);target=result
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    if path==('settings','share','source'):
        target['path']=input('Absolute catalog path: ').strip() if value in ('json','csv') else None
    return profiles.validate(result)


def menu():
    data=None
    while True:
        print('\nInstallation profile builder — no system changes')
        print('1. Create/export base profile\n2. Load JSON\n3. Edit setting\n4. Validate\n5. Preview effective plan\n6. Save JSON\n0. Exit')
        try:
            choice=input('Choice: ').strip()
            if choice=='0':return 0
            if choice=='1':data=profiles.builtin(input('Base GENERAL / HOME / AALTO: ').strip().upper())
            elif choice=='2':data=profiles.load(Path(input('Profile path: ').strip()).expanduser())
            elif choice in ('3','4','5','6'):
                if data is None:raise ValueError('create or load a profile first')
                if choice=='3':data=edit(data)
                elif choice=='4':profiles.validate(data);print('VALID')
                elif choice=='5':preview(data)
                else:
                    path=Path(input('Save outside Git, e.g. ~/my-installation.json: ').strip()).expanduser()
                    replace=False
                    if path.exists():
                        print('Existing file will be replaced only with explicit confirmation.')
                        replace=input('Type REPLACE to overwrite this file: ')=='REPLACE'
                        if not replace:print('Cancelled; existing file retained.');continue
                    profiles.save(path,data,replace);print('Saved '+str(path))
            else:print('Select a listed number.')
        except (ValueError,OSError,subprocess.SubprocessError) as exc:print('Error: '+str(exc))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    action=p.add_mutually_exclusive_group()
    action.add_argument('--export',choices=['GENERAL','HOME','AALTO'],metavar='BASE')
    action.add_argument('--validate',type=Path,metavar='PROFILE')
    action.add_argument('--preview',type=Path,metavar='PROFILE')
    p.add_argument('--output',type=Path,help='export destination; choose a path outside Git for private settings')
    p.add_argument('--replace',action='store_true',help='explicitly allow replacing an export destination')
    a=p.parse_args(argv)
    if a.export:
        if not a.output:p.error('--export requires --output')
        profiles.save(a.output,profiles.builtin(a.export),a.replace);print('Saved '+str(a.output));return 0
    if a.output or a.replace:p.error('--output and --replace require --export')
    if a.validate:profiles.load(a.validate);print('VALID');return 0
    if a.preview:preview(profiles.load(a.preview));return 0
    if not sys.stdin.isatty():p.error('interactive menu requires a terminal; use --export, --validate or --preview')
    return menu()


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:sys.exit('Error: '+str(exc))
