import pathlib,subprocess,json,hashlib
root=pathlib.Path('/mnt/c/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro')
# Run inside WSL; no code in the source image is executed.
image=pathlib.Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-SEKO/system.img')
inside='/system/lib64/libandroid_servers.so'
r=subprocess.run(['/usr/sbin/debugfs','-R','cat '+inside,str(image)],capture_output=True,timeout=45)
if r.returncode or not r.stdout or b'File not found' in r.stderr: raise RuntimeError(r.stderr.decode())
target=root/'reports/device/native/system__lib64__libandroid_servers.so'
if target.exists() and target.read_bytes()!=r.stdout: raise RuntimeError('Preserve an existing different copy')
target.write_bytes(r.stdout)
meta={'file':str(target),'factory_path':inside,'source_image':str(image),'sha256':hashlib.sha256(r.stdout).hexdigest(),'bytes':len(r.stdout),'source_is_authenticated_factory_image':True}
(root/'reports/framework-bridge/android-servers-source.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta))
