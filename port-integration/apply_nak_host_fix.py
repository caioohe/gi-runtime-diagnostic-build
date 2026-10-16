from pathlib import Path
import sys
r=Path(sys.argv[1]);here=Path(__file__).parent
# Per-thread soft TLS base, not the original (possibly zero) TPIDR_EL0.
p=r/'source/util.c';s=p.read_text();s+='''
extern void *__aarch64_read_tp(void);
uintptr_t nx_compiler_host_tls_enter(void) {
  uintptr_t previous=read_thread_pointer();
  write_thread_pointer((uintptr_t)__aarch64_read_tp());
  return previous;
}
void nx_compiler_host_tls_leave(uintptr_t previous) {
  write_thread_pointer(previous);
}
''';p.write_text(s)
p=r/'source/util.h';s=p.read_text().replace('#define BIONIC_TLS_SIZE','#include <stdint.h>\nuintptr_t nx_compiler_host_tls_enter(void);\nvoid nx_compiler_host_tls_leave(uintptr_t previous);\n#define BIONIC_TLS_SIZE');p.write_text(s)
api=[('bool','nak_should_print_nir','void',''),('bool','nak_debug_no_ugpr','void',''),('struct nak_compiler *','nak_compiler_create','const struct nv_device_info *dev','dev'),('void','nak_compiler_destroy','struct nak_compiler *nak','nak'),('uint64_t','nak_debug_flags','const struct nak_compiler *nak','nak'),('const struct nir_shader_compiler_options *','nak_nir_options','const struct nak_compiler *nak','nak'),('uint32_t','nak_max_warps_per_sm','uint32_t num_gprs,const struct nak_compiler *nak','num_gprs,nak'),('void','nak_shader_bin_destroy','struct nak_shader_bin *bin','bin'),('struct nak_shader_bin *','nak_compile_shader','struct nir_shader *nir,bool dump_asm,const struct nak_compiler *nak,uint32_t robust2_modes,const struct nak_fs_key *fs_key,bool has_task_shader','nir,dump_asm,nak,robust2_modes,fs_key,has_task_shader')]
s=(here/'nak_host_tls.c.inc').read_text()
for ret,name,params,args in api:
 s+=f'extern {ret} __real_{name}({params});\n{ret} __wrap_{name}({params}) {{\n  uintptr_t previous=nak_enter();\n'
 if name=='nak_compile_shader':
  s+='  static unsigned calls;\n  unsigned call=__atomic_add_fetch(&calls,1,__ATOMIC_RELAXED);\n  int sampled=call<=8 || !(call&63);\n  if(sampled) memory_runtime_trace("NAK compile begin call=%u host_tls=1",call);\n'
 s+=('  ' if ret=='void' else f'  {ret} result=')+f'__real_{name}({args});\n'
 if name=='nak_compile_shader':s+='  int status=errno;\n  if(sampled || !result) memory_runtime_trace("NAK compile returned call=%u result_nonnull=%d errno=%d",call,result!=NULL,status);\n  errno=status;\n'
 s+='  nak_leave(previous);\n'+('' if ret=='void' else '  return result;\n')+'}\n'
s+='''
struct u_memstream { FILE *f; };
extern bool __real_u_memstream_open(struct u_memstream *,char **,size_t *);
extern int __real_u_memstream_flush(struct u_memstream *);
bool __wrap_u_memstream_open(struct u_memstream *mem,char **buf,size_t *size) {
  bool ok=__real_u_memstream_open(mem,buf,size);
  if(!ok) { int e=errno; memory_runtime_trace("NAK memstream open failed errno=%d scope=%d",e,nx_nak_host_active()); errno=e; }
  return ok;
}
int __wrap_u_memstream_flush(struct u_memstream *mem) {
  int rc=__real_u_memstream_flush(mem);
  if(rc) { int e=errno; memory_runtime_trace("NAK memstream flush failed rc=%d errno=%d scope=%d",rc,e,nx_nak_host_active()); errno=e; }
  return rc;
}
'''
(r/'source/nak_host_tls.c').write_text(s)
p=r/'source/memory_broker.c';p.write_text(p.read_text()+'\n'+(here/'newlib_nak_alloc.c.inc').read_text())
p=r/'Makefile';s=p.read_text();anchor='-Wl,--wrap=malloc -Wl,--wrap=calloc';assert s.count(anchor)==1;flags=' '.join('-Wl,--wrap='+name for _,name,_,_ in api)+' -Wl,--wrap=_malloc_r -Wl,--wrap=_calloc_r -Wl,--wrap=_memalign_r -Wl,--wrap=_realloc_r -Wl,--wrap=_free_r -Wl,--wrap=u_memstream_open -Wl,--wrap=u_memstream_flush';s=s.replace(anchor,flags+' \\\n            '+anchor);p.write_text(s)

p=r/'source/main.c';s=p.read_text();s=s.replace('tests JNI/graphics and one nativeRender; no login flow.','tests JNI/graphics and up to four nativeRender calls; no login flow.');p.write_text(s)

