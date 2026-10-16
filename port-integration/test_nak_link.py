"""Check the actual ARM64 linked call paths, not just wrapper source presence."""
from pathlib import Path
import os,re,subprocess,sys
elf=Path(sys.argv[1]);tool=Path(os.environ['DEVKITPRO'])/'devkitA64/bin/aarch64-none-elf-objdump'
text=subprocess.check_output([str(tool),'-d',str(elf)],text=True)
def body(name):
 m=re.search(r'^\s*[0-9a-f]+ <'+re.escape(name)+r'>:\n(.*?)(?=^\s*[0-9a-f]+ <|\Z)',text,re.M|re.S);assert m,name;return m.group(1)
assert '<__wrap_nak_compile_shader>' in body('nvk_compile_shader'), 'NAK wrapper bypassed'
for name in ['nak_compile_shader','nak_compiler_create','nak_compiler_destroy','nak_shader_bin_destroy','nak_debug_flags','nak_nir_options','nak_max_warps_per_sm','nak_should_print_nir','nak_debug_no_ugpr']:
 if not re.search(r'^\s*[0-9a-f]+ <'+re.escape(name)+r'>:',text,re.M):
  assert not re.search(r'^\s*[0-9a-f]+ <__wrap_'+re.escape(name)+r'>:',text,re.M),name
  continue # --gc-sections may remove an entirely unused API pair.
 assert '<'+name+'>' in body('__wrap_'+name),name
assert '<__aarch64_read_tp>' in body('nx_compiler_host_tls_enter')
assert 'tpidr' in body('nx_compiler_host_tls_enter').lower() or 's3_3_c13_c0_2' in body('nx_compiler_host_tls_enter').lower()
assert '<__wrap_u_memstream_open>' in text and '<__wrap_u_memstream_flush>' in text
assert '<__wrap__malloc_r>' in body('internal_open_memstream_r'), 'memstream allocation bypasses host fallback'
# Reentrant wrappers must call originals, not themselves or public broker wrappers.
for name in ['_malloc_r','_calloc_r','_memalign_r','_realloc_r','_free_r']:
 b=body('__wrap_'+name);assert '<'+name+'>' in b,name
 assert '<__wrap_'+name+'>' not in b, 'recursive reentrant allocator forwarding'
for name in ['_calloc_r','_memalign_r','_realloc_r']:
 assert '<__wrap__malloc_r>' in body(name),name
for name in ['calloc','memalign','realloc']:
 assert '<__wrap__'+name+'_r>' in body(name),name
Path('nak-link-audit.txt').write_text('\n'.join('FUNCTION '+n+'\n'+body(n) for n in ['nx_compiler_host_tls_enter','__wrap_nak_compile_shader','__wrap__malloc_r','__wrap__calloc_r','__wrap__memalign_r','__wrap__realloc_r','__wrap__free_r','_calloc_r','_memalign_r','_realloc_r','calloc','memalign','realloc','internal_open_memstream_r']))
print('PASS linked ARM64 NAK/TLS and memstream allocation routes; assembly evidence only, no console runtime')

# The SDK may resolve calls within the same object without --wrap; require
# the ACTUAL exit and cross-object cleanup routes rather than source flags.
assert '<__wrap___libnx_exit>' in body('__syscall_exit')
assert '<__libnx_exit>' in body('__wrap___libnx_exit')
for name in ['__nx_win_exit','fsdevUnmountAll','fsExit','timeExit','hidExit','appletExit','smExit']:
 assert '<__wrap_'+name+'>' in body('__appExit'),name
 assert '<'+name+'>' in body('__wrap_'+name),name
with Path('nak-link-audit.txt').open('a') as out:
 for name in ['__syscall_exit','__wrap___libnx_exit','__libnx_exit','__appExit']:
  out.write('\nFUNCTION '+name+'\n'+body(name))
print('PASS linked host exit observation routes; original libnx cleanup preserved; no hardware proof')


# Unmount must pass the observer I/O fence before touching the filesystem.
b=body('__wrap_fsdevUnmountAll')
assert b.index('<nx_shutdown_observer_stop>') < b.index('<fsdevUnmountAll>')
with Path('nak-link-audit.txt').open('a') as out:
 for name in ['__wrap_fsdevUnmountAll','nx_shutdown_observer_stop','observer_main']:
  out.write('\nFUNCTION '+name+'\n'+body(name))
print('PASS linked observer-stop-before-unmount route; mutex/file behavior tested on host only')

# Imported fatal shims must reach observation before the preserved abort.
for name in ['__stack_chk_fail_fake','__cxa_pure_virtual_fake','nx_assert2','kill_fake','__FD_SET_chk_fake','__FD_ISSET_chk_fake']:
 assert '<nx_guest_fatal>' in body(name),name
b=body('nx_strcat_chk')
assert '<nx_guest_fatal>' in b or '<fortify_fail>' in b
if '<fortify_fail>' in b: assert '<nx_guest_fatal>' in body('fortify_fail')
assert '<nx_guest_fatal_begin>' in body('nx_android_log_assert')
assert '<abort>' in body('nx_android_log_assert')
b=body('nx_guest_fatal');assert b.index('<nx_guest_fatal_begin>') < b.index('<abort>')
assert '<termination_record>' in body('nx_guest_fatal_begin')
assert '<restore_bionic_tls>' in body('termination_record')
with Path('nak-link-audit.txt').open('a') as out:
 for name in ['__stack_chk_fail_fake','__cxa_pure_virtual_fake','nx_assert2','kill_fake','__FD_SET_chk_fake','__FD_ISSET_chk_fake','nx_android_log_assert','nx_guest_fatal','nx_guest_fatal_begin','termination_record']:
  out.write('\nFUNCTION '+name+'\n'+body(name))
print('PASS linked fatal shim observation and preserved abort routes; no claim this run invoked them')
