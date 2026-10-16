from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1]);src=(root/'source/guest_termination.c').read_text()
assert src==Path(__file__).with_name('guest_termination.c.inc').read_text()
for f,n in [('imports.c','nx_guest_immediate_exit'),('imports.c','nx_guest_abort'),('unity_imports.c','nx_guest_exit')]:assert '&'+n in (root/'source'/f).read_text()
assert 'nx_guest_termination_set_stage(stage);' in (root/'source/main.c').read_text()
code=r'''
#include <stdlib.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <assert.h>
#include <setjmp.h>
#include <pthread.h>
static _Thread_local jmp_buf stopped;
static _Thread_local int guest,forwarded,code_value,logs,expected_kind,expected_status;
static _Thread_local uintptr_t host_tp,tp;
int restore_bionic_tls(void){if(!guest)return 0;guest=0;tp=host_tp;return 1;}
static void forward(int kind,int status) __attribute__((noreturn));
static void forward(int kind,int status){assert(tp==host_tp);forwarded=kind;code_value=status;longjmp(stopped,1);}
static void host_exit(int n) __attribute__((noreturn));static void host_immediate_exit(int n) __attribute__((noreturn));static void host_abort(void) __attribute__((noreturn));
static void host_exit(int n){forward(1,n);}static void host_immediate_exit(int n){forward(2,n);}static void host_abort(void){forward(3,0);}
void memory_runtime_trace(const char *fmt,...){
 assert(tp==host_tp);char b[512];va_list a;va_start(a,fmt);vsnprintf(b,sizeof b,fmt,a);va_end(a);++logs;
 const char *kind=expected_kind==1?"kind=exit ":expected_kind==2?"kind=_exit ":"kind=abort ";assert(strstr(b,kind));assert(strstr(b,"caller="));assert(strstr(b,"stage=shutdown-nativeDone-begin"));
 char status[48];snprintf(status,sizeof status,"status=%d ",expected_status);assert(strstr(b,status));
}
#define exit host_exit
#define _exit host_immediate_exit
#define abort host_abort
'''+src+r'''
#undef exit
#undef _exit
#undef abort
static void *run(void *arg){
 host_tp=(uintptr_t)arg;
 for(int g=0;g<2;g++)for(int k=1;k<=3;k++){
  tp=g?host_tp+100:host_tp;guest=g;logs=forwarded=0;termination_tracing=0;expected_kind=k;expected_status=k==3?0:-7;
  if(!setjmp(stopped)){if(k==1)nx_guest_exit(-7);if(k==2)nx_guest_immediate_exit(-7);nx_guest_abort();}
  assert(forwarded==k&&code_value==expected_status&&logs==1&&!guest);
 }
 /* Reentrant fatal path skips trace and still forwards. */
 guest=1;tp=host_tp+100;termination_tracing=1;logs=0;
 if(!setjmp(stopped))nx_guest_immediate_exit(23);
 assert(forwarded==2&&code_value==23&&logs==0&&tp==host_tp);return NULL;
}
int main(void){nx_guest_termination_set_stage("shutdown-nativeDone-begin");run((void*)1);pthread_t threads[4];for(uintptr_t i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,run,(void*)(i+2)));for(int i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));return 0;}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'util.h').write_text('int restore_bionic_tls(void);\n');(p/'guest_termination.h').write_text((root/'source/guest_termination.h').read_text());(p/'test.c').write_text(code)
 subprocess.run(['gcc','-O1','-g','-pthread','-fsanitize=address,undefined','-I'+td,str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual termination wrappers: distinct forwarding/status, host/guest TLS, four workers, reentrancy; host stubs, no Horizon execution')

