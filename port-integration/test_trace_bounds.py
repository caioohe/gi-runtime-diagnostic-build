from pathlib import Path
import os, subprocess, tempfile
s=Path(__file__).with_name('runtime_trace.c.inc').read_text().replace('#include <switch.h>','').replace('#include "config.h"','')
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;typedef int Mutex;
#define CUR_THREAD_HANDLE 0
#define CUR_PROCESS_HANDLE 0
#define InfoType_TotalMemorySize 0
#define InfoType_UsedMemorySize 1
#define GAME_HOME "unused"
static int lock,deny,fail_open,fail_flush,fail_close,partial;
static size_t actual;
static int mutexTryLock(Mutex *m){(void)m;if(deny)return 0;assert(!lock);lock=1;return 1;}
static void mutexUnlock(Mutex *m){(void)m;assert(lock);lock=0;}
static void svcGetThreadId(u64 *v,int h){(void)h;*v=1;}
static void svcGetInfo(u64 *v,int t,int h,int i){(void)t;(void)h;(void)i;*v=2;}
static u64 armGetSystemTick(void){return 3;}
static FILE *test_open(const char *p,const char *mode){(void)p;(void)mode;return fail_open?NULL:(FILE*)(uintptr_t)1;}
static size_t test_write(const void *p,size_t n,size_t count,FILE *f){(void)p;(void)f;assert(n==1);size_t result=partial?count/2:count;actual+=result;return result;}
static int test_flush(FILE *f){(void)f;return fail_flush?-1:0;}
static int test_close(FILE *f){(void)f;return fail_close?-1:0;}
#define fopen test_open
#define fwrite test_write
#define fflush test_flush
#define fclose test_close
'''+s+r'''
int main(void){
 deny=1;memory_runtime_trace("BOOT blocked");assert(memory_trace_contended==1 && !actual);deny=0;
 fail_open=1;memory_runtime_trace("BOOT open-error");fail_open=0;assert(memory_trace_errors==1);
 partial=1;memory_runtime_trace("BOOT partial");partial=0;
 fail_flush=1;memory_runtime_trace("BOOT flush");fail_flush=0;
 fail_close=1;memory_runtime_trace("BOOT close");fail_close=0;assert(memory_trace_errors==4);
 for(int i=0;i<1000;++i)memory_runtime_trace("ANDROID repeated");assert(memory_trace_sampled>900);
 unsigned before=memory_trace_records;for(int i=0;i<20;++i)memory_runtime_trace("BOOT identical-boundary");assert(memory_trace_records==before+20);
 char large[4000];memset(large,'x',sizeof large-1);large[sizeof large-1]=0;
 for(int i=0;i<3000;++i)memory_runtime_trace("BOOT %d %s",i,large);
 assert(memory_trace_truncated==3000 && memory_trace_limited && actual<=4u*1024u*1024u && memory_trace_bytes<=4u*1024u*1024u && !lock);
 char summary[256];assert(memory_runtime_trace_stats(summary,sizeof summary)==0 && strstr(summary,"limited="));deny=1;assert(memory_runtime_trace_stats(summary,sizeof summary)==-1);deny=0;
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS trace: contention/error/truncation counters, repeat sampling, checkpoint retention and strict 4 MiB attempted-write bound')

