"""Authenticate an already unlocked PICO fastboot session using its saved OEM key.

Does not run flashing unlock/unlock_critical, erase, format, or the failsafe BAT.
Never prints or saves the device-specific key.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'outputs/vr-preview-01-installation'
SDK = Path('C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools')
KEY_SOURCE = Path('C:/Users/RedPanda/Downloads/picounlock-windows-x86_64/FAILSAFE_UNLOCK.bat')

def main():
    state = json.loads((REPORT/'state.json').read_text())
    text = KEY_SOURCE.read_text(encoding='utf-8-sig')
    match = re.search(r'set\s+"PICO=(pico[A-Z0-9]+)"', text, re.I)
    if not match:
        raise RuntimeError('Saved key was not found')
    key = match.group(1)
    def run(tool, args, serial=None, timeout=30, required=True):
        command = [str(SDK/(tool+'.exe'))]
        if serial:
            command += ['-s', serial]
        try:
            p = subprocess.run(command+args, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace')
        except subprocess.TimeoutExpired:
            raise RuntimeError('Device command timed out; inspect state before retrying') from None
        output = (p.stdout+p.stderr).replace(key, 'pico<redacted>')
        if serial:
            output = output.replace(serial, '<device>')
        if required and (p.returncode or 'FAILED' in output):
            raise RuntimeError(output.strip())
        return p, output.strip()
    def devices(tool):
        p, _ = run(tool, ['devices'])
        return [v[0] for line in p.stdout.splitlines() if len(v:=line.split())>=2 and v[1]==('device' if tool=='adb' else 'fastboot')]
    active = devices('adb')
    if len(active)!=1 or hashlib.sha256(active[0].encode()).hexdigest()!=state['device_serial_sha256']:
        raise RuntimeError('Expected original PICO in Android before authentication')
    serial=active[0]
    _, model=run('adb',['shell','getprop ro.product.device'],serial)
    if model!='PICOA8110':
        raise RuntimeError('Unexpected model')
    _, chip=run('adb',['shell','cat /sys/devices/soc0/serial_number'],serial)
    value=int(chip)&0xF7F3F37F
    alphabet='0XD9J6FB3ATQIHNM46XYZZZOPQRSTUVWXYZ'
    encoded=''
    while value:
        encoded=alphabet[value&15]+encoded
        value>>=4
    if key!='pico'+(encoded or alphabet[0]):
        raise RuntimeError('Saved OEM key does not match current SoC')
    _, boot=run('adb',['shell',"su -c 'toybox sha256sum /dev/block/bootdevice/by-name/boot'"],serial,90)
    if boot.split()[0]!=state['boot_sha256']:
        raise RuntimeError('Current boot changed')
    run('adb',['reboot','bootloader'],serial)
    print('Entering the known bootloader for OEM session authentication',flush=True)
    for _ in range(30):
        active=devices('fastboot')
        if active:
            break
        time.sleep(2)
    if len(active)!=1 or hashlib.sha256(active[0].encode()).hexdigest()!=state['bootloader_serial_sha256']:
        raise RuntimeError('Unexpected bootloader identity')
    serial=active[0]
    _, before=run('fastboot',['getvar','unlocked'],serial)
    if not re.search(r'unlocked:\s*yes',before):
        raise RuntimeError('Bootloader must already be unlocked; refusing initial unlock workflow')
    _, authorization=run('fastboot',['oem',key,'unlock'],serial)
    probes={}
    for args in [['getvar','unlocked'],['oem','device-info'],['getvar','is-userspace'],['getvar','is-logical:system'],['getvar','partition-size:system']]:
        p, output=run('fastboot',args,serial,required=False)
        probes[' '.join(args)]={'exit_code':p.returncode,'output':output}
    result={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'saved_key_matches_soc':True,'already_unlocked_before_auth':True,'oem_command_accepted':True,'authorization_output':authorization,'probes':probes,'flashing_unlock_commands_executed':False,'key_printed_or_saved':False}
    (REPORT/'pico-oem-authorization.json').write_text(json.dumps(result,indent=2)+'\n')
    state['pico_oem_authorization']=result
    state['stage']='oem-authorized-fastboot'
    (REPORT/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    main()
