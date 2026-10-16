from pathlib import Path
import sys
r=Path(sys.argv[1]);here=Path(__file__).parent
p=r/'source/main.c';s=p.read_text();a='  memory_boot_checkpoint("graphics-shutdown-begin");';assert s.count(a)==1;s=s.replace(a,(here/'render_probe.c.inc').read_text()+a);s=s.replace('tests JNI/graphics and one nativeRender; no login flow.','tests JNI/graphics and bounded extended rendering; no login flow.');p.write_text(s)
p=r/'source/vulkan_bridge.c';s=p.read_text();a='static unsigned memory_vkQueuePresentKHR_calls;';assert s.count(a)==1;s=s.replace(a,a+'\nstatic unsigned memory_present_returns;\nunsigned nx_memory_present_returns(void) { return __atomic_load_n(&memory_present_returns,__ATOMIC_ACQUIRE); }');a='  VkResult result=vkQueuePresentKHR(queue, present);';assert s.count(a)==1;s=s.replace(a,a+'\n  __atomic_add_fetch(&memory_present_returns,1,__ATOMIC_RELEASE);')
helper='''/* Preserve availability: wrap only a nonnull procedure supplied by loader. */
static PFN_vkVoidFunction memory_frame_proc(const char *route, const char *name, PFN_vkVoidFunction raw) {
  PFN_vkVoidFunction wrapped=NULL;
  if(!name) return raw;
  if(!strcmp(name,"vkAcquireNextImageKHR")) wrapped=(PFN_vkVoidFunction)&memory_vkAcquireNextImageKHR;
  else if(!strcmp(name,"vkQueueSubmit")) wrapped=(PFN_vkVoidFunction)&memory_vkQueueSubmit;
  else if(!strcmp(name,"vkQueuePresentKHR")) wrapped=(PFN_vkVoidFunction)&memory_vkQueuePresentKHR;
  if(!wrapped) return raw;
  static unsigned records;
  unsigned n=__atomic_add_fetch(&records,1,__ATOMIC_RELAXED);
  if(n<=32) memory_runtime_trace("VK resolve route=%s name=%s available=%d wrapped=%d",route,name,raw!=NULL,raw!=NULL);
  return raw?wrapped:NULL;
}
'''
a='static int is_android_surface';s=s.replace(a,helper+'\n'+a)
for access,handle,route in [('vkGetDeviceProcAddr','device','device'),('vkGetInstanceProcAddr','instance','instance')]:
 for name in ['AcquireNextImageKHR','QueueSubmit','QueuePresentKHR']:
  old=f'  if(name && !strcmp(name,"vk{name}") && {access}({handle},name)) return (PFN_vkVoidFunction)&memory_vk{name};';assert s.count(old)==1;s=s.replace(old,'')
 old=f'  return {access}({handle}, name);';assert s.count(old)==1;s=s.replace(old,f'  return memory_frame_proc("{route}",name,{access}({handle},name));')
a='  return (void *)vkGetInstanceProcAddr(VK_NULL_HANDLE, name);';assert s.count(a)==1;s=s.replace(a,'  return (void *)memory_frame_proc("direct",name,vkGetInstanceProcAddr(VK_NULL_HANDLE,name));');p.write_text(s)


