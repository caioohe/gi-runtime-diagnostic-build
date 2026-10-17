#ifndef NX_MEMORY_OBSERVATION_H
#define NX_MEMORY_OBSERVATION_H
#include <stdint.h>
#include <stddef.h>
typedef struct {
  uint64_t guest,host,thread,sparse,mapped,donor_active,donor_used;
  uint64_t guest_failures,host_failures,thread_failures,map_calls,map_retries,map_rc,resize_rc,drops;
} NxMemorySample;
typedef struct {
  uint64_t tick,size,alignment;
  uintptr_t caller;
  uint32_t owner,reason,map_rc,resize_rc;
} NxMemoryFailure;
void nx_memory_sample(NxMemorySample *out);
size_t nx_memory_failure_drain(NxMemoryFailure *out,size_t capacity);
#endif
