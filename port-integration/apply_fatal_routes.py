"""Observe existing fatal shims without changing their host abort endpoint."""
from pathlib import Path
import sys
r=Path(sys.argv[1])/'source'
for name,changes in {
 'imports.c':[
  ('void __stack_chk_fail_fake(void) { abort(); }','void __stack_chk_fail_fake(void) { nx_guest_fatal("abort:stack-check", 0, __builtin_return_address(0)); }'),
  ('static void __cxa_pure_virtual_fake(void) { abort(); }','static void __cxa_pure_virtual_fake(void) { nx_guest_fatal("abort:pure-virtual", 0, __builtin_return_address(0)); }')],
 'genshin_compat.c':[
  ('static void fortify_fail(void) {\n  abort();','static void fortify_fail(void) {\n  nx_guest_fatal("abort:fortify", 0, __builtin_return_address(0));'),
  ('  (void)file; (void)line; (void)function; (void)expr;\n  abort();','  (void)file; (void)function; (void)expr;\n  nx_guest_fatal("abort:assert2", line, __builtin_return_address(0));'),
  ('void nx_android_log_assert(const char *condition, const char *tag, const char *format, ...) {','void nx_android_log_assert(const char *condition, const char *tag, const char *format, ...) {\n  nx_guest_fatal_begin("abort:android-log-assert", 0, __builtin_return_address(0));')],
 'libc_shim.c':[
  ('if (!set || fd < 0 || (size_t)fd / 8u >= setlen) abort();','if (!set || fd < 0 || (size_t)fd / 8u >= setlen) nx_guest_fatal("abort:fd-bounds", fd, __builtin_return_address(0));'),
  ('      abort();','      nx_guest_fatal("abort:kill", sig, __builtin_return_address(0));')]
}.items():
 p=r/name;s=p.read_text()
 if '#include "guest_termination.h"' not in s:s='#include "guest_termination.h"\n'+s
 for a,b in changes:
  assert s.count(a)==(2 if 'setlen) abort' in a else 1),(name,a,s.count(a))
  s=s.replace(a,b)
 p.write_text(s)
