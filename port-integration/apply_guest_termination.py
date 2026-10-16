from pathlib import Path
import sys
root=Path(sys.argv[1]); here=Path(__file__).parent
(root/'source/guest_termination.c').write_text((here/'guest_termination.c.inc').read_text())
(root/'source/guest_termination.h').write_text('''#pragma once
void nx_guest_termination_set_stage(const char *stage);
void nx_guest_exit(int status) __attribute__((noreturn));
void nx_guest_immediate_exit(int status) __attribute__((noreturn));
void nx_guest_abort(void) __attribute__((noreturn));
void nx_guest_fatal_begin(const char *reason, int detail, void *caller);
void nx_guest_fatal(const char *reason, int detail, void *caller) __attribute__((noreturn));
''')
for file,replacements in [('imports.c',{'{ "abort", (uintptr_t)&abort }':'{ "abort", (uintptr_t)&nx_guest_abort }','{ "_exit", (uintptr_t)&exit }':'{ "_exit", (uintptr_t)&nx_guest_immediate_exit }'}),('unity_imports.c',{'{ "exit", (uintptr_t)&exit }':'{ "exit", (uintptr_t)&nx_guest_exit }'})]:
 p=root/'source'/file;s=p.read_text();s='#include "guest_termination.h"\n'+s
 for old,new in replacements.items():assert s.count(old)==1;s=s.replace(old,new)
 p.write_text(s)
p=root/'source/main.c';s=p.read_text();s='#include "guest_termination.h"\n'+s
old='static void memory_boot_teardown_checkpoint(const char *stage) {';assert s.count(old)==1
s=s.replace(old,old+'\n  nx_guest_termination_set_stage(stage);');p.write_text(s)

