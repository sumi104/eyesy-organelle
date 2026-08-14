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

# the root filesystem is normally read only. leave it alone if something
# already made it writable, so this does not fight your own remount script
root_opts=$(awk '$2 == "/" { opts = $4 } END { print opts }' /proc/mounts)
case ",$root_opts," in
    *,ro,*)
        echo "== making / writable"
        sudo mount -o remount,rw /
        ;;
    *)
        echo "== / is already writable"
        ;;
esac

echo "== building controls"
# The build is incremental, so running this after a python only change costs
# nothing. The dependency files only appear once something has been compiled
# by the current makefile though, and until they do make cannot tell what a
# header change affects, so start from clean that one time.
if [ ! -f hw_controls/main.d ]; then
    echo "   no dependency files yet, building from clean"
    make -C hw_controls clean
fi
make -C hw_controls

# Ableton Link is GPL and lives outside this tree, so linkd is only built when
# its headers have been fetched. Everything else works without it.
if [ -f "$HOME/link/include/ableton/Link.hpp" ]; then
    echo "== building linkd"
    make -C linkd
else
    echo "== skipping linkd, no Link headers in ~/link"
    echo "   git clone --recurse-submodules https://github.com/Ableton/link ~/link"
fi

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
