#!/usr/bin/python3
import socket, os, grp, sys
from fnmatch import fnmatch
import subprocess

SOCKET_PATH = "/run/keyd_application_switcher_daemon.sock"
ACCESS_GROUP = "keyd-application-switcher"
CONFIG_PATH = "/etc/keyd_application_switcher/app.conf"
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

# Ensure socket exists
if os.path.exists(SOCKET_PATH):
    os.remove(SOCKET_PATH)

if not os.path.exists(CONFIG_PATH):
    die('could not find app.conf, make sure it is in /etc/keyd_application_switcher/app.conf')

config = parse_config(CONFIG_PATH)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SOCKET_PATH)
os.chown(SOCKET_PATH, 0, grp.getgrnam(ACCESS_GROUP).gr_gid)
os.chmod(SOCKET_PATH, 0o660)  # perms
server.listen(1)

dbg("Debug mode on")
print(f"Keyd Application Switcher Daemon Listening on {SOCKET_PATH}... ")

def lookup_bindings(cls, title):
    bindings = []
    for cexp, texp, b in config:
        if fnmatch(cls, cexp) and fnmatch(title, texp):
            dbg(f'\tMatched {cexp}|{texp}')
            bindings.extend(b)

    return bindings

last_mtime = os.path.getmtime(CONFIG_PATH)
def on_window_change(cls, title):
    global last_mtime
    global config

    mtime = os.path.getmtime(CONFIG_PATH)

    if mtime != last_mtime:
        print(CONFIG_PATH + ': Updated, reloading config...')
        config = parse_config(CONFIG_PATH)
        last_mtime = mtime

    bindings = lookup_bindings(cls, title)
    subprocess.run([KEYD_BIN, 'bind', 'reset', *bindings], stdout=subprocess.DEVNULL)

while True:
    conn, _ = server.accept()
    data = conn.recv(128).decode().strip()
    data = [x.strip() for x in data.split('|') if x.strip() != ""]
    if len(data) == 2:
        classname, title = data
        dbg(f"Calling on_window_change hook with {classname}|{title}")
        on_window_change(classname, title)

    conn.close()