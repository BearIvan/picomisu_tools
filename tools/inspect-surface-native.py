import pathlib,subprocess,json,hashlib
root=pathlib.Path('/mnt/c/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro')
src=pathlib.Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/aosp-10')
tool=src/'prebuilts/clang/host/linux-x86/clang-r353983c/bin/llvm-objdump'
binary=root/'reports/device/native/system__lib64__libandroid_runtime.so'
meta=json.loads((root/'reports/framework-bridge/jni-signatures.json').read_text())
entry=next(e for b in meta['native_candidates'] if b['file']==binary.name for e in b['candidate_entries'] if e['name']=='nativeSetPvrStatus')
start=int(entry['function_vaddr'],16)
result=subprocess.run([str(tool),'-d','--start-address='+hex(start),'--stop-address='+hex(start+0x84),str(binary)],capture_output=True,text=True,check=True)
(root/'reports/framework-bridge/native-set-pvr-status.asm.txt').write_text(result.stdout)
report={'binary':binary.name,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'jni_entry':entry,'disassembly':'native-set-pvr-status.asm.txt','observations':['Calls Surface::getIGraphicBufferProducer().','Passes code 10000 and a pointer to the input status to a virtual method at vtable byte offset 120.'],'inference_requiring_verification':'The virtual method corresponds to the standard producer query interface; PICO handling of code 10000 and Parcel payloads must still be inspected.','implementation_ported':False}
(root/'reports/framework-bridge/surface-native-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
