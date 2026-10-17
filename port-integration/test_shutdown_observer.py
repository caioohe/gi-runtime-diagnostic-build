"""Actual observer + actual unmount wrapper, deterministic in-flight I/O fence."""
from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1]);s=(r/'source/shutdown_observer.c').read_text()
integrated=(r/'source/memory_observation.h').exists()
if not integrated: assert Path(__file__).with_name('shutdown_observer.c.inc').read_text() in s
main=(r/'source/main.c').read_text();assert main.index('nx_shutdown_observer_start();')<main.index('  so_finalize(&game_mod);',main.index('static void memory_boot_init('))
def fn(marker):
 x=(r/'source/imports.c').read_text();a=x.index(marker);return x[a:x.index('\n}',a)+2]
counters=fn('void nx_guest_thread_observer_counters(');storage=fn('void nx_pthread_storage_get_diagnostics(')
assert 'mutexLock' not in counters+storage and 'mallinfo' not in counters+storage
h=Path(__file__).with_name('host_exit_trace.c.inc').read_text();a=h.index('Result __wrap_fsdevUnmountAll(void) {');unmount=h[a:h.index('\n}',a)+2]
code=r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sched.h>
typedef int Result;typedef pthread_mutex_t Mutex;
typedef struct{pthread_t id;void(*entry)(void*);}Thread;
typedef struct{uintptr_t lock_address;uint32_t lock_word;}NxPthreadStorageDiagnostics;
#define R_SUCCEEDED(x) ((x)==0)
#define R_FAILED(x) ((x)!=0)
#define THREAD_DIAG_LOAD(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
static unsigned long long guest_thread_create_successes=7,guest_thread_reaped=3;
static uint32_t g_bionic_pthread_storage_lock=0x123;
static int create_fail,start_fail,open_fail,flush_fail,print_fail;
static atomic_int creates,starts,thread_closes,sleeps,flushes,records,file_closes,unmounted;
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;
static int block_write,io_entered,release_io,stop_waiting;
static _Thread_local int is_exit_thread;
static void mutexLock(Mutex*m){
 if(is_exit_thread){pthread_mutex_lock(&gate);stop_waiting=1;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);}
 assert(!pthread_mutex_lock(m));
}
static void mutexUnlock(Mutex*m){assert(!pthread_mutex_unlock(m));}
static void *launch(void*p){Thread*t=p;t->entry(NULL);return NULL;}
static Result threadCreate(Thread*t,void(*e)(void*),void*a,void*b,size_t z,int p,int c){assert(!a&&!b&&z==0x10000&&p==0x3b&&c==-2);++creates;t->entry=e;return create_fail;}
static Result threadStart(Thread*t){++starts;return start_fail?start_fail:pthread_create(&t->id,NULL,launch,t);}
static void threadClose(Thread*t){(void)t;++thread_closes;}
static uint64_t armGetSystemTick(void){return 1;}
static void svcSleepThread(long long n){assert(n==1000000000LL);++sleeps;sched_yield();}
static const char*nx_guest_termination_stage(void){return "shutdown-nativeDone-begin";}
static const char*nx_guest_termination_kind(void){return "none";}
static void memory_runtime_trace(const char*f,...){assert(!unmounted&&strstr(f,"OBSERVER start"));}
static FILE *fake_open(const char*p,const char*m){assert(!unmounted&&strstr(p,"shutdown-observer.txt")&&!strcmp(m,"wb"));return open_fail?NULL:(FILE*)(uintptr_t)1;}
static int fake_print(FILE*f,const char*format,...){
 assert(f&&!unmounted);
 if(strncmp(format,"sample=",7))return 1;
 ++records;
 pthread_mutex_lock(&gate);
 if(block_write&&!io_entered){io_entered=1;pthread_cond_broadcast(&changed);while(!release_io)pthread_cond_wait(&changed,&gate);}
 pthread_mutex_unlock(&gate);
 assert(!unmounted);return print_fail?-1:1;
}
static int fake_flush(FILE*f){assert(f&&!unmounted);++flushes;return flush_fail?-1:0;}
static int fake_close(FILE*f){assert(f&&!unmounted);++file_closes;errno=EIO;return 0;}
#define fopen fake_open
#define fprintf fake_print
#define fflush fake_flush
#define fclose fake_close
'''+counters+'\n'+storage+'\n'+s+r'''
static _Thread_local unsigned host_exit_depth=1;
static _Thread_local int host_exit_storage_live=1;
static void host_exit_checkpoint(const char*s){(void)s;}
static Result __real_fsdevUnmountAll(void){assert(observer_stopped&&!observer_file);unmounted=1;return 0;}
'''+unmount+r'''
static void*exit_main(void*p){(void)p;is_exit_thread=1;errno=EDOM;assert(__wrap_fsdevUnmountAll()==0);assert(errno==EDOM);return NULL;}
static void reset(void){
 observer_started=observer_stopped=0;observer_file=NULL;
 creates=starts=thread_closes=sleeps=flushes=records=file_closes=unmounted=0;
 create_fail=start_fail=open_fail=flush_fail=print_fail=0;
 block_write=io_entered=release_io=stop_waiting=0;
}
int main(void){
 for(int test=0;test<6;test++){
  reset();create_fail=test==1;start_fail=test==2;open_fail=test==3;flush_fail=test==4;print_fail=test==5;
  nx_shutdown_observer_start();nx_shutdown_observer_start();assert(creates==1);
  if(!create_fail&&!start_fail)assert(!pthread_join(observer_thread.id,NULL));
  if(create_fail)assert(starts==0&&thread_closes==0);
  else if(start_fail)assert(starts==1&&thread_closes==1);
  else if(open_fail)assert(!flushes&&!sleeps&&!file_closes);
  else if(flush_fail)assert(flushes==1&&!sleeps&&file_closes==1);
  else if(print_fail)assert(records==1&&!sleeps&&file_closes==1);
  else assert(records==300&&sleeps==300&&flushes==301&&file_closes==1);
  errno=EDOM;nx_shutdown_observer_stop();assert(errno==EDOM);nx_shutdown_observer_stop();
 }
 reset();nx_shutdown_observer_stop();nx_shutdown_observer_start();assert(!creates&&!observer_file);
 reset();block_write=1;nx_shutdown_observer_start();
 pthread_mutex_lock(&gate);while(!io_entered)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);
 pthread_t exiting;assert(!pthread_create(&exiting,NULL,exit_main,NULL));
 pthread_mutex_lock(&gate);while(!stop_waiting)pthread_cond_wait(&changed,&gate);
 assert(!unmounted&&!file_closes);release_io=1;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);
 assert(!pthread_join(exiting,NULL));assert(!pthread_join(observer_thread.id,NULL));
 assert(unmounted&&file_closes==1&&!observer_file);nx_shutdown_observer_stop();assert(file_closes==1);
 return 0;
}
'''
if integrated:
 # Declare SVC and observation stubs after the Result typedef.
 code=code.replace('typedef int Result;', 'typedef int Result;\n#include "memory_observation.h"\ntypedef uint64_t u64;\n#define InfoType_TotalMemorySize 1\n#define InfoType_UsedMemorySize 2\n#define CUR_PROCESS_HANDLE 0\nstatic Result svcGetInfo(u64 *out,int kind,int h,int v){(void)kind;(void)h;(void)v;*out=42;return 0;}\nvoid nx_memory_sample(NxMemorySample *s){memset(s,0,sizeof(*s));}\nsize_t nx_memory_failure_drain(NxMemoryFailure *out,size_t n){if(!n)return 0;memset(out,0,sizeof(*out));return 1;}')
with tempfile.TemporaryDirectory() as td:
 p=Path(td)
 if integrated:(p/'memory_observation.h').write_text((r/'source/memory_observation.h').read_text())
 for name in ['switch.h','guest_termination.h','imports.h']:(p/name).write_text('')
 (p/'test.c').write_text(code)
 subprocess.run(['gcc','-std=c11','-O1','-g','-pthread','-fsanitize=address,undefined','-I'+td,str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual observer/unmount fence: pthread overlap, no I/O after unmount, one close, stop-before-start/repeat/failures, errno; host stubs, no Horizon proof')
