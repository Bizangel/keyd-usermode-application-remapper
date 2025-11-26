#!/usr/bin/python3

import argparse
import os
import re
import sys
import fcntl

LOCKFILE = os.getenv('HOME') + '/.config/keyd/app.lock'

def die(msg):
    sys.stderr.write('ERROR: ')
    sys.stderr.write(msg)
    sys.stderr.write('\n')
    exit(0)

def assert_env(var):
    if not os.getenv(var):
        raise Exception(f'Missing environment variable {var}')

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
            print(f'{name} application switcher monitor started')
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

opt = argparse.ArgumentParser()
opt.add_argument('-v', '--verbose', default=False, action='store_true', help='Log the active window (useful for discovering window and class names)')
args = opt.parse_args()

lock()

def normalize_class(s):
     return re.sub('[^A-Za-z0-9]+', '-', s).strip('-').lower()

def normalize_title(s):
    return re.sub(r'[\W_]+', '-', s).strip('-').lower()

def on_window_change(cls, title):
    global last_mtime
    global config

    cls = normalize_class(cls)
    title = normalize_title(title)
    if args.verbose:
        print(f'Active window: {cls}|{title}')


mon = get_monitor(on_window_change)
mon.init()

mon.run()
