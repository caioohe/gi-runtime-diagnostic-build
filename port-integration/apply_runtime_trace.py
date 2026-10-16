"""Add bounded diagnostic records without changing guest/driver results."""
from pathlib import Path
import sys
root=Path(sys.argv[1]); p=root/'source/android_log_sink.c'; s=p.read_text()
s+='\n'+Path(__file__).with_name('runtime_trace.c.inc').read_text()
s=s.replace('#define ANDROID_LOG_TEXT_BYTES 4096u','#define ANDROID_LOG_TEXT_BYTES 4096u\nextern void memory_runtime_trace(const char *format, ...);')
needle='  (void)text;\n  return 1;'
assert s.count(needle)==1
s=s.replace(needle,'  memory_runtime_trace("ANDROID buffer=%d priority=%d tag=%s text=%s",buffer_id,priority,tag?tag:"(null)",text?text:"(null)");\n  return 1;')
needle='  (void)args;\n  return 1;'; assert s.count(needle)==1
s=s.replace(needle,'  char text[1536];\n  if(format) vsnprintf(text,sizeof text,format,args); else snprintf(text,sizeof text,"(null format)");\n  memory_runtime_trace("ANDROID buffer=%d priority=%d tag=%s text=%s",buffer_id,priority,tag?tag:"(null)",text);\n  return 1;')
p.write_text(s)
p=root/'source/vulkan_bridge.c'; s=p.read_text()
insert='\nextern void memory_runtime_trace(const char *format, ...);\n'
commands=[('EnumeratePhysicalDevices','VkInstance instance, uint32_t *count, VkPhysicalDevice *devices','instance, count, devices'),('CreateDevice','VkPhysicalDevice physical, const VkDeviceCreateInfo *info, const VkAllocationCallbacks *allocator, VkDevice *device','physical, info, allocator, device'),('AllocateMemory','VkDevice device, const VkMemoryAllocateInfo *info, const VkAllocationCallbacks *allocator, VkDeviceMemory *memory','device, info, allocator, memory'),('CreateSwapchainKHR','VkDevice device, const VkSwapchainCreateInfoKHR *info, const VkAllocationCallbacks *allocator, VkSwapchainKHR *swapchain','device, info, allocator, swapchain')]
for name,params,args in commands:
    insert+=f'static VKAPI_ATTR VkResult VKAPI_CALL memory_vk{name}({params}) {{\n  memory_runtime_trace("VK vk{name} begin");\n  VkResult result=vk{name}({args});\n  memory_runtime_trace("VK vk{name} returned rc=%d",(int)result);\n  return result;\n}}\n'
s=s.replace('#include "vulkan_bridge.h"','#include "vulkan_bridge.h"\n'+insert)
for name,_,_ in commands:
    needle='  return vkGetInstanceProcAddr(instance, name);'
    s=s.replace(needle,f'  if(strcmp(name,"vk{name}")==0 && vkGetInstanceProcAddr(instance,name)) return (PFN_vkVoidFunction)&memory_vk{name};\n'+needle)
    needle='  return vkGetDeviceProcAddr(device, name);'
    s=s.replace(needle,f'  if(name && strcmp(name,"vk{name}")==0 && vkGetDeviceProcAddr(device,name)) return (PFN_vkVoidFunction)&memory_vk{name};\n'+needle)
s=s.replace('return (void *)&vkEnumeratePhysicalDevices;','return (void *)&memory_vkEnumeratePhysicalDevices;')
s=s.replace('  return vkCreateInstance(&local, allocator, instance);','  memory_runtime_trace("VK vkCreateInstance begin");\n  VkResult result=vkCreateInstance(&local, allocator, instance);\n  memory_runtime_trace("VK vkCreateInstance returned rc=%d",(int)result);\n  return result;')
s=s.replace('  return vkCreateViSurfaceNN(instance, &vi_info, allocator, surface);','  memory_runtime_trace("VK vkCreateViSurfaceNN begin");\n  VkResult result=vkCreateViSurfaceNN(instance, &vi_info, allocator, surface);\n  memory_runtime_trace("VK vkCreateViSurfaceNN returned rc=%d",(int)result);\n  return result;')
p.write_text(s)

