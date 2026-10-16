"""Preserve fatal/session history and make remaining lifecycle limits explicit."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'source/error.c';s=p.read_text();a='FILE *log = fopen("sdmc:/switch/genshinimpact_nx/fatal.txt", "w");';assert s.count(a)==1;s=s.replace(a,a.replace('"w"','"ab"'));s=s.replace('if (log) { fprintf(log, "%s\\n", message); fclose(log); }','if (log) { fprintf(log, "FATAL tick=%llu %s\\n", (unsigned long long)armGetSystemTick(), message); fflush(log); fclose(log); }');p.write_text(s)
# Refuse destructive replacement when FAT cannot rename over a destination.
# Keep the last committed version; do not remove identity or session files.
p=root/'source/combo_session.c';s=p.read_text();a=s.index('  /* FAT does not consistently replace');b=s.index('  unlink(SESSION_TEMP_PATH);',a);s=s[:a]+'''  /* A failed replacement must not erase the previous committed session.
   * Filesystems without rename-over-existing support report failure. */
'''+s[b:];p.write_text(s)
p=root/'source/android_identity.c';s=p.read_text();a=s.index('    /* Some FAT implementations');b=s.index('  }\n  unlink(ANDROID_ID_TEMP_PATH);',a);s=s[:a]+s[b:];s=s.replace('  (void)persist_android_id();','  if (!persist_android_id())\n    fprintf(stderr,"ANDROID_ID persistence failed; generated identity is process-local\\n");');p.write_text(s)
# A retry after constructors can race living guest workers. No unsafe reset.
p=root/'source/main.c';s=p.read_text();a='static void memory_boot_init(void) {';assert s.count(a)==1;s=s.replace(a,a+'''
  static int attempted;
  if(attempted) { memory_test_check("boot retry requires a new process",0); return; }
  attempted=1;
  memory_test_report("BOOT memory: guest sysconf limit=512 MiB; guest meminfo is synthetic (3 GiB total/2 GiB available); kernel usage is reported separately\\n");''')
a=s.index('static void shutdown_host(void)');b=s.index('/* Android\'s connected flag',a);part=s[a:b];part=part.replace('  socketExit();','  socketExit();\n  socket_started=0; g_net_on=0;').replace('  nifmExit();','  nifmExit();\n  nifm_started=0;');s=s[:a]+part+s[b:]
a=s.index('static void memory_boot_init(void)');b=s.index('static void memory_boot_run',a) if 'static void memory_boot_run' in s[a:] else s.index('\nstatic ',a+30)
# Record retained ownership on post-constructor failures, preserving TLS restore.
end=s.index('static void memory_boot_',a+30) if 'static void memory_boot_' in s[a+30:] else len(s)
part=s[a:end]
for reason,needle in [('bridge','if(bridge!=0) {'),('jni-self-test','if(!jni_reference_self_test()) {'),('storage-self-test','if(!unity_storage_paths_self_test()) {'),('crypto','if(combo_crypto_init()!=0) {'),('jni-export','if(!entry) {')]:
 assert part.count(needle)==1, 'unexpected failure branch: '+reason
 part=part.replace(needle,needle+f' memory_boot_teardown_checkpoint("{reason}-failure-cleanup-deferred");',1)
part=part.replace('  if(version==JNI_VERSION_1_6) memory_boot_graphics(guest_tp);','  if(version==JNI_VERSION_1_6) memory_boot_graphics(guest_tp);\n  else memory_boot_teardown_checkpoint("jni-version-failure-cleanup-deferred");')
s=s[:a]+part+s[end:];p.write_text(s)
s=p.read_text()
a='  if(trace) { fputs("HUB 1.10 runtime trace; maximum 4 MiB; contended records may be dropped\\n",trace); fclose(trace); }'
assert s.count(a)==1
s=s.replace(a,'  if(trace) fclose(trace);\n  memory_runtime_trace("HUB 1.10 smoke test; bounded trace, synchronous I/O");')
a='  memory_test_snapshot("end");'
assert s.count(a)==1
s=s.replace(a,a+'''
  extern int memory_runtime_trace_stats(char *, size_t);
  char trace_stats[256];
  if(memory_runtime_trace_stats(trace_stats,sizeof trace_stats)==0)
    memory_test_report("%s\\n",trace_stats);
  else memory_test_report("TRACE summary unavailable (contended)\\n");''')
p.write_text(s)

