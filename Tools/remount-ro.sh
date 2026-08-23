#!/bin/sh

# This script was based on the Organelle OS's.
#
systemctl daemon-reload
#
mount / -o remount,ro
mount /boot/firmware -o remount,ro
