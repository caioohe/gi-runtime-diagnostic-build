from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1])
def fn(file,marker):
 s=(root/'source'/file).read_text();a=s.index(marker);return s[a:s.index('\n}',a)+2]
cancel=fn('libc_shim.c','int mmap_cancel_unclaimed_unity_slab_reservation(')
reset=fn('plugin_loader.c','int plugin_loader_reset_unstarted(')
helper=Path(__file__).with_name('safe_cleanup.c.inc').read_text()
setter=fn('error.c','void error_set_cleanup(')
main_source=(root/'source/main.c').read_text()
a=main_source.index('  memory_boot_teardown_checkpoint("shutdown-nativeDone-returned");')
tail=main_source[a:main_source.index('\n}',a)]
error_source=(root/'source/error.c').read_text()
a=error_source.index('  void (*cleanup)(void)=')
hook_dispatch=error_source[a:error_source.index('\n\n',a)]
assert helper in (root/'source/main.c').read_text()
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include "so_util.h"
#define UNITY_SLAB_RESERVATION_BYTES 8192
#define UNITY_SLAB_CHUNK_COUNT 4
#define UNITY_SLAB_EMPTY 0
#define UNITY_SLAB_RESERVED 1
#define UNITY_SLAB_CLAIMED 2
#define MemType_Unmapped 0
#define PLUGIN_MAX_MODULES 3
#define PLUGIN_FREE 0
static struct{unsigned committed_chunks;} unity_slab_diagnostics;
static unsigned unity_slab_state;
static uint8_t unity_slab_committed[4];static uint32_t unity_slab_donor_sources[4];
static void *unity_slab_prepared_base,*unity_slab_reservation,*unity_slab_aligned_base,*oc_alias_layout_reservation;
static size_t unity_slab_reservation_size;
static int mmap_locked,loader_locked,unmapped=1;
static int oc_address_range_state(void *base,size_t size,int prot,int type){assert(mmap_locked && base && size==8192 && !prot && !type);return unmapped;}
static void mmap_broker_lock(void){assert(!mmap_locked);mmap_locked=1;}
static void mmap_broker_unlock(void){assert(mmap_locked);mmap_locked=0;}
static void loader_lock(void){assert(!loader_locked);loader_locked=1;}
static void loader_unlock(void){assert(loader_locked);loader_locked=0;}
static struct{so_module module;int state;}g_plugins[3];
static int g_initialized;static so_module *g_main_module;
static uintptr_t g_arena_at;static size_t g_arena_left;static char g_data_root[32];
'''+cancel+'\n'+reset+r'''
static so_module game_mod;static uintptr_t memory_boot_host_tp=1,tp=2,g_il2cpp_base;static size_t g_il2cpp_size;
static FILE *memory_test_log;
static int discarded,exits,printed;
static jmp_buf stopped;
static const char *last_stage;
static void write_thread_pointer(uintptr_t v){tp=v;}
static void memory_boot_teardown_checkpoint(const char *stage){last_stage=stage;}
static void memory_test_report(const char *f,...){(void)f;++printed;}
static int memory_runtime_trace_stats(char *s,size_t n){snprintf(s,n,"stats");return 0;}
static void svcExitProcess(void) __attribute__((noreturn));
static void svcExitProcess(void){++exits;longjmp(stopped,1);}
int so_is_loaded_module(const so_module *m){return m==&game_mod && m->so_base;}
static void (*error_cleanup)(void);
#define hook error_cleanup
'''+setter+'''
static void fatal_hook_dispatch(void){
'''+hook_dispatch+'''
}
static void memory_boot_discard_pre_slab_failure(void *base,size_t n){
 assert(base==(void*)0x2000 && n==32768 && !unity_slab_state && !g_initialized && !g_main_module && !g_il2cpp_base && !g_il2cpp_size && !hook);++discarded;
}
'''+helper+r'''
static unsigned ends;
static void jni_boundary_end(void){++ends;}
static void after_guest_done(void){
'''+tail+r'''
}
static void initial(void){
 memset(g_plugins,0,sizeof g_plugins);memset(&game_mod,0,sizeof game_mod);game_mod.so_base=(void*)1;
 g_initialized=1;g_main_module=&game_mod;g_arena_at=0x2000;g_arena_left=32768;strcpy(g_data_root,"data");
 unity_slab_state=UNITY_SLAB_RESERVED;unity_slab_reservation=(void*)0x10000;unity_slab_reservation_size=8192;
 unity_slab_aligned_base=(void*)0x10000;unity_slab_prepared_base=NULL;oc_alias_layout_reservation=(void*)0x3000;
 memset(unity_slab_committed,0,sizeof unity_slab_committed);memset(unity_slab_donor_sources,0,sizeof unity_slab_donor_sources);unity_slab_diagnostics.committed_chunks=0;
 memory_cleanup_heap_base=(void*)0x2000;memory_cleanup_heap_limit=32768;
 memory_cleanup_slab=unity_slab_reservation;memory_cleanup_slab_size=8192;
 g_il2cpp_base=0x4000;g_il2cpp_size=65536;discarded=exits=printed=0;unmapped=1;tp=2;hook=memory_boot_cleanup_unstarted;
}
int main(void){
 initial();fatal_hook_dispatch();assert(discarded==1 && !exits && unity_slab_prepared_base==(void*)0x10000 && oc_alias_layout_reservation==(void*)0x3000);
 assert(!unity_slab_reservation && !unity_slab_reservation_size && !unity_slab_aligned_base && !g_arena_at && !g_arena_left && !g_data_root[0]);
 assert(!mmap_cancel_unclaimed_unity_slab_reservation((void*)0x10000,8192));
 for(int mode=0;mode<13;++mode){initial();
  if(mode==0)unity_slab_state=UNITY_SLAB_CLAIMED;
  if(mode==1)unity_slab_committed[2]=1;
  if(mode==2)unity_slab_donor_sources[1]=1;
  if(mode==3)unity_slab_diagnostics.committed_chunks=1;
  if(mode==4)unity_slab_prepared_base=(void*)1;
  if(mode==5)oc_alias_layout_reservation=NULL;
  if(mode==6)memory_cleanup_slab=(void*)2;
  if(mode==7)memory_cleanup_slab_size=1;
  if(mode==8)game_mod.finalized=1;
  if(mode==9)g_plugins[1].state=1;
  if(mode==10)unmapped=0;
  if(mode==11)unity_slab_aligned_base=NULL;
  if(mode==12)g_plugins[1].module.load_base=(void*)1;
  if(!setjmp(stopped)){memory_boot_cleanup_unstarted();assert(0);}
  assert(exits==1 && !discarded && unity_slab_reservation==(void*)0x10000 && game_mod.so_base && !mmap_locked && !loader_locked);
 }
 initial();if(!setjmp(stopped)){memory_boot_process_exit("post-guest-exit");assert(0);}
 assert(exits==1 && !discarded && unity_slab_state==UNITY_SLAB_RESERVED && g_initialized && game_mod.so_base && tp==1 && !strcmp(last_stage,"post-guest-exit"));
 initial();error_set_cleanup(svcExitProcess);if(!setjmp(stopped)){fatal_hook_dispatch();assert(0);}assert(exits==1 && tp==2 && !discarded);
 initial();if(!setjmp(stopped)){after_guest_done();assert(0);}assert(exits==1 && ends==1 && tp==1 && !discarded && g_initialized && !strcmp(last_stage,"guest-nativeDone-returned-process-exit"));return 0;
}
'''
main=(root/'source/main.c').read_text();error=(root/'source/error.c').read_text()
assert main.index('error_set_cleanup(svcExitProcess);')<main.index('  so_finalize(&game_mod);',main.index('static void memory_boot_init('))
for stage in ['bridge','jni-self-test','storage-self-test','crypto','jni-export','jni-version','guest-graphics-early-return','guest-nativeDone-returned']:assert stage+'-process-exit' in main or stage+'-failure-process-exit' in main
assert 'if(cleanup) cleanup();' in error and '__ATOMIC_ACQUIRE' in error
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(root/'source'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual slab cancellation/plugin reset and integrated cleanup: ownership guards, unstarted rollback, thirteen refusals, post-guest syscall without unload; no Horizon execution')

