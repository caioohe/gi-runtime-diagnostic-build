"""Integrated pre-finalization checkpoints; host stubs, no assets/plugins."""
from pathlib import Path
import subprocess
import sys
import tempfile
source=(Path(sys.argv[1])/'source/main.c').read_text()
a=source.index('static void memory_boot_teardown_checkpoint(')
checkpoint=source[a:source.index('\n}',a)+2]
a=source.index('  memory_boot_checkpoint("asset-access-checks-begin");')
flow=source[a:source.index('  memory_boot_checkpoint("finalize-begin");',a)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#define DATA_ROOT "unused"
static struct { void *load_virtbase;size_t load_size; } game_mod={(void *)0x1000,4096};
static uintptr_t g_il2cpp_base,current_tp=1,memory_boot_host_tp=1;
static size_t g_il2cpp_size,heap_so_limit=16384;
static void *heap_so_base=(void *)0x2000;
static unsigned calls,count,memory_test_failed,continued;
static int plugin_failure,stopping=-1;
static char records[16][96];
static const char *stages[]={"cpu","vulkan-sentinel","egl","globalgamemanagers","metadata-digest","startup-mapping","plugin-init"};
static jmp_buf escape;
static uintptr_t read_thread_pointer(void) { return current_tp; }
static void write_thread_pointer(uintptr_t p) { current_tp=p; }
static void memory_runtime_trace(const char *fmt,const char *s) {
  assert(current_tp==1 && count<16);snprintf(records[count++],96,fmt,s);
}
static void memory_boot_checkpoint(const char *s) { assert(!strcmp(s,"asset-access-checks-begin")); }
static void memory_test_check(const char *s,int ok) {
  assert(!strcmp(s,"original plugin loader for native crypto"));if(!ok) ++memory_test_failed;
}
static void call(unsigned index) {
  assert(current_tp==1 && calls==index && count==2*index+1);
  char expected[96];
  snprintf(expected,sizeof expected,index==6?"BOOT %s-begin":"BOOT asset-check-%s-begin",stages[index]);
  assert(!strcmp(records[count-1],expected));++calls;
  if(stopping==(int)index) longjmp(escape,1);
}
static void check_synthetic_cpu_topology_read(void) { call(0); }
static void check_force_vulkan_sentinel(void) { call(1); }
static void check_vulkan_egl_configuration(void) { call(2); }
static void check_globalgamemanagers_seek_read(void) { call(3); }
static void check_global_metadata_digest_read(void) { call(4); }
static void check_startup_metadata_mapping(void) { call(5); }
static int plugin_loader_init(void *base,size_t size,const char *path) {
  assert(base==heap_so_base && size==heap_so_limit && !strcmp(path,DATA_ROOT));
  assert(g_il2cpp_base==0x1000 && g_il2cpp_size==4096);
  call(6);return plugin_failure?-1:0;
}
'''+checkpoint+'\nstatic void run_flow(void) {\n'+flow+r'''
  ++continued;
}
static void reset(void) {
  current_tp=1;calls=count=memory_test_failed=continued=0;
  g_il2cpp_base=g_il2cpp_size=0;plugin_failure=0;stopping=-1;
}
int main(void) {
  reset();run_flow();assert(calls==7 && count==14 && continued==1 && !memory_test_failed);
  for(unsigned i=0;i<7;i++) {
    char expected[96];snprintf(expected,sizeof expected,i==6?"BOOT %s-returned":"BOOT asset-check-%s-returned",stages[i]);
    assert(!strcmp(records[2*i+1],expected));
  }
  for(unsigned i=0;i<7;i++) {
    reset();stopping=(int)i;
    if(!setjmp(escape)) { run_flow();assert(0); }
    assert(calls==i+1 && count==2*i+1 && !continued && current_tp==1);
    if(i<6) assert(!g_il2cpp_base && !g_il2cpp_size);
  }
  reset();plugin_failure=1;run_flow();
  assert(calls==7 && count==15 && memory_test_failed==1 && !continued);
  assert(!strcmp(records[14],"BOOT plugin-init-failed-cleanup-deferred"));
  puts("PASS asset/plugin trace: preserved 7-call order, success, 7 non-returns, plugin failure before finalize");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)

