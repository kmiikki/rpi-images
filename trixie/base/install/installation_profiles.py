"""Version 1 installation preferences; no credentials or apply authorizations."""
import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile

import rpi_accounts as accounts

COMPONENTS=('system','conda','lab314','spyder','hardware','wolfram','share','imaging')
DEFAULTS=dict(primary_user=None,additional_users=None,hostname=None,ssh=None,
              ntp_servers=None,lab_prefix='/opt/lab314',ide_prefix=None,
              components={name:None for name in COMPONENTS},
              share=dict(source='auto',path=None,users=[],prefix=None,default_group=None),
              imaging=dict(source=None,apps=[]))


def builtin(base):
    return validate(dict(version=1,name=base,base=base,settings=copy.deepcopy(DEFAULTS)))


def keys(obj,expected,where):
    if not isinstance(obj,dict) or set(obj)!=set(expected):
        raise ValueError(where+': exactly these fields are required: '+', '.join(expected))


def text(value,where,nullable=False):
    if nullable and value is None:return
    if not isinstance(value,str) or not value or any(ord(c)<32 for c in value):
        raise ValueError(where+': nonempty text without control characters required')


def username(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',value) or value in ('root','nobody'):
        raise ValueError('invalid local username')


def strings(value,where,check=text,nullable=False):
    if nullable and value is None:return
    if not isinstance(value,list):raise ValueError(where+': array required')
    for item in value:
        if check is text:check(item,where)
        else:check(item)
    if len(set(value))!=len(value):raise ValueError(where+': duplicate values')


def absolute(value,where,nullable=False):
    if nullable and value is None:return
    text(value,where)
    p=Path(value)
    if not p.is_absolute() or p==Path('/') or p!=p.resolve():
        raise ValueError(where+': canonical absolute path required')


def ntp_server(value):
    text(value,'NTP server')
    if not re.fullmatch(r'[A-Za-z0-9.:-]+',value):raise ValueError('invalid NTP hostname or IP address')
    try:ipaddress.ip_address(value);return value
    except ValueError:pass
    if len(value)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',x) for x in value.removesuffix('.').split('.')):
        raise ValueError('invalid NTP hostname or IP address')
    return value


def validate(data):
    keys(data,('version','name','base','settings'),'profile')
    if type(data['version']) is not int or data['version']!=1:raise ValueError('unsupported profile version')
    text(data['name'],'name')
    if data['base'] not in ('GENERAL','HOME','AALTO'):raise ValueError('unsupported base profile')
    s=data['settings'];keys(s,DEFAULTS,'settings')
    if s['primary_user'] is not None:username(s['primary_user'])
    strings(s['additional_users'],'additional_users',username,True)
    if s['additional_users'] and s['primary_user'] in s['additional_users']:raise ValueError('duplicate primary/additional user')
    if data['base']=='AALTO':accounts.aalto_account_plan(s['primary_user'],s['additional_users'])
    if s['hostname'] is not None:
        text(s['hostname'],'hostname')
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',s['hostname']):raise ValueError('invalid hostname')
    if s['ssh'] not in (None,'keep','enable','disable'):raise ValueError('invalid SSH policy')
    strings(s['ntp_servers'],'ntp_servers',ntp_server,True)
    if s['ntp_servers']==[]:raise ValueError('NTP list must be nonempty or null for base defaults')
    absolute(s['lab_prefix'],'lab_prefix');absolute(s['ide_prefix'],'ide_prefix',True)
    keys(s['components'],COMPONENTS,'components')
    for value in s['components'].values():
        if value is not None and type(value) is not bool:raise ValueError('component values must be boolean or null')
    c=s['components']
    if data['base'] in ('HOME','AALTO') and c['share'] is False:raise ValueError('HOME/AALTO require rpi-share')
    if s['ide_prefix'] and c['spyder'] is False:raise ValueError('IDE prefix requires Spyder')
    prefixes=[Path(p) for p in (s['lab_prefix'],s['ide_prefix']) if p]
    protected=[Path(p) for p in ('/opt/conda','/opt/rpi','/opt/sci')]
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a in prefixes for b in protected) or (len(prefixes)>1 and (prefixes[0].is_relative_to(prefixes[1]) or prefixes[1].is_relative_to(prefixes[0]))):raise ValueError('overlapping environment prefixes')
    share=s['share'];keys(share,DEFAULTS['share'],'share')
    if share['source'] not in ('auto','later','json','csv','example'):raise ValueError('invalid share source')
    absolute(share['path'],'share.path',True)
    if (share['source'] in ('json','csv'))!=(share['path'] is not None):raise ValueError('share path required only for JSON/CSV source')
    strings(share['users'],'share.users',username);absolute(share['prefix'],'share.prefix',True)
    text(share['default_group'],'share.default_group',True)
    if share['default_group'] and share['source'] in ('auto','later'):raise ValueError('default group requires an explicit share catalog')
    selected_share=c['share'] if c['share'] is not None else data['base']!='GENERAL'
    if share['source'] not in ('auto','later') and not selected_share:raise ValueError('catalog requires rpi-share')
    imaging=s['imaging'];keys(imaging,DEFAULTS['imaging'],'imaging')
    absolute(imaging['source'],'imaging.source',True);strings(imaging['apps'],'imaging.apps')
    return data


def unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key: '+key)
        result[key]=value
    return result


def load(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=unique_pairs,
                              parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON number'))))


def save(path,data,replace=False):
    validate(data);path=Path(path)
    if path.is_symlink():raise ValueError('symlinked profile destination refused')
    payload=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    fd,tmp=tempfile.mkstemp(prefix='.profile-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        if replace:os.replace(tmp,path)
        else:os.link(tmp,path)  # atomic no-clobber; existing files are never truncated
    finally:Path(tmp).unlink(missing_ok=True)


def arguments(data):
    validate(data);s=data['settings'];argv=[]
    def option(name,value):argv.append('--'+name+'='+str(value))
    option('profile',data['base'])
    for key in ('primary_user','hostname','ssh','lab_prefix','ide_prefix'):
        if s[key] is not None:option(key.replace('_','-'),s[key])
    if s['additional_users'] is not None:
        if not s['additional_users']:argv.append('--no-additional-users')
        for user in s['additional_users']:option('additional-user',user)
    for server in s['ntp_servers'] or []:option('ntp-server',server)
    for name,value in s['components'].items():
        if value is not None:argv.append('--'+('' if value else 'no-')+name)
    share=s['share'];source=share['source']
    if source in ('json','csv'):option('share-'+source,share['path'])
    elif source!='auto':argv.append('--share-'+source)
    for user in share['users']:option('share-user',user)
    for key in ('prefix','default_group'):
        if share[key] is not None:option('share-prefix' if key=='prefix' else 'default-group',share[key])
    if s['imaging']['source']:option('imaging-source',s['imaging']['source'])
    for app in s['imaging']['apps']:option('imaging-app',app)
    return argv


def parse_arguments(parser,argv):
    """Explicit CLI groups replace profile groups, including repeated options."""
    argv=list(argv);a=parser.parse_args(argv)
    if not a.profile_file:return a
    values=parser.parse_args(arguments(load(a.profile_file)))
    explicit=set()
    for token in argv:
        option=token.split('=',1)[0]
        action=parser._option_string_actions.get(option)
        if action:explicit.add(action.dest)
        elif parser.allow_abbrev and option.startswith('--'):
            explicit.update(action.dest for flag,action in parser._option_string_actions.items() if flag.startswith(option))
    groups=[{'additional_user','no_additional_users'},
            {'share_json','share_csv','share_example','share_later'}]
    for group in groups:
        if group & explicit:explicit.update(group)
    if 'share_later' in explicit and a.share_later:
        explicit.add('default_group')  # A deferred catalog cannot carry an active group override.
    for key,value in vars(values).items():
        if key not in explicit and key!='profile_file':setattr(a,key,value)
    return a
