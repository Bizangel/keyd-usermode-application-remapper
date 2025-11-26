#!/usr/bin/python3

import subprocess
import argparse
import select
import socket
import struct
import os
import errno
import shutil
import re
import sys
import fcntl
import signal
from fnmatch import fnmatch

CONFIG_PATH = os.getenv('HOME')+'/.config/keyd/app.conf'
LOCKFILE = os.getenv('HOME')+'/.config/keyd/app.lock'
LOGFILE = os.getenv('HOME')+'/.config/keyd/app.log'

KEYD_BIN = os.environ.get('KEYD_BIN', 'keyd')

debug_flag = os.getenv('KEYD_DEBUG')

def dbg(s):
    if debug_flag:
        print(s)

def die(msg):
    sys.stderr.write('ERROR: ')
    sys.stderr.write(msg)
    sys.stderr.write('\n')
    exit(0)

def assert_env(var):
    if not os.getenv(var):
        raise Exception(f'Missing environment variable {var}')

def run(cmd):
    return subprocess.check_output(['/bin/sh', '-c', cmd]).decode('utf8')

def parse_config(path):
    config = []

    for line in open(path):
        line = line.strip()

        if line.startswith('[') and line.endswith(']'):
            a = line[1:-1].split('|')

            if len(a) < 2:
                cls = a[0]
                title = '*'
            else:
                cls = a[0]
                title = a[1]

            bindings = []
            config.append((cls, title, bindings))
        elif line == '':
            continue
        elif line.startswith('#'):
            continue
        else:
            bindings.append(line)

    return config

def new_interruptible_generator(fd, event_fn, flushed_fn = None):
    intr, intw = os.pipe()

    def handler(s, _):
        os.write(intw, b'i')

    signal.signal(signal.SIGUSR1, handler)

    while True:
        r,_,_ = select.select([fd, intr], [], [])

        if intr in r:
            os.read(intr, 1)
            yield None
        if fd in r:
            if flushed_fn:
                while not flushed_fn():
                    yield event_fn()
            else:
                yield event_fn()

class KDE():
    def __init__(self, on_window_change):
        import os
        import dbus
        import dbus.mainloop.glib

        assert_env("KDE_SESSION_VERSION")

        self.on_window_change = on_window_change
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Inject the kwin script
    def init(self):
        import dbus

        if os.getenv('KDE_SESSION_VERSION') == '6':
                api = 'windowActivated'
        else:
                api = 'clientActivated'

        kwin_script = '''workspace.%s.connect(client => {
            if (!client) return;
            callDBus("org.rvaiya.keyd", "/listener", "", "updateWindow", client.caption, client.resourceClass, client.resourceName);
        });
        ''' % api

        f = open(f'/tmp/keyd-kwin-{os.getuid()}.js', 'w')
        f.write(kwin_script)
        f.close()

        bus = dbus.SessionBus()

        kwin = KDE.get_kwin(bus)

        kwin.unloadScript(f.name)
        num = kwin.loadScript(f.name)

        if os.getenv('KDE_SESSION_VERSION') == '6':
                script_object = f'/Scripting/Script{num}'
        else:
                script_object = f'/{num}'

        script = bus.get_object('org.kde.KWin',  script_object)
        script.run()

    @staticmethod
    def get_kwin(bus):
        import dbus
        import time

        # Give KDE time to initialize the dbus service
        # (allows use in autostart script)
        last_err = None
        for _ in range(5):
            try:
                return bus.get_object('org.kde.KWin', '/Scripting')
            except dbus.exceptions.DBusException as e:
                time.sleep(1)
                last_err = e

        if last_err is not None:
            raise last_err

    def run(self):
        import dbus.service
        import gi.repository.GLib

        on_window_change = self.on_window_change
        class Listener(dbus.service.Object):
            def __init__(self):
                super().__init__(dbus.service.BusName('org.rvaiya.keyd', dbus.SessionBus()), '/listener')

            @dbus.service.method('org.rvaiya.keyd')
            def updateWindow(self, title, klass, id):
                on_window_change(klass, title)

        Listener()

        gi.repository.GLib.MainLoop().run()

def get_monitor(on_window_change):
    monitors = [
        ('kde', KDE),
    ]

    for name, mon in monitors:
        try:
            m = mon(on_window_change)
            print(f'{name} detected')
            return m
        except:
            pass

    print('Could not detect app environment :(.')
    sys.exit(-1)

def lock():
    global lockfh
    lockfh = open(LOCKFILE, 'w')
    try:
        fcntl.flock(lockfh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except:
        die('only one instance may run at a time')

def daemonize():
    print(f'Daemonizing, log output will be stored in {LOGFILE}...')

    fh = open(LOGFILE, 'w')

    os.close(1)
    os.close(2)
    os.dup2(fh.fileno(), 1)
    os.dup2(fh.fileno(), 2)

    if os.fork(): exit(0)
    if os.fork(): exit(0)

opt = argparse.ArgumentParser()
opt.add_argument('-v', '--verbose', default=False, action='store_true', help='Log the active window (useful for discovering window and class names)')
opt.add_argument('-d', '--daemonize', default=False, action='store_true', help='fork and run in the background')
args = opt.parse_args()

if not os.path.exists(CONFIG_PATH):
    die('could not find app.conf, make sure it is in ~/.config/keyd/app.conf')

config = parse_config(CONFIG_PATH)
lock()

def lookup_bindings(cls, title):
    bindings = []
    for cexp, texp, b in config:
        if fnmatch(cls, cexp) and fnmatch(title, texp):
            dbg(f'\tMatched {cexp}|{texp}')
            bindings.extend(b)

    return bindings

def normalize_class(s):
     return re.sub('[^A-Za-z0-9]+', '-', s).strip('-').lower()

def normalize_title(s):
    return re.sub(r'[\W_]+', '-', s).strip('-').lower()

last_mtime = os.path.getmtime(CONFIG_PATH)
def on_window_change(cls, title):
    global last_mtime
    global config

    cls = normalize_class(cls)
    title = normalize_title(title)

    mtime = os.path.getmtime(CONFIG_PATH)

    if mtime != last_mtime:
        print(CONFIG_PATH + ': Updated, reloading config...')
        config = parse_config(CONFIG_PATH)
        last_mtime = mtime

    print(config)

    if args.verbose:
        print(f'Active window: {cls}|{title}')

    bindings = lookup_bindings(cls, title)
    print(bindings)
    subprocess.run([KEYD_BIN, 'bind', 'reset', *bindings], stdout=subprocess.DEVNULL)


mon = get_monitor(on_window_change)
mon.init()

if args.daemonize:
    daemonize()

mon.run()
