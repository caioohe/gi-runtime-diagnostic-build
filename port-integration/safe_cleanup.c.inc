/* Pre-constructor rollback and post-guest process-wide reclamation. */
static void *memory_cleanup_heap_base, *memory_cleanup_slab;
static size_t memory_cleanup_heap_limit, memory_cleanup_slab_size;
static void memory_boot_process_exit(const char *stage) __attribute__((noreturn));
static void memory_boot_process_exit(const char *stage) {
  write_thread_pointer(memory_boot_host_tp);
  memory_boot_teardown_checkpoint(stage);
  memory_test_report("BOOT process exit: guest code/services stay resident until kernel termination; no per-module unload\n");
  char stats[256];
  extern int memory_runtime_trace_stats(char *,size_t);
  if(memory_runtime_trace_stats(stats,sizeof stats)==0) memory_test_report("%s\n",stats);
  if(memory_test_log) fflush(memory_test_log);
  svcExitProcess();
}
static void memory_boot_cleanup_unstarted(void) {
  /* This hook is removed before finalize/constructors: no guest has run. */
  if(game_mod.finalized || !so_is_loaded_module(&game_mod))
    memory_boot_process_exit("pre-constructor-module-guard-process-exit");
  memory_boot_teardown_checkpoint("cleanup-unstarted-plugin-begin");
  if(!plugin_loader_reset_unstarted())
    memory_boot_process_exit("pre-constructor-plugin-guard-process-exit");
  memory_boot_teardown_checkpoint("cleanup-unstarted-plugin-returned");
  memory_boot_teardown_checkpoint("cleanup-unclaimed-slab-begin");
  if(!mmap_cancel_unclaimed_unity_slab_reservation(memory_cleanup_slab,
                                                 memory_cleanup_slab_size))
    memory_boot_process_exit("pre-constructor-slab-guard-process-exit");
  memory_boot_teardown_checkpoint("cleanup-unclaimed-slab-returned");
  g_il2cpp_base=0; g_il2cpp_size=0;
  error_set_cleanup(NULL);
  memory_boot_discard_pre_slab_failure(memory_cleanup_heap_base,
                                     memory_cleanup_heap_limit);
}

