#!/bin/sh

# This script was based on the Organelle OS's.
#
systemctl daemon-reload

mount / -o remount,rw
mount /boot/firmware -o remount,rw
