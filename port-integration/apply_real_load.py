"""Diagnostic real-library materialization; never execute guest code."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'source/main.c'
s=p.read_text()
host_shutdown='''static void shutdown_host(void) {
  android_native_vibration_shutdown();
  opensles_shutdown();
  combo_auth_shutdown();
  SDL_Quit();
  if (socket_started) socketExit();
  if (nifm_started) nifmExit();
}'''
assert s.count(host_shutdown)==1
host_traced='static void (*memory_host_shutdown_trace)(const char *stage);\nstatic void shutdown_host(void) {\n'
for stage,call,condition in [
    ('vibration','android_native_vibration_shutdown();',None),
    ('opensles','opensles_shutdown();',None),
    ('auth','combo_auth_shutdown();',None),
    ('SDL','SDL_Quit();',None),
    ('sockets','socketExit();','socket_started'),
    ('nifm','nifmExit();','nifm_started')]:
    if condition: host_traced+=f'  if ({condition}) {{\n'
    host_traced+=f'  if(memory_host_shutdown_trace) memory_host_shutdown_trace("shutdown-host-{stage}-begin");\n'
    host_traced+=f'  {call}\n'
    host_traced+=f'  if(memory_host_shutdown_trace) memory_host_shutdown_trace("shutdown-host-{stage}-returned");\n'
    if condition: host_traced+='  }\n'
host_traced+='}'
s=s.replace(host_shutdown,host_traced)
marker='static int memory_test_main(void) {'
body=Path(__file__).with_name('real_load.c.inc').read_text()+'\n'+Path(__file__).with_name('boot_init.c.inc').read_text()
assert s.count(marker)==1
s=s.replace(marker,body+'\n'+marker)
s=s.replace('GI wrapper memory HUB 1.4', 'GI real library memory HUB 1.10')
s=s.replace('No game files required. No game loaded.', 'Reads local 6.7 files; tests JNI/graphics and one nativeRender; no login flow.')
needle='  memory_test_snapshot("end");'
assert s.count(needle)==1
s=s.replace(needle,'  if (ready && storage && !memory_test_failed) memory_real_load();\n  if (ready && storage && !memory_test_failed) memory_boot_init();\n'+needle)
s=s.replace('static FILE *memory_test_log;', 'static int memory_console_active=1;\nstatic FILE *memory_test_log;')
s=s.replace('va_start(args, format); vprintf(format, args); va_end(args);','if(memory_console_active) { va_start(args, format); vprintf(format, args); va_end(args); }')
s=s.replace('consoleUpdate(NULL);','if(memory_console_active) consoleUpdate(NULL);')
s=s.replace('  consoleExit(NULL);\n  return memory_test_failed', '  if(memory_console_active) consoleExit(NULL);\n  return memory_test_failed')
p.write_text(s)

p=root/'source/so_util.c'
s=p.read_text()
needle='        if (function != 0) ((int (*)())function)();'
assert s.count(needle)==1
s=s.replace(needle,'        if (function != 0) { memory_boot_constructor_checkpoint(j, function); ((int (*)())function)(); }')
s=s.replace('void so_execute_init_array(so_module *mod) {','extern void memory_boot_constructor_checkpoint(int index, uintptr_t address);\nvoid so_execute_init_array(so_module *mod) {')
p.write_text(s)


