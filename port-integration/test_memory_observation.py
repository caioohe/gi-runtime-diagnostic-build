"""Actual bounded queue: saturation, reentry, FIFO, concurrent producer/drainer."""
from pathlib import Path
import subprocess,sys,tempfile,os
r=Path(sys.argv[1]);s=(r/'source/libc_shim.c').read_text();module=Path(__file__).with_name('memory_observation.c.inc').read_text();assert module in s
body=s[s.index('static void *oc_pool_owned_alloc('):s.index('\nstatic int oc_pool_owned_lookup_locked')]
assert body.count('nx_memory_failure_record(')==10
for i in range(1,11):assert f'owner, {i}, caller)' in body
assert 'nx_sparse_arena_get_diagnostics' not in module
obs=(r/'source/shutdown_observer.c').read_text();assert 'nx_memory_sample(&mem)' in obs and 'nx_memory_failure_drain(events,16)' in obs
sources=['oc_spill_pages','oc_host_spill_pages','oc_thread_pool_pages','oc_committed_pages','oc_dynamic_mapped_segments','g_heap_donor_active_bytes','oc_donor_used_units','oc_guest_allocation_failures','oc_host_allocation_failures','oc_thread_allocation_failures','oc_map_call_count','oc_map_retry_count','oc_last_map_result','oc_donor_last_resize_result']
code='''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#define MMAP_PAGE 4096
#define OC_DYNAMIC_SEGMENT_BYTES 1048576
#define OC_HEAP_DONOR_UNIT_BYTES 65536
static uint64_t armGetSystemTick(void){return 77;}
'''+''.join('static uint64_t '+x+'=2;\n' for x in sources)+module+'''
static atomic_int done;
static void check(NxMemoryFailure *f){assert(f->tick==77&&f->size==123&&f->alignment==16&&f->owner==1&&f->reason==9&&f->caller==456&&f->map_rc==2&&f->resize_rc==2);}
static void*producer(void*p){(void)p;for(int i=0;i<50000;i++)nx_memory_failure_record(123,16,1,9,456);atomic_fetch_add(&done,1);return NULL;}
int main(void){
 NxMemorySample s;nx_memory_sample(NULL);nx_memory_sample(&s);
 assert(s.guest==8192&&s.host==8192&&s.thread==8192&&s.sparse==8192&&s.mapped==2097152&&s.donor_active==2&&s.donor_used==131072&&s.map_rc==2);
 NxMemoryFailure out[64]; assert(!nx_memory_failure_drain(NULL,64));
 nx_mem_event_lock=1;nx_memory_failure_record(1,1,1,1,1);assert(nx_mem_event_drops==1);assert(!nx_memory_failure_drain(out,64));nx_mem_event_lock=0;
 for(unsigned i=0;i<70;i++)nx_memory_failure_record(i,16,1,9,456);
 assert(nx_mem_event_count==64&&nx_mem_event_drops==7);
 assert(nx_memory_failure_drain(out,16)==16);for(unsigned i=0;i<16;i++)assert(out[i].size==i);
 assert(nx_memory_failure_drain(out,64)==48);for(unsigned i=0;i<48;i++)assert(out[i].size==i+16);
 assert(!nx_memory_failure_drain(out,64));
 uint64_t drops=nx_mem_event_drops,received=0;
 pthread_t threads[4];for(int i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,producer,NULL));
 while(atomic_load(&done)<4){size_t n=nx_memory_failure_drain(out,64);received+=n;for(size_t i=0;i<n;i++)check(&out[i]);}
 for(int i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
 size_t n=nx_memory_failure_drain(out,64);received+=n;for(size_t i=0;i<n;i++)check(&out[i]);
 assert(received+nx_mem_event_drops-drops==200000);return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'memory_observation.h').write_text((r/'source/memory_observation.h').read_text());(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-pie','-no-pie','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('memory observation FIFO/reentry/saturation/concurrency PASS')
