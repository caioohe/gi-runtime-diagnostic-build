"""Run actual console workload helpers against a host allocator, including failure cleanup.
Does not simulate or validate Horizon mapping behavior.
"""
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).with_name('memory_workloads.c.inc').read_text().split('/* Force public malloc entrypoints')[0]
harness = r'''
#define _POSIX_C_SOURCE 200112L
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#include <stdarg.h>
typedef uint64_t u64;
typedef struct {
 uint64_t spill_bytes,host_spill_bytes,thread_pool_bytes,dynamic_mapped_bytes;
 uint64_t donor_used_bytes,committed_bytes,reserved_bytes,ownership_records_in_use;
 uint64_t quarantined_bytes,donor_grow_calls,donor_shrink_calls;
} NxSparseArenaDiagnostics;
static NxSparseArenaDiagnostics stats;
static unsigned checks_failed, alloc_calls, fail_at;
typedef struct {void *p;size_t n;} Record;
static Record live[16];
static u64 armGetSystemTick(void) {static u64 t;return ++t;}
static void nx_sparse_arena_get_diagnostics(NxSparseArenaDiagnostics *d){*d=stats;}
static void memory_test_report(const char *fmt,...) {(void)fmt;}
static void memory_test_snapshot(const char *s){(void)s;}
static void memory_test_check(const char *name,int ok){(void)name;if(!ok)++checks_failed;}
static void *nx_sparse_pool_spill_alloc_aligned(size_t n,size_t a){
 if(++alloc_calls==fail_at)return NULL;
 void *p=NULL;if(posix_memalign(&p,a,n))return NULL;
 unsigned i=0;while(i<16&&live[i].p)++i;assert(i<16);
 live[i]=(Record){p,n};stats.spill_bytes+=n;
 stats.dynamic_mapped_bytes+=n;stats.donor_used_bytes+=n;++stats.ownership_records_in_use;
 return p;
}
static int nx_sparse_pool_spill_release(void *p){
 unsigned i=0;while(i<16&&live[i].p!=p)++i;assert(i<16);
 size_t n=live[i].n;live[i].p=NULL;
 stats.spill_bytes-=n;stats.dynamic_mapped_bytes-=n;stats.donor_used_bytes-=n;
 --stats.ownership_records_in_use;free(p);return 1;
}
'''
harness += source
harness += r'''
int main(void){
 assert(memory_workloads());assert(checks_failed==0);assert(!stats.spill_bytes);
 alloc_calls=0;fail_at=4;
 assert(memory_workloads());assert(checks_failed==1);
 assert(!stats.spill_bytes&&!stats.ownership_records_in_use);
 MemoryProbe p={0};u64 ticks=0;fail_at=0;
 assert(memory_probe_allocate(&p,4097,64,3,&ticks));
 assert(memory_probe_verify(&p));p.pointer[0]^=1;assert(!memory_probe_verify(&p));
 assert(memory_probe_release(&p,&ticks));
 puts("PASS actual workload helpers: 12 mixed cycles, injected allocation failure cleanup, corruption detection");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'test.c'
    exe = Path(tmp) / 'test'
    c.write_text(harness)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)

