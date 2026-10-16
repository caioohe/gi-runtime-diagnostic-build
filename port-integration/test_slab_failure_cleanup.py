"""Actual slab preparation/getter and integrated failure gate with PC stubs."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
root=Path(sys.argv[1])
main=(root/'source/main.c').read_text()
shim=(root/'source/libc_shim.c').read_text()
def function(text,marker):
    a=text.index(marker);return text[a:text.index('\n}',a)+2]
prepare=function(shim,'int mmap_prepare_unity_slab_reservation(')
getter=function(shim,'int mmap_get_unity_slab_diagnostics(')
cleanup=function(main,'static void memory_boot_cleanup_slab_failure(')
a=main.index('  void *slab=NULL; size_t slab_size=0;')
flow=main[a:main.index('  memory_boot_checkpoint("asset-access-checks-begin");',a)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define UNITY_SLAB_EMPTY 0
#define UNITY_SLAB_RESERVED 1
#define UNITY_SLAB_CLAIMED 2
#define UNITY_SLAB_RETIRED 3
#define UNITY_SLAB_RESERVATION_BYTES 8192u
#define UNITY_SLAB_ALIGNMENT 4096u
#define GENSHIN_UNITY_SLAB_USABLE_BYTES 4096u
#define MemType_Unmapped 0
#define ALIGN_MEM(v,a) (((v)+(a)-1)&~((uintptr_t)(a)-1))
typedef struct {
  uintptr_t reservation_base;
  uint64_t reservation_size;
  uint32_t reservation_state,committed_chunks;
} UnitySlabMmapDiagnostics;
static UnitySlabMmapDiagnostics unity_slab_diagnostics;
static uintptr_t unity_slab_state;
static uint8_t *unity_slab_prepared_base,*unity_slab_aligned_base;
static void *unity_slab_reservation,*oc_alias_layout_reservation;
static size_t unity_slab_reservation_size;
static uint8_t unity_slab_committed[4];
static uint32_t unity_slab_donor_sources[4];
static int locked,unmapped,cleanup_calls,continued,reports,deferred,memory_test_failed;
static int getter_available=1;
static void mmap_broker_lock(void) { assert(!locked);locked=1; }
static void mmap_broker_unlock(void) { assert(locked);locked=0; }
static int oc_address_range_state(void *p,size_t n,int prot,int type) {
  assert(locked && p==unity_slab_prepared_base && n==8192 && !prot && !type);
  return unmapped;
}
static void memory_test_report(const char *fmt,...) { (void)fmt;++reports; }
static void memory_boot_teardown_checkpoint(const char *stage) {
  assert(!strcmp(stage,"slab-failure-cleanup-deferred"));++deferred;
}
static void memory_boot_discard_pre_slab_failure(void *base,size_t limit) {
  assert(base==(void *)(uintptr_t)0x1000 && limit==32768);
  assert(!locked && !unity_slab_state && !unity_slab_reservation && !unity_slab_reservation_size && !unity_slab_diagnostics.committed_chunks);
  ++cleanup_calls;
}
static void memory_test_check(const char *name,int ok) { (void)name;if(!ok) ++memory_test_failed; }
'''+prepare+'\n'+getter+r'''
static int test_getter(UnitySlabMmapDiagnostics *d) {
  return getter_available?mmap_get_unity_slab_diagnostics(d):0;
}
#define mmap_get_unity_slab_diagnostics test_getter
'''+cleanup+'\nstatic void run_flow(void *module_heap_base,size_t module_heap_limit) {\n'+flow+r'''
  ++continued;
}
static void reset(void) {
  unity_slab_state=0;unity_slab_reservation=NULL;unity_slab_reservation_size=0;
  unity_slab_prepared_base=(void *)(uintptr_t)0x10000;unity_slab_aligned_base=NULL;
  oc_alias_layout_reservation=(void *)1;
  memset(&unity_slab_diagnostics,0,sizeof unity_slab_diagnostics);
  memset(unity_slab_committed,0x55,sizeof unity_slab_committed);
  memset(unity_slab_donor_sources,0x55,sizeof unity_slab_donor_sources);
  locked=cleanup_calls=continued=reports=deferred=memory_test_failed=0;
  getter_available=unmapped=1;
}
int main(void) {
  (void)memory_boot_cleanup_slab_failure;
  for(int mode=0;mode<4;mode++) {
    reset();
    if(mode==0) unity_slab_prepared_base=NULL;
    if(mode==1) oc_alias_layout_reservation=NULL;
    if(mode==2) unmapped=0;
    if(mode==3) unity_slab_prepared_base=(void *)(uintptr_t)(UINTPTR_MAX-1);
    uint8_t *before=unity_slab_prepared_base;
    run_flow((void *)(uintptr_t)0x1000,32768);
    assert(cleanup_calls==1 && reports==1 && !deferred && !continued && memory_test_failed==1);
    assert(!locked && unity_slab_prepared_base==before && !unity_slab_state);
    for(unsigned i=0;i<sizeof unity_slab_committed;i++) assert(unity_slab_committed[i]==0x55);
  }
  for(int state=1;state<=3;state++) {
    reset();unity_slab_state=state;unity_slab_reservation=(void *)0x20000;
    unity_slab_reservation_size=1;run_flow((void *)(uintptr_t)0x1000,32768);
    assert(!cleanup_calls && deferred==1 && !continued && reports==1);
    assert(unity_slab_state==(uintptr_t)state && unity_slab_reservation==(void *)0x20000 && unity_slab_reservation_size==1);
  }
  for(int mode=0;mode<4;mode++) {
    reset();unity_slab_prepared_base=NULL;
    if(mode==0) getter_available=0;
    if(mode==1) unity_slab_reservation=(void *)0x20000;
    if(mode==2) unity_slab_reservation_size=1;
    if(mode==3) unity_slab_diagnostics.committed_chunks=1;
    run_flow((void *)(uintptr_t)0x1000,32768);
    assert(!cleanup_calls && deferred==1 && !continued && reports==1);
  }
  reset();run_flow((void *)(uintptr_t)0x1000,32768);
  assert(continued==1 && !cleanup_calls && !reports && !deferred && !memory_test_failed);
  assert(unity_slab_state==1 && unity_slab_reservation==(void *)0x10000 && unity_slab_reservation_size==8192 && !unity_slab_prepared_base);
  for(int state=1;state<=3;state++) {
    reset();unity_slab_state=state;unity_slab_reservation=(void *)0x20000;unity_slab_reservation_size=8192;
    run_flow((void *)(uintptr_t)0x1000,32768);
    assert(continued==1 && !cleanup_calls && !reports && !deferred);
    assert(unity_slab_state==(uintptr_t)state && unity_slab_reservation==(void *)0x20000);
  }
  puts("PASS slab: 4 empty-state failures, 3 existing invalid states, 4 unavailable/inconsistent snapshots, fresh and 3 existing success cases");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,env=os.environ)

