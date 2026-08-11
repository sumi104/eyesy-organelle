#!/bin/bash
#
# Build and install the Organelle S control surface.
#
# Run it as the music user, not with sudo, so the build output stays owned by
# music and the next git pull does not trip over root owned files:
#
#     ~/EYESY_OS/platforms/organelle_s/install.sh
#
set -e
cd "$(dirname "$0")"

echo "== making / writable"
sudo mount -o remount,rw /

echo "== building controls"
make -C hw_controls clean
make -C hw_controls

echo "== installing services"
sudo ./deploy.sh

echo "== restarting"
# eyesypy requires eyesyhw, so the order matters here
sudo systemctl restart eyesyhw
sudo systemctl restart eyesypy
sudo systemctl restart eyesyweb

echo
echo "done. / is still writable, reboot before pulling the plug."
echo "if something looks wrong:  journalctl -u eyesyhw -u eyesypy -n 40"
