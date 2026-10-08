"""Stop only the WSL keepalive created for this preview's local validation."""
import os
from pathlib import Path
import signal

expected = b'codex-pico-vr-image-validation\x001800\x00'
stopped = 0
for process in Path('/proc').iterdir():
    if not process.name.isdigit():
        continue
    try:
        if (process / 'cmdline').read_bytes() == expected:
            os.kill(int(process.name), signal.SIGTERM)
            stopped += 1
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        continue
print('Owned WSL keepalive stopped:', stopped)
