import subprocess,pathlib,hashlib,json
# Run inside WSL; compare selected saved copies with the authenticated stock image.
stock=pathlib.Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-SEKO/system.img')
root=pathlib.Path('/mnt/c/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro')
selected=[('static/system__framework__framework.jar','/system/framework/framework.jar'),('static/system__framework__services.jar','/system/framework/services.jar'),('native/system__lib64__libandroid_runtime.so','/system/lib64/libandroid_runtime.so'),('native/system__lib64__libservices.so','/system/lib64/libservices.so')]
items=[]
for saved,inside in selected:
 r=subprocess.run(['/usr/sbin/debugfs','-R','cat '+inside,str(stock)],capture_output=True,timeout=45)
 errors=r.stderr.decode('utf-8','replace')
 if r.returncode or not r.stdout or any(x in errors for x in ['File not found','Filesystem not open','Could not','Bad magic']): raise RuntimeError(errors)
 actual=hashlib.sha256(r.stdout).hexdigest();local=hashlib.sha256((root/'reports/device'/saved).read_bytes()).hexdigest()
 items.append({'path':inside,'factory_bytes':len(r.stdout),'factory_sha256':actual,'saved_device_sha256':local,'equal':actual==local})
report={'factory_source':str(stock),'factory_logical_image_authenticated_by_5_13_7_ota':True,'files':items,'all_selected_copies_equal':all(x['equal'] for x in items)}
(root/'reports/framework-bridge/factory-copy-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
