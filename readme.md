## User-Mode KeyD Application Specific Remapper.
**Note: Currently targeted towards: KDE Wayland - other logic has been removed for code cleaning**
Adapted from: https://github.com/rvaiya/keyd/blob/master/scripts/keyd-application-mapper

Current keyd implementation of `keyd-application-mapper` requires the user to be able to read and modify keyd socket - i.e. basically have input and root access.
I'd like to have this nice remapping functionality without having a clear privilege escalation.

Given the code is quite simple I thought I'd just change it a bit:

1. A daemon server listens on a unix socket specifically `/run/keyd_application_switcher_daemon.sock` this daemon reads the config and triggers the actual keyd changes.
1.1. The daemon only reads from the untrusted socket input classnames and window titles for the matching logic. This prevents any sort of privilege escalation.
1.2. It is then very important that the configuration file permissions are protected to only root. (`/etc/keyd_application_switcher/app.conf`)

2. The user client will simply use the previously existing logic to detect whenever a window changes - and send this to the switcher daemon by writing into the unix socket. This will trigger the remapping.

For a bit extra security users must be part of `keyd-application-switcher` group to write to the socket.

**NOTE: Bear in mind that this is based on the python script of keyd - so it is still relatively experimental**

## Quickstart

0. Pull this repo

```
git clone https://github.com/Bizangel/keyd-usermode-application-remapper
cd keyd-usermode-application-remapper
```

1. Create access group:

```sh
sudo groupadd keyd-application-switcher
```

2. Add yourself to the group

```sh
sudo usermod -aG keyd-application-switcher "$(whoami)"
```

3. Reboot so that group permissions are re-loaded. (For me logout didn't work)

4. Create the config you wish to use:

```sh
sudo mkdir -p /etc/keyd_application_switcher/
sudo touch /etc/keyd_application_switcher/app.conf
sudo nano /etc/keyd_application_switcher/app.conf
```

Fill it out with contents as you wish - example:

```
[org-mozilla-firefox]

q = a
a = q
```

5. Set up the daemon service as `root`:

```sh
sudo cp keyd_application_mapper_daemon.py /usr/local/bin/keyd_application_mapper_daemon
sudo chmod +x /usr/local/bin/keyd_application_mapper_daemon
sudo cp services/keyd-application-mapper-daemon.service /usr/local/lib/systemd/system/keyd-application-mapper-daemon.service
sudo systemctl daemon-reload
sudo systemctl enable --now keyd-application-mapper-daemon
```

Ensure that it's running the server daemon without issues:

```sh
sudo systemctl status keyd-application-mapper-daemon
```

6. Set up the usermode daemon that reports the window switches:

```sh
cp keyd_application_mapper_user_reporter.py ~/.local/bin/keyd_application_mapper_user_reporter
chmod +x ~/.local/bin/keyd_application_mapper_user_reporter
cp services/keyd-application-mapper-user-reporter.service ~/.config/systemd/user/keyd-application-mapper-user-reporter.service
sed -i "s|<home_abs_path>|$HOME|" ~/.config/systemd/user/keyd-application-mapper-user-reporter.service
systemctl --user daemon-reload
systemctl --user enable --now keyd-application-mapper-user-reporter.service
```

Check that the service is successfully running:

```sh
systemctl --user status keyd-application-mapper-user-reporter.service
```






