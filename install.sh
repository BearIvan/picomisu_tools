#!/usr/bin/env bash
# Install Picomisu on the PICO 4 Pro (USB): picomisu/install.sh [--wipe] | factory | status | recovery
# On Windows: python picomisu\tools\picomisu-install.py ... (the headset's USB is not visible in WSL
# without usbipd). See tools/picomisu-install.py.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/tools/picomisu-install.py" "$@"
