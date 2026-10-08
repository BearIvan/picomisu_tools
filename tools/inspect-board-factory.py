import pathlib,subprocess,struct,json
root=pathlib.Path('/mnt/c/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro')
stock=pathlib.Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-SEKO')
for inside,out in [('/system/etc/ld.config.29.txt','ld.config.29.txt'),('/system/etc/init/hw/init.environ.rc','init.environ.rc')]:
 r=subprocess.run(['/usr/sbin/debugfs','-R','cat '+inside,str(stock/'system.img')],capture_output=True,timeout=30)
 if r.returncode or not r.stdout or b'File not found' in r.stderr: print(json.dumps({'path':inside,'error':r.stderr.decode()}));continue
 (root/'reports/vr-dependencies'/out).write_bytes(r.stdout)
 if 'ld.config' in inside: print(r.stdout.decode()[:1500])
boot=(stock/'boot.img').read_bytes()[:4096]
fields=struct.unpack_from('<10I',boot,8)
cmd=(boot[64:576]+boot[608:1632]).split(b'\x00')[0].decode()
result={'kernel_size':fields[0],'kernel_addr':hex(fields[1]),'ramdisk_size':fields[2],'ramdisk_addr':hex(fields[3]),'second_size':fields[4],'second_addr':hex(fields[5]),'tags_addr':hex(fields[6]),'page_size':fields[7],'header_version':fields[8],'cmdline':cmd,'dtb_size':struct.unpack_from('<I',boot,1648)[0],'dtb_addr':hex(struct.unpack_from('<Q',boot,1652)[0])}
(root/'reports/board/boot-header.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
