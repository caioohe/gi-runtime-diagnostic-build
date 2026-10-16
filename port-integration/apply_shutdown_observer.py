from pathlib import Path
import os,sys
r=Path(sys.argv[1]);here=Path(__file__).parent
p=r/'source/guest_termination.c';s=p.read_text();s=s.replace('static _Thread_local int termination_tracing;','''static _Thread_local int termination_tracing;
static const char *termination_kind = "none";
const char *nx_guest_termination_stage(void) { return __atomic_load_n(&termination_stage,__ATOMIC_ACQUIRE); }
const char *nx_guest_termination_kind(void) { return __atomic_load_n(&termination_kind,__ATOMIC_ACQUIRE); }''');s=s.replace('  int restored = restore_bionic_tls();','  __atomic_store_n(&termination_kind,kind,__ATOMIC_RELEASE);\n  int restored = restore_bionic_tls();');p.write_text(s)
p=r/'source/guest_termination.h';p.write_text(p.read_text()+'''const char *nx_guest_termination_stage(void);
const char *nx_guest_termination_kind(void);
void nx_shutdown_observer_start(void);
void nx_shutdown_observer_stop(void);
''')
p=r/'source/imports.c';s=p.read_text();a='void nx_guest_thread_get_diagnostics(NxGuestThreadDiagnostics *out) {';assert s.count(a)==1;s=s.replace(a,'''/* No registry lock, allocator query or thread suspension in observer. */
void nx_guest_thread_observer_counters(unsigned long long *created, unsigned long long *reaped) {
  *created = THREAD_DIAG_LOAD(guest_thread_create_successes);
  *reaped = THREAD_DIAG_LOAD(guest_thread_reaped);
}
'''+a);p.write_text(s)
p=r/'source/imports.h';p.write_text(p.read_text()+'\nvoid nx_guest_thread_observer_counters(unsigned long long *, unsigned long long *);\n')
p=r/'source/main.c';s=p.read_text();a='  error_set_cleanup(svcExitProcess);';assert s.count(a)==1;s=s.replace(a,'  nx_shutdown_observer_start();\n'+a);a='static void memory_boot_checkpoint(const char *stage) {';assert s.count(a)==1;s=s.replace(a,a+'\n  nx_guest_termination_set_stage(stage);');p.write_text(s)
build=os.environ.get('GITHUB_SHA','local-unversioned');assert all(c in '0123456789abcdef-' for c in build) or build=='local-unversioned'
(r/'source/shutdown_observer.c').write_text('#define OBSERVER_BUILD "'+build+'"\n'+(here/'shutdown_observer.c.inc').read_text())

