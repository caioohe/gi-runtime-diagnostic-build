from pathlib import Path
import os,subprocess,sys,tempfile
root=Path(sys.argv[1])
def function(file,marker):
 s=(root/'source'/file).read_text();a=s.index(marker);return s[a:s.index('\n}',a)+2]
session=function('combo_session.c','static int write_atomic(')
identity=function('android_identity.c','static int persist_android_id(')
fatal=function('error.c','void fatal_error(')
shutdown=function('main.c','static void shutdown_host(')
code=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <setjmp.h>
#define SESSION_TEMP_PATH "session.tmp"
#define SESSION_PATH "session.dat"
#define ANDROID_ID_TEMP_PATH "identity.tmp"
#define ANDROID_ID_PATH "identity.dat"
static char install_android_id[17]="0123456789abcdef";
static int ensure_session_directory(void){return 0;}
static int ensure_identity_directory(void){return 1;}
static int reject_rename;
static int test_rename(const char *a,const char *b){return reject_rename?-1:rename(a,b);}
#define rename test_rename
'''+session+'\n'+identity+r'''
#undef rename
static int status_active;
typedef int PadState;typedef int ErrorApplicationConfig;
#define HidNpadStyleSet_NpadStandard 0
#define HidNpadButton_A 1
#define R_SUCCEEDED(r) ((r)==0)
static void padConfigureInput(int a,int b){(void)a;(void)b;}
static void padInitializeDefault(PadState *p){(void)p;}
static void consoleUpdate(void *p){(void)p;}
static int appletMainLoop(void){return 0;}
static void padUpdate(PadState *p){(void)p;}
static int padGetButtonsDown(PadState *p){(void)p;return 0;}
static void startup_status_end(void){}
static int errorApplicationCreate(ErrorApplicationConfig *e,const char *a,const char *b){(void)e;(void)a;(void)b;return -1;}
static void errorApplicationShow(ErrorApplicationConfig *e){(void)e;}
static uint64_t armGetSystemTick(void){return 99;}
static jmp_buf stopped;
static void test_exit(int n){assert(n==1);longjmp(stopped,1);}
static FILE *fatal_open(const char *path,const char *mode){(void)path;return fopen("fatal.dat",mode);}
#define fopen fatal_open
#define exit test_exit
'''+fatal+r'''
#undef exit
#undef fopen
static int socket_started,nifm_started,g_net_on,sockets,nifms;
static void (*memory_host_shutdown_trace)(const char *);
static void android_native_vibration_shutdown(void){}
static void opensles_shutdown(void){}
static void combo_auth_shutdown(void){}
static void SDL_Quit(void){}
static void socketExit(void){++sockets;}
static void nifmExit(void){++nifms;}
'''+shutdown+r'''
static void seed(const char *path){FILE *f=fopen(path,"wb");assert(f);assert(fwrite("previous\n",1,9,f)==9);assert(!fclose(f));}
static void previous(const char *path){char b[32]={0};FILE *f=fopen(path,"rb");assert(f);assert(fread(b,1,9,f)==9 && !strcmp(b,"previous\n"));fclose(f);}
int main(void){
 seed(SESSION_PATH);seed(ANDROID_ID_PATH);reject_rename=1;
 assert(write_atomic((const uint8_t*)"new",3)==-1);assert(!persist_android_id());
 previous(SESSION_PATH);previous(ANDROID_ID_PATH);assert(access(SESSION_TEMP_PATH,F_OK)!=0 && access(ANDROID_ID_TEMP_PATH,F_OK)!=0);
 reject_rename=0;assert(write_atomic((const uint8_t*)"new",3)==0 && persist_android_id());
 seed("fatal.dat");if(!setjmp(stopped))fatal_error("message %d",7);previous("fatal.dat");
 char buf[128]={0};FILE *f=fopen("fatal.dat","rb");size_t n=fread(buf,1,sizeof buf-1,f);assert(n>9 && strstr(buf,"FATAL tick=99 message 7"));fclose(f);
 socket_started=nifm_started=g_net_on=1;shutdown_host();assert(!socket_started && !nifm_started && !g_net_on && sockets==1 && nifms==1);
 shutdown_host();assert(sockets==1 && nifms==1);return 0;
}
'''
main=(root/'source/main.c').read_text()
assert 'if(attempted)' in main and 'attempted=1;' in main
for stage in ['bridge','jni-self-test','storage-self-test','crypto','jni-export','jni-version']:assert stage+'-failure-cleanup-deferred' in main
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,cwd=td,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
print('PASS actual persistence/fatal/shutdown functions: failed rename preserves old files, successful writes, fatal history append, socket/nifm flags; retry/deferred-stage source checks')

