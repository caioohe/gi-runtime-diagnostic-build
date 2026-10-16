/* Diagnostic writer: try-lock only; filesystem I/O remains synchronous. */
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <switch.h>
#include "config.h"
static Mutex memory_trace_lock;
static unsigned memory_trace_records;
static size_t memory_trace_bytes;
static unsigned memory_trace_contended, memory_trace_limited, memory_trace_errors;
static unsigned memory_trace_sampled, memory_trace_truncated, memory_trace_repeats;
static char memory_trace_last[2048];
void memory_runtime_trace(const char *format, ...) {
  if(!mutexTryLock(&memory_trace_lock)) {
    __atomic_fetch_add(&memory_trace_contended,1,__ATOMIC_RELAXED);
    return;
  }
  char line[2048]; va_list args; va_start(args,format);
  int n=vsnprintf(line,sizeof line,format,args); va_end(args);
  if(n<0) { ++memory_trace_errors; mutexUnlock(&memory_trace_lock); return; }
  size_t length=(size_t)n<sizeof line?(size_t)n:sizeof line-1;
  if((size_t)n>=sizeof line) ++memory_trace_truncated;
  for(size_t i=0;i<length;i++) if((unsigned char)line[i]<32 || (unsigned char)line[i]==127) line[i]=' ';
  /* Keep boundary checkpoints; coalesce only consecutive identical Android
   * messages after the first eight, with one sample every 64 repeats. */
  if(!strncmp(line,"ANDROID ",8) && !strcmp(line,memory_trace_last)) {
    if(++memory_trace_repeats>8 && (memory_trace_repeats&63)) {
      ++memory_trace_sampled; mutexUnlock(&memory_trace_lock); return;
    }
  } else { strcpy(memory_trace_last,line); memory_trace_repeats=0; }
  u64 id=0,total=0,used=0; svcGetThreadId(&id,CUR_THREAD_HANDLE);
  svcGetInfo(&total,InfoType_TotalMemorySize,CUR_PROCESS_HANDLE,0);
  svcGetInfo(&used,InfoType_UsedMemorySize,CUR_PROCESS_HANDLE,0);
  char record[2560];
  int written=snprintf(record,sizeof record,
    "%u tick=%llu thread=%llu used=%llu total=%llu contended=%u limited=%u errors=%u sampled=%u truncated=%u %s\n",
    memory_trace_records+1,(unsigned long long)armGetSystemTick(),(unsigned long long)id,
    (unsigned long long)used,(unsigned long long)total,
    __atomic_load_n(&memory_trace_contended,__ATOMIC_RELAXED),memory_trace_limited,
    memory_trace_errors,memory_trace_sampled,memory_trace_truncated,line);
  if(written<0 || (size_t)written>=sizeof record) {
    ++memory_trace_errors; mutexUnlock(&memory_trace_lock); return;
  }
  const size_t budget=4u*1024u*1024u;
  if((size_t)written>budget-memory_trace_bytes) {
    ++memory_trace_limited; mutexUnlock(&memory_trace_lock); return;
  }
  FILE *f=fopen(GAME_HOME "/runtime-trace.txt","ab");
  if(f) {
    ++memory_trace_records;
    /* Charge the whole attempted record even on partial writes, so failed
     * writes cannot bypass the per-process byte bound. */
    memory_trace_bytes+=(size_t)written;
    int ok=fwrite(record,1,(size_t)written,f)==(size_t)written;
    if(fflush(f)!=0) ok=0;
    if(fclose(f)!=0) ok=0;
    if(!ok) ++memory_trace_errors;
  } else ++memory_trace_errors;
  mutexUnlock(&memory_trace_lock);
}
int memory_runtime_trace_stats(char *out, size_t capacity) {
  if(!mutexTryLock(&memory_trace_lock)) return -1;
  int n=snprintf(out,capacity,
    "TRACE records=%u attempted_bytes=%zu contended=%u limited=%u errors=%u sampled=%u truncated=%u",
    memory_trace_records,memory_trace_bytes,
    __atomic_load_n(&memory_trace_contended,__ATOMIC_RELAXED),memory_trace_limited,
    memory_trace_errors,memory_trace_sampled,memory_trace_truncated);
  mutexUnlock(&memory_trace_lock);
  return n>=0 && (size_t)n<capacity ? 0 : -1;
}

