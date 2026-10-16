"""Inspect an optimized ARM64 probe using the actual integrated TP writer."""
from pathlib import Path
import os,re,subprocess,sys,tempfile
s=(Path(sys.argv[1])/'source/main.c').read_text();a=s.index('static inline void write_thread_pointer(');f=s[a:s.index('\n}',a)+2]
compiler=Path(os.environ['DEVKITPRO'])/'devkitA64/bin/aarch64-none-elf-gcc'
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'probe.c').write_text('#include <stdint.h>\n'+f+'\nvoid tls_probe(uintptr_t tp,int *p){*p=1;write_thread_pointer(tp);*p=2;}\n')
 subprocess.run([str(compiler),'-O2','-mtp=soft','-march=armv8-a','-S',str(p/'probe.c'),'-o',str(p/'probe.s')],check=True)
 assembly=(p/'probe.s').read_text();msr=assembly.lower().index('msr');stores=[m.start() for m in re.finditer(r'\bstr\s',assembly)]
 assert any(i<msr for i in stores) and any(i>msr for i in stores),assembly
 Path('tls-probe-arm64.s').write_text(assembly)
print('PASS optimized ARM64 TP probe: memory stores retained before and after actual MSR helper; no hardware claim')

