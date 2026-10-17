"""Bounded failure capture and lock-free counter sampling; no allocation policy change."""
from pathlib import Path
import sys
r=Path(sys.argv[1])/'source'
h=Path(__file__).with_name('memory_observation.h.inc').read_text()
(r/'memory_observation.h').write_text(h)
p=r/'libc_shim.c';s=p.read_text();a=s.index('static void *oc_pool_owned_alloc(');b=s.index('\nstatic int oc_pool_owned_lookup_locked',a)
body=s[a:b]
reasons=['invalid-size-alignment','thread-overflow-or-reentry','thread-unit-range','thread-donor-or-state','thread-record-conflict','range-or-reentry','no-virtual-extent','record-conflict','backing-commit','extent-metadata']
assert body.count('oc_pool_record_failure(owner);')==len(reasons)
parts=body.split('oc_pool_record_failure(owner);')
body=parts[0]+''.join(f'oc_pool_record_failure(owner);\n    nx_memory_failure_record(size, alignment, owner, {i}, caller);'+part for i,part in enumerate(parts[1:],1))
body=body.replace('  if (!size', '  const uintptr_t caller = (uintptr_t)__builtin_return_address(0);\n  if (!size',1)
s=s[:a]+Path(__file__).with_name('memory_observation.c.inc').read_text()+'\n'+body+s[b:];p.write_text(s)
p=r/'shutdown_observer.c';s=p.read_text();s=s.replace('#include "imports.h"','#include "imports.h"\n#include "memory_observation.h"')
a='    int n=fprintf(observer_file,"sample='
assert s.count(a)==1
s=s.replace(a,'''    NxMemorySample mem;
    nx_memory_sample(&mem);
    u64 total=0, used=0;
    Result total_rc=svcGetInfo(&total,InfoType_TotalMemorySize,CUR_PROCESS_HANDLE,0);
    Result used_rc=svcGetInfo(&used,InfoType_UsedMemorySize,CUR_PROCESS_HANDLE,0);
    int memory_n=fprintf(observer_file,"memory sample=%u guest_pages_bytes=%llu host_pages_bytes=%llu thread_pages_bytes=%llu sparse_committed_bytes=%llu dynamic_mapped_bytes=%llu donor_active_bytes=%llu donor_used_bytes=%llu guest_failures=%llu host_failures=%llu thread_failures=%llu map_calls=%llu map_retries=%llu last_map_rc=0x%llx donor_resize_rc=0x%llx event_drops=%llu process_total=%llu process_used=%llu total_rc=0x%x used_rc=0x%x\\n",i,
      (unsigned long long)mem.guest,(unsigned long long)mem.host,(unsigned long long)mem.thread,
      (unsigned long long)mem.sparse,(unsigned long long)mem.mapped,(unsigned long long)mem.donor_active,(unsigned long long)mem.donor_used,
      (unsigned long long)mem.guest_failures,(unsigned long long)mem.host_failures,(unsigned long long)mem.thread_failures,
      (unsigned long long)mem.map_calls,(unsigned long long)mem.map_retries,(unsigned long long)mem.map_rc,(unsigned long long)mem.resize_rc,
      (unsigned long long)mem.drops,(unsigned long long)total,(unsigned long long)used,total_rc,used_rc);
    NxMemoryFailure events[16];
    size_t event_count=nx_memory_failure_drain(events,16);
    for(size_t e=0;e<event_count;e++) {
      NxMemoryFailure *f=&events[e];
      if(fprintf(observer_file,"allocation_failure tick=%llu request=%llu effective_alignment=%llu owner=%u reason=%u pool_caller=0x%llx map_rc_snapshot=0x%x resize_rc_snapshot=0x%x\\n",
          (unsigned long long)f->tick,(unsigned long long)f->size,(unsigned long long)f->alignment,f->owner,f->reason,
          (unsigned long long)f->caller,f->map_rc,f->resize_rc)<0) memory_n=-1;
    }
'''+a)
s=s.replace('if(n<0 || fflush(observer_file)!=0)', 'if(n<0 || memory_n<0 || fflush(observer_file)!=0)')
p.write_text(s)
