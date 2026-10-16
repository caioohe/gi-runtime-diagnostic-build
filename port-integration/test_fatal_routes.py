"""Actual fatal shims and termination module; fatal endpoints/SD are host stubs."""
from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1])/'source'
def function(file,name):
 s=(r/file).read_text();pos=s.index(name+'(');start=s.rfind('\n',0,pos)+1;begin=s.index('{',pos);depth=1;i=begin+1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[start:i]
src=(r/'guest_termination.c').read_text()
# No unobserved abort remains in these scoped files except Android assertion,
# which must publish BEFORE its existing formatted Android log and abort.
assert (r/'imports.c').read_text().count('abort();')==0
assert (r/'libc_shim.c').read_text().count('abort();')==0
assert (r/'genshin_compat.c').read_text().count('abort();')==1
android=function('genshin_compat.c','nx_android_log_assert')
assert android.index('nx_guest_fatal_begin(')<android.index('if (format)')<android.index('abort();')
code=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>
#include <assert.h>
#include <pthread.h>
static _Thread_local jmp_buf done;
static _Thread_local int guest,logs,aborts,detail,reenter,drop,android_logs;
static _Thread_local uintptr_t tp;
static const char *expected;
const char *nx_guest_termination_kind(void);
int restore_bionic_tls(void) { if(!guest)return 0;guest=0;tp=1;return 1; }
static void fake_abort(void) __attribute__((noreturn));
static void fake_abort(void) { assert(tp==1&&!guest);++aborts;longjmp(done,1); }
void nx_guest_fatal(const char *,int,void *) __attribute__((noreturn));
void memory_runtime_trace(const char *fmt,...) {
 assert(tp==1&&!guest);assert(!strcmp(nx_guest_termination_kind(),expected));++logs;
 if(reenter) { reenter=0;nx_guest_fatal(expected,detail,(void*)7); }
 if(drop)return;
 char b[512],v[48];va_list a;va_start(a,fmt);vsnprintf(b,sizeof b,fmt,a);va_end(a);
 snprintf(v,sizeof v,"status=%d ",detail);assert(strstr(b,expected)&&strstr(b,v)&&strstr(b,"caller="));
}
#define abort fake_abort
'''+src+r'''
static int fakefd_select_bit(int fd){return fd;}
int getpid_fake(void){return 1;}
static int android_log_sink_vprint(int id,int priority,const char *tag,const char *fmt,va_list args) {
 (void)id;(void)priority;(void)tag;(void)fmt;(void)args;
 assert(tp==1&&!guest&&!strcmp(nx_guest_termination_kind(),expected));++android_logs;return 0;
}
static int android_log_sink_write(int id,int priority,const char *tag,const char *msg) {
 (void)id;(void)priority;(void)tag;(void)msg;
 assert(tp==1&&!guest&&!strcmp(nx_guest_termination_kind(),expected));++android_logs;return 0;
}
'''
for f,n in [('imports.c','__stack_chk_fail_fake'),('imports.c','__cxa_pure_virtual_fake'),('genshin_compat.c','fortify_fail'),('genshin_compat.c','nx_assert2'),('genshin_compat.c','nx_android_log_assert'),('libc_shim.c','__FD_SET_chk_fake'),('libc_shim.c','__FD_ISSET_chk_fake'),('libc_shim.c','kill_fake')]:code+='\n'+function(f,n)+'\n'
code+=r'''
static void *run(void *unused) {
 (void)unused;
 const char *reasons[]={"abort:stack-check","abort:pure-virtual","abort:fortify","abort:assert2","abort:android-log-assert","abort:fd-bounds","abort:fd-bounds","abort:kill","abort:android-log-assert","abort:android-log-assert"};
 for(volatile int g=0;g<2;g++)for(volatile int loss=0;loss<3;loss++)for(volatile int k=0;k<10;k++) {
  expected=reasons[k];detail=k==3?123:k==5||k==6?-1:k==7?11:0;
  guest=g;tp=g?2:1;logs=aborts=android_logs=0;termination_tracing=0;reenter=loss==2;drop=loss==1;
  if(!setjmp(done))switch(k) {
   case 0:__stack_chk_fail_fake();break;case 1:__cxa_pure_virtual_fake();break;
   case 2:fortify_fail();break;case 3:nx_assert2((void*)1,123,(void*)1,(void*)1);break;
   case 4:nx_android_log_assert(NULL,NULL,"assert");break;
   case 5:__FD_SET_chk_fake(-1,NULL,0);break;case 6:__FD_ISSET_chk_fake(-1,NULL,0);break;
   case 7:kill_fake(1,11);break;
   case 8:nx_android_log_assert("condition",NULL,NULL);break;
   case 9:nx_android_log_assert(NULL,NULL,NULL);break;
  }
  assert(aborts==1&&logs==1&&tp==1&&!guest);assert(!strcmp(nx_guest_termination_kind(),expected));
  if(k==4||k==8||k==9)assert(android_logs==(loss==2?0:1));
 }
 termination_tracing=0;guest=0;tp=1;logs=aborts=0;
 assert(kill_fake(1,0)==0);assert(kill_fake(2,0)==-1&&errno==ESRCH);
 assert(kill_fake(1,65)==-1&&errno==EINVAL);assert(kill_fake(1,1)==-1&&errno==38);assert(!logs&&!aborts);
 unsigned long bits=0;__FD_SET_chk_fake(1,&bits,sizeof bits);assert(__FD_ISSET_chk_fake(1,&bits,sizeof bits));
 return NULL;
}
int main(void){run(NULL);pthread_t t;assert(!pthread_create(&t,NULL,run,NULL));assert(!pthread_join(t,NULL));return 0;}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'util.h').write_text('int restore_bionic_tls(void);\n');(p/'guest_termination.h').write_text((r/'guest_termination.h').read_text());(p/'test.c').write_text(code)
 subprocess.run(['cc','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+td,str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual fatal shims: distinct reasons/details, publication before trace/Android formatting, dropped/reentrant logging, host/guest TLS and worker; host abort stubs only')
