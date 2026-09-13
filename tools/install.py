#!/usr/bin/env python3
"""Auditable installer/uninstaller. No package downloads or shell evaluation."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tomllib

REPO = Path(__file__).resolve().parents[1]
LIB = Path('/usr/local/lib/omarchy-touchbar-radio')
ETC = Path('/etc/omarchy-touchbar-radio')
DATA = Path('/var/lib/omarchy-touchbar-radio')
MANIFEST = DATA / 'install.json'
UNIT = 'touchbar-radio-renderer.service'
USER_UNITS = ['touchbar-radio-media.service', 'touchbar-radio-feed.service', 'touchbar-radio-gestures.service']
MARKER = '-- omarchy-touchbar-radio: managed include'


def toml_value(value):
    if isinstance(value, bool): return str(value).lower()
    if isinstance(value, str): return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)): return str(value)
    if isinstance(value, list): return '[' + ', '.join(map(toml_value, value)) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{json.dumps(k)} = {toml_value(v)}' for k,v in value.items()) + ' }'
    raise ValueError(f'Unsupported TOML value: {type(value).__name__}')


def make_layout(defaults, current, dictation=False):
    merged = copy.deepcopy(dict(defaults, **current))
    media = [dict(k) for k in merged['MediaLayerKeys']]
    if any(k.get('Icon') == 'radio-info' for k in media):
        raise ValueError('An existing radio panel was found; see docs/MIGRATING.md.')
    media.insert(0, dict(Icon='radio-info', Action=[], Stretch=5, IconWidth=520, IconHeight=48))
    mapping = {'PreviousSong':'F15', 'PlayPause':'F16', 'NextSong':'F17'}
    for key in media:
        if isinstance(key.get('Action'), str) and key['Action'] in mapping:
            key['Action'] = mapping[key['Action']]
            if key['Action'] == 'F16':
                key.pop('Text', None)
                key.pop('Theme', None)
                key['Icon'] = 'radio-playback'
    if dictation:
        for layer in (media, merged['PrimaryLayerKeys']):
            if any(k.get('Action') == 'F13' for k in layer):
                raise ValueError('F13 already exists; resolve the dictation binding first.')
            layer.insert(1 if layer is media else 0, dict(Icon='touchbar-dictation', Action='F13'))
    merged['MediaLayerDefault'] = True
    merged['MediaLayerKeys'] = media
    text = '# Managed by omarchy-touchbar-radio. Customize the base.toml template.\n'
    text += '\n'.join(f'{json.dumps(k)} = {toml_value(v)}' for k,v in merged.items()) + '\n'
    tomllib.loads(text)
    return text


def display_width():
    for connector in Path('/sys/class/drm').glob('card*-USB-*'):
        try:
            mode=(connector/'modes').read_text().splitlines()[0]
            a,b=map(int,mode.split('x'))
            if min(a,b)<=100 and 1000<=max(a,b)<=3000:
                return max(a,b), min(a,b)
        except (OSError, ValueError, IndexError): pass
    raise ValueError('No Touch Bar DRM display found. Configure tiny-dfr first, or pass --display-width.')


def unit_text(role, karaoke_python=None, background=False, apple_music=False):
    if role == 'media':
        return f'''[Unit]
Description=Music Touchbar active player selection
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 -I {LIB}/media.py serve
Environment=TOUCHBAR_APPLE_MUSIC={int(apple_music)}
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%t
RestrictAddressFamilies=AF_UNIX
UMask=0077

[Install]
WantedBy=graphical-session.target
'''
    if role == 'karaoke':
        if not karaoke_python:
            raise ValueError('Karaoke requires a prepared Python 3.12 environment.')
        return f'''[Unit]
Description=Touch Bar song recognition and synchronized lyrics
PartOf=graphical-session.target
After=graphical-session.target pipewire-pulse.service

[Service]
ExecStart="{karaoke_python}" -I {LIB}/karaoke.py
Environment=TOUCHBAR_WIKIPEDIA={int(background)}
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%t
PrivateTmp=true
UMask=0077

[Install]
WantedBy=graphical-session.target
'''
    script={'renderer':'renderer.py','feed':'feed.py','gestures':'gestures.py'}[role]
    if role=='renderer':
        return f'''[Unit]
Description=Radio Atlas Touch Bar renderer
# Publishes files independently; tiny-dfr may start after graphical.target.
Wants=tiny-dfr.service

[Service]
ExecStart=/usr/bin/python3 -I {LIB}/{script}
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/etc/tiny-dfr
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX
IPAddressDeny=any
UMask=0022

[Install]
WantedBy=multi-user.target
'''
    sandbox = f'ProtectSystem=strict\nProtectHome=read-only\nReadWritePaths={DATA}/status.json\n' if role=='feed' else ''
    return f'''[Unit]
Description=Radio Atlas Touch Bar {role}
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 -I {LIB}/{script}
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
{sandbox}
[Install]
WantedBy=graphical-session.target
'''


def apple_bridge(source):
    original = '    const state = JSON.stringify(model.serializePlayer(instance))'
    replacement = (REPO / 'patches/apple-music-clock.js').read_text().rstrip('\n')
    if replacement in source:
        return source
    if source.count(original) != 1:
        raise ValueError('Apple Music bridge is not compatible with this clock patch. Update the plugin or install without --with-apple-music.')
    return source.replace(original, replacement)


def apple_lyrics_extension(manifest, control):
    manifest = copy.deepcopy(manifest)
    background = manifest.get('background')
    if background and background != {'service_worker': 'lyrics-background.js'}:
        raise ValueError('Apple Music extension has an unrecognized background worker.')
    manifest['permissions'] = list(dict.fromkeys(manifest.get('permissions', []) + ['nativeMessaging']))
    manifest['background'] = {'service_worker': 'lyrics-background.js'}
    scripts = manifest.get('content_scripts', [])
    main = next((s for s in scripts if s.get('world') == 'MAIN'), None)
    isolated = next((s for s in scripts if s.get('world', 'ISOLATED') == 'ISOLATED'), None)
    if main is None or isolated is None:
        raise ValueError('Apple Music extension script layout has changed.')
    for script, name in ((main, 'lyrics-main.js'), (isolated, 'lyrics-content.js')):
        script['js'] = list(dict.fromkeys(script.get('js', []) + [name]))
    names = ['lyrics-main.js', 'lyrics-content.js', 'lyrics-background.js']
    def extend(match):
        existing = match[1].split()
        return 'EXTENSION_FILES=(' + ' '.join(dict.fromkeys(existing + names)) + ')'
    control, count = re.subn(r'^EXTENSION_FILES=\(([^\n()]*)\)', extend, control, flags=re.M)
    if count != 1:
        raise ValueError('Apple Music extension deployment list has changed.')
    return manifest, control


def plan(account, width, height, dictation, karaoke_python=None, background=False, apple_music=False):
    home=Path(account.pw_dir)
    config=Path('/etc/tiny-dfr/config.toml')
    defaults=tomllib.loads(Path('/usr/share/tiny-dfr/config.toml').read_text())
    current=tomllib.loads(config.read_text()) if config.exists() else {}
    base=make_layout(defaults,current,dictation)
    main=home/'.config/hypr/hyprland.lua'
    if not main.is_file(): raise ValueError('This version requires Omarchy with Hyprland Lua configuration.')
    if MARKER in main.read_text(): raise ValueError('Managed include already present.')
    files={}
    def add(path, data, user=False, replace=False, dynamic=False):
        path=Path(path)
        if path.is_symlink(): raise ValueError(f'Refusing symlink: {path}')
        if path.exists() and not replace: raise ValueError(f'Existing file would be overwritten: {path}')
        files[str(path)]={'data':data.encode() if isinstance(data,str) else data,'user':user,'dynamic':dynamic}
    for source in (REPO/'src').glob('*.py'): add(LIB/source.name,source.read_bytes())
    add(ETC/'base.toml',base)
    add(ETC/'settings.json',json.dumps({'display_width':width,'display_height':height})+'\n')
    add(config,base,replace=True,dynamic=True)
    add('/etc/tiny-dfr/radio-info.svg','<svg xmlns="http://www.w3.org/2000/svg" width="520" height="48"><text x="12" y="30" fill="white">Radio Atlas</text></svg>',dynamic=True)
    add('/etc/tiny-dfr/radio-playback.svg','<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><path fill="white" d="M15 9v30l24-15z"/></svg>',dynamic=True)
    add('/etc/tiny-dfr/radio-track.svg','<svg xmlns="http://www.w3.org/2000/svg" width="300" height="48"/>',dynamic=True)
    add(DATA/'status.json','{}\n',user=True,dynamic=True)
    add('/etc/systemd/system/'+UNIT,unit_text('renderer'))
    for role in ('feed','gestures'):
        add(home/f'.config/systemd/user/touchbar-radio-{role}.service',unit_text(role),user=True)
    add(home/'.config/systemd/user/touchbar-radio-media.service',
        unit_text('media', apple_music=apple_music), user=True)
    if apple_music:
        bridge = home/'.config/omarchy/plugins/melonamin.apple-music/extension/player-bridge.js'
        if not bridge.is_file():
            raise ValueError('Install the melonamin.apple-music Omarchy plugin before enabling Apple Music support.')
        add(bridge, apple_bridge(bridge.read_text()), user=True, replace=True)
        if karaoke_python:
            plugin = bridge.parent.parent
            manifest_path = plugin/'extension/chromium-manifest.json'
            control_path = plugin/'control.sh'
            extension, control = apple_lyrics_extension(json.loads(manifest_path.read_text()), control_path.read_text())
            add(manifest_path, json.dumps(extension, indent=2)+'\n', user=True, replace=True)
            add(control_path, control, user=True, replace=True)
            files[str(control_path)]['mode'] = 0o755
            for source in (REPO/'patches/apple-lyrics').glob('*.js'):
                add(plugin/'extension'/source.name, source.read_bytes(), user=True, replace=True)
            extension_path = f'/run/user/{account.pw_uid}/omarchy-apple-music/extension'
            digest = hashlib.sha256(extension_path.encode()).hexdigest()[:32]
            extension_id = ''.join(chr(ord('a') + int(char, 16)) for char in digest)
            native = json.dumps({'name': 'com.omarchy.touchbar_apple_lyrics',
                'description': 'Apple Music lyrics for Music Touchbar',
                'path': str(LIB/'apple_lyrics.py'), 'type': 'stdio',
                'allowed_origins': [f'chrome-extension://{extension_id}/']}, indent=2)+'\n'
            for profile in (home/'.config/chromium', home/'.local/share/omarchy-apple-music/chromium'):
                add(profile/'NativeMessagingHosts/com.omarchy.touchbar_apple_lyrics.json', native, user=True, replace=True)
            files[str(LIB/'apple_lyrics.py')]['mode'] = 0o755
    if karaoke_python:
        add(home/'.config/systemd/user/touchbar-radio-karaoke.service',
            unit_text('karaoke', karaoke_python, background), user=True)
    # Read-only ACLs on exactly the digitizer and its virtual keys; no input-group membership.
    rules='''# Installed by omarchy-touchbar-radio.
'''
    for name in ('Apple Inc. Touch Bar Display Touchpad','Dynamic Function Row Virtual Input Device'):
        rules+=f'SUBSYSTEM=="input", KERNEL=="event*", ATTRS{{name}}=="{name}", RUN+="/usr/bin/setfacl -m u:{account.pw_name}:r /dev/input/%k"\n'
    add('/etc/udev/rules.d/99-omarchy-touchbar-radio.rules',rules)
    player=home/'.config/omarchy/plugins/akshar.radio-atlas/radio-player'
    if not player.is_file() and not apple_music:
        raise ValueError('Install Radio Atlas or enable --with-apple-music with the Apple Music plugin installed.')
    binds='-- Tap/swipe is handled by the gesture service, not an F14 binding.\n'
    for key,action in [('XF86Launch6','previous'),('XF86Launch7','toggle'),('XF86Launch8','next')]:
        command=f'/usr/bin/python3 -I {LIB}/media.py {action}'
        binds+=f'hl.unbind("{key}")\no.bind("{key}", "Music Touchbar {action}", {json.dumps(command)})\n'
    if dictation:
        if not shutil.which('voxtype'): raise ValueError('Voxtype is required for --with-dictation.')
        vox=home/'.config/voxtype/config.toml'
        hotkey=tomllib.loads(vox.read_text()).get('hotkey',{}) if vox.exists() else {}
        if not (hotkey.get('enabled',False) and hotkey.get('key','').upper()=='F13'):
            binds+='o.bind("XF86Tools", "Touch Bar dictation", "voxtype record toggle")\n'
        add('/etc/tiny-dfr/touchbar-dictation.svg',(REPO/'assets/dictation.svg').read_bytes(),dynamic=True)
    add(home/'.config/hypr/touchbar-radio.lua',binds,user=True)
    add(main,main.read_text()+f'\n{MARKER}\nrequire("hypr.touchbar-radio")\n',user=True,replace=True)
    return files


def user_systemctl(account,*args):
    runtime=f'/run/user/{account.pw_uid}'
    if not Path(runtime+'/bus').exists(): return
    subprocess.run(['runuser','-u',account.pw_name,'--','env',f'XDG_RUNTIME_DIR={runtime}',f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus','systemctl','--user',*args],check=True)


def apply(files,account):
    DATA.mkdir(parents=True,exist_ok=True)
    records={}
    user_units = USER_UNITS + (['touchbar-radio-karaoke.service'] if any(Path(n).name == 'touchbar-radio-karaoke.service' for n in files) else [])
    # Save all originals before the first mutation, including tiny-dfr and Hyprland.
    for name,item in files.items():
        p=Path(name)
        previous=None
        if p.exists():
            st=p.stat()
            previous={'data':base64.b64encode(p.read_bytes()).decode(),'mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid}
        records[name]={'previous':previous,'sha256':hashlib.sha256(item['data']).hexdigest(),'dynamic':item['dynamic'],'installed':False}
    MANIFEST.write_text(json.dumps({'version':'1.3.0','user':account.pw_name,'files':records,'user_units':user_units},indent=2)+'\n')
    MANIFEST.chmod(0o600)
    for name,item in files.items():
        p=Path(name)
        missing=[];parent=p.parent
        while not parent.exists():
            missing.append(parent);parent=parent.parent
        p.parent.mkdir(parents=True,exist_ok=True)
        if item['user']:
            for directory in missing: os.chown(directory,account.pw_uid,account.pw_gid)
        p.write_bytes(item['data']);p.chmod(item.get('mode', 0o600 if p == DATA/'status.json' else 0o644))
        os.chown(p,account.pw_uid if item['user'] else 0,account.pw_gid if item['user'] else 0)
        records[name]['installed']=True
        MANIFEST.write_text(json.dumps({'version':'1.3.0','user':account.pw_name,'files':records,'user_units':user_units},indent=2)+'\n')
    subprocess.run(['udevadm','control','--reload-rules'],check=True)
    for e in Path('/sys/class/input').glob('event*'):
        if (e/'device/name').read_text().strip() in ('Apple Inc. Touch Bar Display Touchpad','Dynamic Function Row Virtual Input Device'):
            subprocess.run(['setfacl','-m',f'u:{account.pw_name}:r','/dev/input/'+e.name],check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','restart','tiny-dfr.service'],check=True)
    subprocess.run(['systemctl','enable','--now',UNIT],check=True)
    user_systemctl(account,'daemon-reload')
    user_systemctl(account,'enable','--now',*user_units)


def uninstall():
    saved=json.loads(MANIFEST.read_text());account=pwd.getpwnam(saved['user'])
    for name,item in saved['files'].items():
        if not item.get('installed',True): continue
        p=Path(name)
        if p.is_symlink(): raise ValueError(f'Path changed to a symlink: {p}')
        if p.exists() and not item['dynamic'] and hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError(f'{p} changed since installation. Back it up and restore the installed version before uninstalling.')
    user_systemctl(account,'disable','--now',*saved.get('user_units', ['touchbar-radio-feed.service', 'touchbar-radio-gestures.service']))
    # Stop the dedicated popup only when it is running.
    runtime = f'/run/user/{account.pw_uid}'
    if Path(runtime + '/bus').exists():
        subprocess.run(['runuser','-u',account.pw_name,'--','env',f'XDG_RUNTIME_DIR={runtime}',
                        f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus',
                        'systemctl','--user','stop','touchbar-song-window.service'], check=False)
    subprocess.run(['systemctl','disable','--now',UNIT],check=True)
    for name,item in reversed(list(saved['files'].items())):
        if not item.get('installed',True): continue
        p=Path(name);old=item['previous']
        if old is None: p.unlink(missing_ok=True)
        else:
            p.write_bytes(base64.b64decode(old['data']));p.chmod(old['mode']);os.chown(p,old['uid'],old['gid'])
    subprocess.run(['udevadm','control','--reload-rules'],check=True)
    for e in Path('/sys/class/input').glob('event*'):
        if (e/'device/name').read_text().strip() in ('Apple Inc. Touch Bar Display Touchpad','Dynamic Function Row Virtual Input Device'):
            subprocess.run(['setfacl','-x',f'u:{account.pw_name}','/dev/input/'+e.name],check=False)
            subprocess.run(['udevadm','trigger','--action=add',str(e)],check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    user_systemctl(account,'daemon-reload')
    subprocess.run(['systemctl','restart','tiny-dfr.service'],check=True)
    MANIFEST.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user',default=os.environ.get('SUDO_USER',os.environ.get('USER')))
    parser.add_argument('--display-width',type=int)
    parser.add_argument('--with-dictation',action='store_true')
    parser.add_argument('--with-apple-music',action='store_true', help='Enable Apple Music and patch its installed bridge to export the song clock')
    parser.add_argument('--with-karaoke',action='store_true', help='Enable Shazam recognition with LRCLIB and NetEase lyric lookup')
    parser.add_argument('--with-background',action='store_true', help='Also look up artist/song/album names on Wikipedia')
    parser.add_argument('--karaoke-python', help='Path to a prepared Python 3.12 virtual environment interpreter')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--uninstall',action='store_true')
    args=parser.parse_args()
    if not args.dry_run and os.geteuid()!=0: parser.error('Run installation/uninstallation with sudo.')
    if args.uninstall:
        if args.dry_run: parser.error('--dry-run is for installation only')
        uninstall();print('Uninstalled; run hyprctl reload in your desktop session.');return
    if MANIFEST.exists(): parser.error('Already installed. Uninstall before installing v1.1.0; see docs/MIGRATING.md.')
    if not args.user or not re.fullmatch(r'[a-z_][a-z0-9_-]*',args.user): parser.error('Pass a regular Linux username with --user.')
    account=pwd.getpwnam(args.user)
    if account.pw_uid==0: parser.error('The desktop user must not be root.')
    for command in ['tiny-dfr','setfacl','systemctl','udevadm','runuser']:
        if not shutil.which(command): parser.error(f'Missing dependency: {command}')
    if args.with_apple_music:
        for command in ('omarchy-shell', 'hyprctl', 'busctl', 'pactl'):
            if not shutil.which(command): parser.error(f'Missing Apple Music dependency: {command}')
    subprocess.run(['/usr/bin/python3','-I','-c','import gi; gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); from gi.repository import Pango, PangoCairo'],check=True)
    width,height=(args.display_width,60) if args.display_width else display_width()
    if not 1000<=width<=3000: parser.error('Unsupported display width.')
    karaoke_python = None
    if args.with_background and not args.with_karaoke:
        parser.error('--with-background requires --with-karaoke')
    if args.with_karaoke:
        karaoke_python = args.karaoke_python or str(Path(account.pw_dir)/'.local/share/omarchy-touchbar-radio/karaoke-venv/bin/python')
        if not Path(karaoke_python).is_absolute() or any(c in karaoke_python for c in '\n\r\"%\\'):
            parser.error('Use an absolute interpreter path without quotes, percent signs, or backslashes.')
        if not Path(karaoke_python).is_file():
            parser.error('Prepare the Python 3.12 karaoke environment first; see README.md.')
        for command in ('parec', 'pactl', 'pw-dump', 'chromium'):
            if not shutil.which(command): parser.error(f'Missing karaoke dependency: {command}')
        check = [karaoke_python, '-I', '-c', 'import sys; assert sys.version_info[:2] == (3,12), \"Use Python 3.12\"; import shazamio, PIL']
        # Never import a user-owned virtual environment as root.
        if os.geteuid() == 0:
            check = ['runuser', '-u', account.pw_name, '--', *check]
        subprocess.run(check, check=True)
    files=plan(account,width,height,args.with_dictation,karaoke_python,args.with_background,args.with_apple_music)
    if args.dry_run:
        print('\n'.join(files));return
    apply(files,account)
    print('Installed. Run hyprctl reload in your desktop session; inspect hyprctl configerrors.')

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        sys.exit(f'Installation error: {error}')
