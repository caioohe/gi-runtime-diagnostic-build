#include "memory_observation.h"
/* Try-lock only. No allocator, formatting, I/O, extent scan or waiting here.
 * All event payload access is under this lock (including the reader). Reentry
 * and concurrent writers drop rather than wait. Full queue preserves oldest.
 * The counter sample is approximate: independent relaxed atomic loads. */
static unsigned nx_mem_event_lock;
static uint64_t nx_mem_event_drops;
static NxMemoryFailure nx_mem_events[64];
static size_t nx_mem_event_head,nx_mem_event_count;
static void nx_memory_failure_record(size_t size,size_t alignment,
                                     unsigned owner,unsigned reason,uintptr_t caller) {
  unsigned expected=0;
  if(!__atomic_compare_exchange_n(&nx_mem_event_lock,&expected,1,0,
                                  __ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) {
    __atomic_fetch_add(&nx_mem_event_drops,1,__ATOMIC_RELAXED); return;
  }
  if(nx_mem_event_count==64) {
    __atomic_fetch_add(&nx_mem_event_drops,1,__ATOMIC_RELAXED);
  } else {
    NxMemoryFailure *f=&nx_mem_events[(nx_mem_event_head+nx_mem_event_count)%64];
    f->tick=armGetSystemTick(); f->size=size; f->alignment=alignment;
    f->owner=owner; f->reason=reason; f->caller=caller;
    /* These are recent global results, not necessarily caused by this request. */
    f->map_rc=__atomic_load_n(&oc_last_map_result,__ATOMIC_RELAXED);
    f->resize_rc=__atomic_load_n(&oc_donor_last_resize_result,__ATOMIC_RELAXED);
    ++nx_mem_event_count;
  }
  __atomic_store_n(&nx_mem_event_lock,0,__ATOMIC_RELEASE);
}
size_t nx_memory_failure_drain(NxMemoryFailure *out,size_t capacity) {
  if(!out || !capacity) return 0;
  unsigned expected=0;
  if(!__atomic_compare_exchange_n(&nx_mem_event_lock,&expected,1,0,
                                  __ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) return 0;
  size_t n=nx_mem_event_count<capacity?nx_mem_event_count:capacity;
  for(size_t i=0;i<n;i++) out[i]=nx_mem_events[(nx_mem_event_head+i)%64];
  nx_mem_event_head=(nx_mem_event_head+n)%64; nx_mem_event_count-=n;
  __atomic_store_n(&nx_mem_event_lock,0,__ATOMIC_RELEASE);
  return n;
}
void nx_memory_sample(NxMemorySample *out) {
  if(!out) return;
#define NX_MEM_READ(field,source,scale) out->field=__atomic_load_n(&(source),__ATOMIC_RELAXED)*(uint64_t)(scale)
  NX_MEM_READ(guest,oc_spill_pages,MMAP_PAGE);
  NX_MEM_READ(host,oc_host_spill_pages,MMAP_PAGE);
  NX_MEM_READ(thread,oc_thread_pool_pages,MMAP_PAGE);
  NX_MEM_READ(sparse,oc_committed_pages,MMAP_PAGE);
  NX_MEM_READ(mapped,oc_dynamic_mapped_segments,OC_DYNAMIC_SEGMENT_BYTES);
  NX_MEM_READ(donor_active,g_heap_donor_active_bytes,1);
  NX_MEM_READ(donor_used,oc_donor_used_units,OC_HEAP_DONOR_UNIT_BYTES);
  NX_MEM_READ(guest_failures,oc_guest_allocation_failures,1);
  NX_MEM_READ(host_failures,oc_host_allocation_failures,1);
  NX_MEM_READ(thread_failures,oc_thread_allocation_failures,1);
  NX_MEM_READ(map_calls,oc_map_call_count,1);
  NX_MEM_READ(map_retries,oc_map_retry_count,1);
  NX_MEM_READ(map_rc,oc_last_map_result,1);
  NX_MEM_READ(resize_rc,oc_donor_last_resize_result,1);
  NX_MEM_READ(drops,nx_mem_event_drops,1);
#undef NX_MEM_READ
}
