"""Rollback unstarted ownership; use process termination after guest execution."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'source/libc_shim.c';s=p.read_text();anchor='int mmap_validate_unity_slab_reservation('
insert='''/* Cancel only an untouched bootstrap transfer, never a guest-owned slab.
 * Shared alias backing remains process-owned in the prepared arena. */
int mmap_cancel_unclaimed_unity_slab_reservation(const void *base, size_t size) {
  mmap_broker_lock();
  int valid = base && base == unity_slab_reservation &&
    size == unity_slab_reservation_size && size == UNITY_SLAB_RESERVATION_BYTES &&
    unity_slab_state == UNITY_SLAB_RESERVED && !unity_slab_prepared_base &&
    oc_alias_layout_reservation && unity_slab_aligned_base &&
    !unity_slab_diagnostics.committed_chunks &&
    oc_address_range_state((void *)base,size,0,MemType_Unmapped);
  for(size_t i=0; valid && i<UNITY_SLAB_CHUNK_COUNT; ++i)
    if(unity_slab_committed[i] || unity_slab_donor_sources[i]) valid=0;
  if(valid) {
    unity_slab_prepared_base = unity_slab_reservation;
    unity_slab_reservation = NULL;
    unity_slab_reservation_size = 0;
    unity_slab_aligned_base = NULL;
    unity_slab_state = UNITY_SLAB_EMPTY;
  }
  mmap_broker_unlock();
  return valid;
}

'''
assert s.count(anchor)==1;p.write_text(s.replace(anchor,insert+anchor))
p=root/'source/libc_shim.h';s=p.read_text().replace('int mmap_validate_unity_slab_reservation(', 'int mmap_cancel_unclaimed_unity_slab_reservation(const void *base, size_t size);\nint mmap_validate_unity_slab_reservation(');p.write_text(s)
p=root/'source/plugin_loader.c';s=p.read_text();anchor='int plugin_loader_init('
insert='''/* Only valid before any plugin has loaded or executed constructors. */
int plugin_loader_reset_unstarted(void) {
  loader_lock();
  for(size_t i=0;i<PLUGIN_MAX_MODULES;++i) {
    if(g_plugins[i].state != PLUGIN_FREE || g_plugins[i].module.so_base ||
       g_plugins[i].module.load_memrv || g_plugins[i].module.finalized ||
       g_plugins[i].module.load_base || g_plugins[i].module.load_virtbase) {
      loader_unlock();
      return 0;
    }
  }
  g_initialized=0;
  g_main_module=NULL;
  g_arena_at=0; g_arena_left=0;
  memset(g_data_root,0,sizeof g_data_root);
  loader_unlock();
  return 1;
}

''';assert s.count(anchor)==1;p.write_text(s.replace(anchor,insert+anchor))
p=root/'source/plugin_loader.h';s=p.read_text().replace('int plugin_loader_init(', 'int plugin_loader_reset_unstarted(void);\nint plugin_loader_init(');p.write_text(s)
p=root/'source/error.h';s=p.read_text().replace('void fatal_error(', 'void error_set_cleanup(void (*cleanup)(void));\nvoid fatal_error(');p.write_text(s)
p=root/'source/error.c';s=p.read_text();anchor='static int status_active;';s=s.replace(anchor,anchor+'''
static void (*error_cleanup)(void);
void error_set_cleanup(void (*cleanup)(void)) {
  __atomic_store_n(&error_cleanup,cleanup,__ATOMIC_RELEASE);
}''');anchor='  if (status_active) {\n    PadState pad;';assert s.count(anchor)==1;s=s.replace(anchor,'''  void (*cleanup)(void)=__atomic_load_n(&error_cleanup,__ATOMIC_ACQUIRE);
  if(cleanup) cleanup();

'''+anchor);p.write_text(s)
p=root/'source/main.c';s=p.read_text();anchor='static void memory_boot_graphics(';i=s.index(anchor);s=s[:i]+Path(__file__).with_name('safe_cleanup.c.inc').read_text()+'\n'+s[i:]
a=s.index('  memory_boot_teardown_checkpoint("shutdown-host-begin");',s.index('static void memory_boot_graphics('));b=s.index('\n}',a)
s=s[:a]+'  memory_boot_process_exit("guest-nativeDone-returned-process-exit");\n'+s[b:]
anchor='  memory_boot_checkpoint("asset-access-checks-begin");';assert s.count(anchor)==1;s=s.replace(anchor,'''  memory_cleanup_heap_base=module_heap_base; memory_cleanup_heap_limit=module_heap_limit;
  memory_cleanup_slab=slab; memory_cleanup_slab_size=slab_size;
  error_set_cleanup(memory_boot_cleanup_unstarted);
'''+anchor)
old='  if(memory_test_failed) { memory_boot_teardown_checkpoint("plugin-init-failed-cleanup-deferred"); return; }';assert s.count(old)==1;s=s.replace(old,'  if(memory_test_failed) { memory_boot_cleanup_unstarted(); return; }')
anchor='  memory_boot_checkpoint("finalize-begin");';assert s.count(anchor)==1;s=s.replace(anchor,'''  /* Finalization may partly donate pages even on fatal failure. From here,
   * preserve all resources and let the kernel terminate every thread. */
  error_set_cleanup(svcExitProcess);
'''+anchor)
for stage in ['bridge','jni-self-test','storage-self-test','crypto','jni-export']:
 marker=f'memory_boot_teardown_checkpoint("{stage}-failure-cleanup-deferred");'
 a=s.index(marker);b=s.index('return;',a)
 s=s[:a]+s[a:b].replace(marker,'')+f'memory_boot_process_exit("{stage}-failure-process-exit");'+s[b+len('return;'):]
s=s.replace('else memory_boot_teardown_checkpoint("jni-version-failure-cleanup-deferred");','else memory_boot_process_exit("jni-version-failure-process-exit");')
s=s.replace('if(version==JNI_VERSION_1_6) memory_boot_graphics(guest_tp);','if(version==JNI_VERSION_1_6) { memory_boot_graphics(guest_tp); memory_boot_process_exit("guest-graphics-early-return-process-exit"); }')
p.write_text(s)

