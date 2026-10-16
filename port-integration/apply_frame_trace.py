"""Bounded acquire/submit/present observations; keep the one-frame smoke test."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'source/vulkan_bridge.c';s=p.read_text()
commands=[('AcquireNextImageKHR','VkDevice device, VkSwapchainKHR swapchain, uint64_t timeout, VkSemaphore semaphore, VkFence fence, uint32_t *index','device, swapchain, timeout, semaphore, fence, index'),('QueueSubmit','VkQueue queue, uint32_t count, const VkSubmitInfo *submits, VkFence fence','queue, count, submits, fence'),('QueuePresentKHR','VkQueue queue, const VkPresentInfoKHR *present','queue, present')]
insert=''
for name,params,args in commands:
 insert+=f'''static unsigned memory_vk{name}_calls;
static VKAPI_ATTR VkResult VKAPI_CALL memory_vk{name}({params}) {{
  unsigned call=__atomic_add_fetch(&memory_vk{name}_calls,1,__ATOMIC_RELAXED);
  int sample=call<=8 || !(call&63);
  if(sample) memory_runtime_trace("VK vk{name} begin call=%u",call);
  VkResult result=vk{name}({args});
  if(sample || result<0) memory_runtime_trace("VK vk{name} returned call=%u rc=%d",call,(int)result);
  return result;
}}
'''
anchor='static int is_android_surface';assert s.count(anchor)==1;s=s.replace(anchor,insert+'\n'+anchor)
for name,_,_ in commands:
 for accessor,handle in [('vkGetInstanceProcAddr','instance'),('vkGetDeviceProcAddr','device')]:
  anchor=f'  return {accessor}({handle}, name);';assert s.count(anchor)==1
  s=s.replace(anchor,f'  if(name && !strcmp(name,"vk{name}") && {accessor}({handle},name)) return (PFN_vkVoidFunction)&memory_vk{name};\n'+anchor)
p.write_text(s)

