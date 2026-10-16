from pathlib import Path
import subprocess,sys,tempfile
s=(Path(sys.argv[1])/'source/vulkan_bridge.c').read_text();a=s.index('static unsigned memory_vkAcquireNextImageKHR_calls;');b=s.index('static int is_android_surface',a)
code=r'''
#include <stdint.h>
#include <assert.h>
#include <stdarg.h>
#define VKAPI_ATTR
#define VKAPI_CALL
typedef int VkResult;typedef uintptr_t VkDevice;typedef uintptr_t VkSwapchainKHR;
typedef uintptr_t VkSemaphore;typedef uintptr_t VkFence;typedef uintptr_t VkQueue;
typedef struct{int x;} VkSubmitInfo;typedef struct{int x;} VkPresentInfoKHR;
static unsigned traced,called;static int outcome;
static void memory_runtime_trace(const char *f,...){(void)f;++traced;}
static VkResult vkAcquireNextImageKHR(VkDevice d,VkSwapchainKHR s,uint64_t t,VkSemaphore sem,VkFence f,uint32_t *i){assert(d==1 && s==2 && t==3 && sem==4 && f==5);*i=7;++called;return outcome;}
static VkResult vkQueueSubmit(VkQueue q,uint32_t n,const VkSubmitInfo *s,VkFence f){assert(q==1 && n==1 && s->x==9 && f==5);++called;return outcome;}
static VkResult vkQueuePresentKHR(VkQueue q,const VkPresentInfoKHR *p){assert(q==1 && p->x==10);++called;return outcome;}
'''+s[a:b]+r'''
int main(void){VkSubmitInfo sub={9};VkPresentInfoKHR pre={10};uint32_t index=0;
 for(int i=0;i<130;++i){outcome=i==129?-4:0;assert(memory_vkAcquireNextImageKHR(1,2,3,4,5,&index)==outcome && index==7);assert(memory_vkQueueSubmit(1,1,&sub,5)==outcome);assert(memory_vkQueuePresentKHR(1,&pre)==outcome);}
 assert(called==390 && traced==63);return 0;}
'''
for name in ['AcquireNextImageKHR','QueueSubmit','QueuePresentKHR']:
 for accessor in ['vkGetDeviceProcAddr','vkGetInstanceProcAddr']:assert f'{accessor}(' in s and f'&memory_vk{name}' in s
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS frame trace actual wrappers: forwarding arguments/results/index, bounded samples and negative-result records; no GPU test')

