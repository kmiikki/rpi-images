#!/usr/bin/env python3
"""Offline rpi-share validation, lossless JSON/CSV interchange and navigation."""
import argparse
import csv
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from urllib.parse import quote, urlsplit

IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')
CREDENTIALS = {'password', 'passwd', 'passphrase', 'token', 'secret', 'credentials', 'private_key', 'password_hash', 'api_key', 'apikey', 'access_token', 'auth_token', 'secret_key', 'ssh_private_key'}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: '+key)
        result[key] = value
    return result


def loads(text):
    def constant(value):
        raise Invalid('non-finite JSON number: '+value)
    return json.loads(text, object_pairs_hook=unique, parse_constant=constant)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def same_value(a,b):
    """Structural JSON equality including boolean/integer/float distinctions."""
    if type(a) is not type(b):return False
    if isinstance(a,dict):return set(a)==set(b) and all(same_value(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(same_value(x,y) for x,y in zip(a,b))
    return a==b


def no_credentials(value, location=''):
    if isinstance(value, dict):
        for key, item in value.items():
            require(key.lower().replace('-', '_') not in CREDENTIALS,
                    'credential-bearing field is unsupported: '+location+'/'+key)
            no_credentials(item, location+'/'+key)
    elif isinstance(value, list):
        for item in value:
            no_credentials(item, location)
    elif isinstance(value,float):
        require(math.isfinite(value),'non-finite JSON number at '+location)


def labels(value, where):
    require(isinstance(value, list) and all(isinstance(x, str) and x for x in value), where+' must be a string array')
    require(len(set(value)) == len(value), where+' contains duplicate groups')


def remote_path(value, where):
    require(isinstance(value, str) and value.startswith('/') and not any(c in value for c in '\r\n\0'), where+' must be an absolute remote path')
    require('..' not in PurePosixPath(value).parts, where+' must not contain parent traversal')


def validate(config):
    require(isinstance(config, dict), 'configuration must be a JSON object')
    no_credentials(config)
    version = config.get('version')
    require(type(version) in (str, int, float) and str(version) in ('1','1.0','2','2.0'), 'unsupported configuration version')
    for key in ('defaults','gateways','shares'):
        require(isinstance(config.get(key), dict), key+' must be an object')
    require(config['gateways'] and config['shares'], 'at least one gateway and destination is required')
    nodes = config.get('nodes', {})
    require(isinstance(nodes, dict), 'nodes must be an object')
    group_defs = config.get('groups', {})
    require(isinstance(group_defs, dict), 'groups must be an object')
    known_groups = {'all','staff','students'} | set(group_defs)
    for group in group_defs:
        require(IDENT.fullmatch(group), 'invalid group ID: '+group)
    for kind in ('gateways','shares','nodes'):
        for key, item in config.get(kind, {}).items():
            require(IDENT.fullmatch(key) and key not in ('.','..'), 'invalid '+kind+' ID: '+key)
            require(isinstance(item, dict), kind+'/'+key+' must be an object')
            for field in ('name','description'):
                if item.get(field) is not None: require(isinstance(item[field], str), key+'/'+field+' must be a string')
            if item.get('allowed_groups') is not None: labels(item['allowed_groups'], key+'/allowed_groups')
            if item.get('groups') is not None:
                labels(item['groups'], key+'/groups')
                require(set(item['groups']) <= known_groups, key+' references an undefined navigation group')
    for key, gateway in config['gateways'].items():
        host = gateway.get('host')
        require(isinstance(host, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', host), 'invalid gateway host: '+key)
        if gateway.get('default_user') is not None:
            require(isinstance(gateway['default_user'], str) and not any(c in gateway['default_user'] for c in '\r\n\0'), 'invalid default_user')
        if gateway.get('domain') is not None:
            require(isinstance(gateway['domain'], str) and not any(c in gateway['domain'] for c in '\r\n\0'), 'invalid CIFS domain')
    for key, share in config['shares'].items():
        kind = share.get('mount_type')
        require(kind in ('sshfs','cifs','browse'), 'unsupported mount_type: '+key)
        if share.get('explicit_only') is not None: require(type(share['explicit_only']) is bool, key+'/explicit_only must be boolean')
        if share.get('remote_path') is not None: remote_path(share['remote_path'], key+'/remote_path')
        require(share.get('paths') is None or isinstance(share['paths'],dict),key+'/paths must be an object or null')
        paths = share.get('paths') or {}
        require(isinstance(paths, dict) and set(paths) <= set(config['gateways']), key+' has unknown gateway paths')
        for gateway, value in paths.items(): remote_path(value, key+'/paths/'+gateway)
        if kind != 'browse':
            require(share.get('remote_path') or paths or share.get('share_root'), key+' has no remote destination')
        require(share.get('browse_url') is None or isinstance(share['browse_url'],str),'browse_url must be a string or null')
        if share.get('browse_url'):
            u = urlsplit(share['browse_url'])
            require(u.scheme == 'smb' and u.hostname and not u.username and not u.password and not any(c in share['browse_url'] for c in '\r\n\0'), 'browse_url must be an SMB URL without credentials')
        if share.get('cifs_options') is not None:
            options = share['cifs_options']
            require(isinstance(options, str) and not any(c in options for c in '\r\n\0'), 'invalid cifs_options')
            require(not re.search(r'(?i)(?:^|,)\s*(?:pass(?:word)?2?|credentials|cred|username|user|domain)\s*=', options), 'credentials and identity belong to runtime fields, not cifs_options')
        if kind == 'cifs':
            for gateway in config['gateways']:
                if share.get('remote_path') or gateway in paths or share.get('share_root'):
                    mapping(config, gateway, key)
    combined = {**nodes, **config['shares']}
    require(not (set(nodes) & set(config['shares'])), 'node and destination IDs must be distinct')
    for key, item in combined.items():
        parent = item.get('parent')
        require(parent is None or isinstance(parent, str) and parent in combined, 'unknown parent for '+key)
        seen = {key}
        while parent is not None:
            require(isinstance(parent,str) and parent in combined, 'unknown parent for '+key)
            require(parent not in seen, 'hierarchy cycle at '+key)
            seen.add(parent); parent = combined[parent].get('parent')
            require(len(seen) <= 128, 'hierarchy exceeds 128 levels')
    defaults = config['defaults']
    require(defaults.get('gateway') in config['gateways'], 'unknown default gateway')
    require(defaults.get('share') in config['shares'], 'unknown default destination')
    if defaults.get('group') is not None: require(defaults['group'] in known_groups, 'unknown default navigation group')
    if defaults.get('additional_groups') is not None:
        labels(defaults['additional_groups'], 'defaults/additional_groups')
        require(set(defaults['additional_groups']) <= known_groups, 'unknown additional default group')
    # This is local consistency only; mapping does not contact a server.
    mapping(config, defaults['gateway'], defaults['share'])
    return config


def mapping(config, gateway, share):
    require(gateway in config['gateways'] and share in config['shares'], 'unknown gateway/destination')
    item = config['shares'][share]; host = config['gateways'][gateway]['host']
    kind = item.get('mount_type')
    path = (item.get('paths') or {}).get(gateway, item.get('remote_path'))
    if kind == 'browse':
        return {'type':kind,'remote':item.get('browse_url') or 'smb://'+host+'/'+quote((path or '').lstrip('/'), safe='/'), 'options':''}
    if kind == 'sshfs':
        require(path, 'destination is not configured for this gateway')
        return {'type':kind,'remote':host+':'+path,'path':path,'options':''}
    require(kind == 'cifs', 'unsupported mount type')
    root = item.get('share_root')
    require(root is None or not (path or item.get('paths')), 'conflicting CIFS share_root and remote_path/paths definitions')
    subdir = item.get('subdir') if item.get('subdir') is not None else ''
    require(isinstance(subdir, str), 'CIFS subdir must be a string')
    if root is None:
        require(path, 'destination is not configured for this gateway')
        parts = path.strip('/').split('/', 1); root=parts[0]
        subdir = '/'.join(x for x in (parts[1] if len(parts)>1 else '', subdir) if x)
    require(isinstance(root, str) and re.fullmatch(r'[^/\\,\r\n\0]+', root), 'CIFS share_root must be a single share name')
    require(not subdir.startswith(('/', '\\')) and not any(c in subdir for c in ',\r\n\0\\') and '..' not in subdir.split('/'), 'invalid CIFS relative subdirectory')
    options = item.get('cifs_options') if item.get('cifs_options') is not None else 'iocharset=utf8,vers=3.0,noserverino'
    require(not subdir or not re.search(r'(?i)(?:^|,)\s*prefixpath\s*=',options),'conflicting CIFS subdirectory and prefixpath option')
    if subdir: options = ','.join(x for x in (options,'prefixpath='+subdir) if x)
    return {'type':kind,'remote':'//'+host+'/'+root,'options':options,'path':'/'+root+('/'+subdir if subdir else '')}


def pointer(parts):
    return ''.join('/'+str(p).replace('~','~0').replace('/','~1') for p in parts)


def unpointer(text):
    require(text == '' or text.startswith('/'), 'path must be a JSON Pointer')
    require(not re.search(r'~(?![01])', text), 'invalid JSON Pointer escape')
    parts=tuple(p.replace('~1','/').replace('~0','~') for p in text[1:].split('/')) if text else ()
    require(len(parts)<=128, 'CSV path exceeds 128 levels')
    return parts


def export_csv(config):
    stream=io.StringIO(newline=''); writer=csv.writer(stream, lineterminator='\n')
    writer.writerow(['path','json_value'])
    def walk(value, parts):
        writer.writerow([pointer(parts), json_text({} if isinstance(value,dict) else [] if isinstance(value,list) else value)])
        if isinstance(value,dict):
            for key in sorted(value): walk(value[key], (*parts,key))
        elif isinstance(value,list):
            for index, item in enumerate(value): walk(item,(*parts,str(index)))
    walk(config,()); return stream.getvalue()


def import_csv(text):
    text=text.lstrip('\ufeff')
    first=text.splitlines()[0] if text.splitlines() else ''
    try:
        dialect=csv.Sniffer().sniff(first, delimiters=',;\t')
        reader=csv.reader(io.StringIO(text,newline=''), delimiter=dialect.delimiter,
                          quotechar='"', doublequote=True, strict=True)
        header=next(reader)
        require([v.strip() for v in header]==['path','json_value'], 'CSV columns must be path,json_value')
        values={}
        for row in reader:
            if not row: continue
            require(len(row)==2, 'CSV row '+str(reader.line_num)+' must have two columns')
            parts=unpointer(row[0]);require(parts not in values,'duplicate CSV path: '+row[0])
            values[parts]=loads(row[1]); require(len(values)<=100000,'CSV exceeds 100000 values')
    except (csv.Error, StopIteration) as exc:
        raise Invalid('malformed CSV: '+str(exc)) from exc
    require(() in values, 'CSV must contain the root object row (empty path)')
    children={p:[] for p in values}
    for parts in values:
        if parts:
            require(parts[:-1] in values, 'missing parent row: '+pointer(parts[:-1]))
            children[parts[:-1]].append(parts)
    def build(parts):
        value=values[parts]; descendants=children[parts]
        if descendants:
            require(value=={} or value==[], 'parent with children must use {} or [] marker: '+pointer(parts))
            if isinstance(value,dict): return {p[-1]:build(p) for p in sorted(descendants)}
            require(all(re.fullmatch(r'0|[1-9][0-9]*',p[-1]) for p in descendants), 'array indices must be decimal integers')
            ordered=sorted(descendants,key=lambda p:int(p[-1]))
            require([int(p[-1]) for p in ordered]==list(range(len(ordered))), 'array indices must be contiguous from zero')
            return [build(p) for p in ordered]
        return value
    return build(())


def atomic_write(path, data, force=False):
    path=Path(path)
    require(path.parent.is_dir() and not path.is_symlink(), 'output parent must exist and output must not be a symlink')
    if path.exists():
        require(path.is_file(), 'output must be a regular file')
        require(force, 'output exists; use --force after reviewing the replacement')
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,0o600)
        if force:
            require(not path.is_symlink(), 'symlinked output refused')
            os.replace(tmp,path)
        else:
            os.link(tmp,path)  # Atomic no-clobber even if another writer wins.
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        Path(tmp).unlink(missing_ok=True)


def selected_groups(config, requested):
    groups=requested or [config['defaults'].get('group') or 'all',*(config['defaults'].get('additional_groups') or [])]
    known={'all','staff','students'} | set(config.get('groups',{}))
    require(set(groups)<=known,'unknown navigation group')
    return set(groups)


def visible(item, groups):
    return 'all' in groups or not item.get('groups') or 'all' in item['groups'] or bool(set(item['groups']) & groups)


def tree_lines(config, groups, full=False, explicit=False):
    items={**config.get('nodes',{}),**config['shares']}; shown=set()
    for key,item in items.items():
        if full or (visible(item,groups) and (explicit or not item.get('explicit_only',False))):
            shown.add(key);parent=item.get('parent')
            while parent is not None: shown.add(parent);parent=items[parent].get('parent')
    def walk(parent, depth):
        for key in sorted(k for k,v in items.items() if v.get('parent')==parent and k in shown):
            item=items[key];kind='category' if key not in config['shares'] else item['mount_type']
            yield '  '*depth+key+' — '+(item.get('name') or item.get('description') or key)+' ['+kind+('; explicit-only' if item.get('explicit_only') else '')+']'
            yield from walk(key,depth+1)
    return list(walk(None,0))


def runtime_cli(argv):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['validate','tree','menu','mapping'])
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--group',action='append',default=[])
    p.add_argument('--full',action='store_true');p.add_argument('--admin',action='store_true')
    p.add_argument('--gateway');p.add_argument('--share')
    a=p.parse_args(argv);config=validate(loads(a.config.read_text(encoding='utf-8-sig')))
    if a.operation=='validate':return
    groups=selected_groups(config,a.group)
    if a.operation=='tree': print('\n'.join(tree_lines(config,groups,a.full,a.admin)))
    elif a.operation=='mapping': print(json.dumps(mapping(config,a.gateway,a.share),ensure_ascii=False))
    else:
        for key,item in config['shares'].items():
            if not visible(item,groups) or item.get('explicit_only',False) and not a.admin: continue
            try: mapping(config,a.gateway,key)
            except Invalid: continue
            print(key+'\t'+(item.get('name') or item.get('description') or key).replace('\t',' ').replace('\n',' '))


def builder_cli(argv=None):
    p=argparse.ArgumentParser(description='Offline, lossless rpi-share JSON ↔ CSV conversion. Never contacts a server.')
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--csv',type=Path,help='import CSV to JSON')
    source.add_argument('--json',type=Path,help='export JSON to CSV, or validate with --validate')
    p.add_argument('--output',type=Path);p.add_argument('--validate',action='store_true')
    p.add_argument('--plan','--preview',action='store_true',help='print proposed output without writing')
    p.add_argument('--force',action='store_true',help='explicitly authorize atomic replacement')
    p.add_argument('--default-group',help='explicitly override the default navigation group')
    a=p.parse_args(argv)
    config=import_csv(a.csv.read_text(encoding='utf-8-sig')) if a.csv else loads(a.json.read_text(encoding='utf-8-sig'))
    if a.default_group: config.setdefault('defaults',{})['group']=a.default_group
    validate(config)
    if a.validate:
        print('VALID: local configuration only; remote authentication, paths and ACLs have not been checked.');return
    output=json.dumps(config,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n' if a.csv else export_csv(config)
    if a.plan: print(output,end='');return
    require(a.output is not None, '--output is required unless --plan or --validate is selected')
    atomic_write(a.output,output,a.force)
    print('Written '+str(a.output)+'; no network access or remote validation performed.')


if __name__=='__main__':
    try: runtime_cli(sys.argv[1:])
    except (Invalid,ValueError,OSError,TypeError) as exc: sys.exit('Error: '+str(exc))
