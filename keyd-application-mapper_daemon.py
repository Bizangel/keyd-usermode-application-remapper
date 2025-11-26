#!/usr/bin/python3
import socket, os, subprocess, grp

SOCKET_PATH = "/run/keyd_application_switcher_daemon.sock"
ACCESS_GROUP = "keyd-application-switcher"

# Ensure socket exists
if os.path.exists(SOCKET_PATH):
    os.remove(SOCKET_PATH)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SOCKET_PATH)
os.chown(SOCKET_PATH, 0, grp.getgrnam(ACCESS_GROUP).gr_gid)
os.chmod(SOCKET_PATH, 0o660)  # perms
server.listen(1)

print(f"Keyd Application Switcher Daemon Listening on {SOCKET_PATH}... ")

while True:
    conn, _ = server.accept()
    data = conn.recv(128).decode().strip()

    print("received: ", data)

    conn.close()