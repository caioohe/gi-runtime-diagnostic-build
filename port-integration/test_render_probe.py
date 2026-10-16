from pathlib import Path
import os,subprocess,sys,tempfile
r=Path(sys.argv[1]);probe=Path(__file__).with_name('render_probe.c.inc').read_text();assert probe in (r/'source/main.c').read_text()
s=(r/'source/vulkan_bridge.c').read_text();a=s.index('static unsigned memory_vkAcquireNextImageKHR_calls;');b=s.index('static int is_android_surface',a)
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#define VKAPI_ATTR
#define VKAPI_CALL
typedef int VkResult;typedef uintptr_t VkDevice;typedef uintptr_t VkSwapchainKHR;typedef uintptr_t VkSemaphore;typedef uintptr_t VkFence;typedef uintptr_t VkQueue;
typedef void(*PFN_vkVoidFunction)(void);
typedef struct{int x;}VkSubmitInfo;typedef struct{int x;}VkPresentInfoKHR;
static unsigned forwarded;static int outcome;
static void memory_runtime_trace(const char*f,...){(void)f;}
static void memory_test_report(const char*f,...){(void)f;}
static VkResult vkAcquireNextImageKHR(VkDevice d,VkSwapchainKHR s,uint64_t t,VkSemaphore m,VkFence f,uint32_t*i){assert(d==1&&s==2&&t==3&&m==4&&f==5);*i=7;++forwarded;return outcome;}
static VkResult vkQueueSubmit(VkQueue q,uint32_t n,const VkSubmitInfo*s,VkFence f){assert(q==1&&n==1&&s->x==9&&f==5);++forwarded;return outcome;}
static VkResult vkQueuePresentKHR(VkQueue q,const VkPresentInfoKHR*p){assert(q==1&&p->x==10);++forwarded;return outcome;}
static void sentinel(void){}
'''+s[a:b]+r'''
static int jni_quit_requested,rendered,scenario,calls,frames,pumps;
static uintptr_t tp,memory_boot_host_tp=1,guest_tp=2;
static uint64_t clock_tick;
static uint64_t armGetSystemTick(void){assert(tp==1);uint64_t n=clock_tick;clock_tick+=scenario==9?UINT64_C(60)*19200000u:1;return n;}
static void nx_guest_termination_set_stage(const char*s){assert(tp==2);(void)s;}
static void *fake_env,*fake_unityplayer_thiz;
#define AppletFocusState_InFocus 1
static void write_thread_pointer(uintptr_t p){tp=p;}
static int appletMainLoop(void){assert(tp==1);return scenario!=4;}
static int appletGetFocusState(void){assert(tp==1);return scenario!=3;}
static int android_native_looper_pump_callbacks(int n){assert(n==8&&tp==2);++pumps;if(scenario==10)clock_tick=UINT64_C(61)*19200000u;if(scenario==5)jni_quit_requested=1;return 0;}
static void memory_boot_teardown_checkpoint(const char*s){assert(tp==2);(void)s;}
static void jni_boundary_begin(const char*s){assert(tp==2&&!frames&&!strcmp(s,"nativeRender"));++frames;if(scenario==11)clock_tick=UINT64_C(61)*19200000u;}
static void jni_boundary_end(void){assert(frames==1);--frames;}
static int render(void*a,void*b){assert(!a&&!b&&tp==2&&frames==1);++calls;if(scenario==7)memory_present_returns=1;return scenario!=6;}
static void run_probe(void){
'''+probe+r'''
 if(scenario==0)assert(calls==3600&&!strcmp(probe_stop,"iteration-limit"));
 else if(scenario==6)assert(calls==1&&!strcmp(probe_stop,"render-returned-false"));
 else if(scenario==7 || scenario==8)assert(calls==3600&&!strcmp(probe_stop,"iteration-limit"));
 else if(scenario==9 || scenario==10 || scenario==11)assert(calls==0&&!strcmp(probe_stop,"time-limit"));
 else assert(!calls);
 assert(!frames&&tp==2);
}
int main(void){
 const char*names[]={"vkAcquireNextImageKHR","vkQueueSubmit","vkQueuePresentKHR"};const char*routes[]={"device","instance","direct"};
 for(int i=0;i<3;i++)for(int j=0;j<3;j++){
  assert(!memory_frame_proc(routes[j],names[i],NULL));
  PFN_vkVoidFunction p=memory_frame_proc(routes[j],names[i],sentinel);assert(p&&p!=sentinel);
 }
 assert(memory_frame_proc("direct","unknown",sentinel)==sentinel);assert(memory_frame_proc("direct",NULL,sentinel)==sentinel);
 VkPresentInfoKHR pre={10};outcome=-4;assert(memory_vkQueuePresentKHR(1,&pre)==-4&&nx_memory_present_returns()==1&&forwarded==1);
 for(scenario=0;scenario<12;scenario++){
  clock_tick=0;calls=frames=pumps=jni_quit_requested=memory_present_returns=0;tp=2;rendered=scenario!=1;
  if(scenario==2)jni_quit_requested=1;if(scenario==8)memory_present_returns=1;
  run_probe();
 }
 return 0;
}
'''
# Source verifies all lookup routes use the actual tested routing helper.
for route in ['device','instance','direct']:assert 'memory_frame_proc("'+route+'"' in s
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code);subprocess.run(['gcc','-O1','-g','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS actual bounded probe and Vulkan proc routing: 12 scenarios including continuation after presentation/time/call limits, JNI/TLS, null availability, three routes and returned-present counter; no GPU')


