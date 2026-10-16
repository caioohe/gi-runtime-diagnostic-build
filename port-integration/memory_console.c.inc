/* Standalone entry point: original wrapper backing, no client/assets/network. */
static FILE *memory_test_log;
static unsigned memory_test_failed;
const char *nx_memory_init_stage(void);
int nx_memory_diag_set_batch(size_t bytes);
static void memory_test_report(const char *format, ...) {
  va_list args;
  va_start(args, format); vprintf(format, args); va_end(args);
  if (memory_test_log) {
    va_start(args, format); vfprintf(memory_test_log, format, args); va_end(args);
    fflush(memory_test_log);
  }
  consoleUpdate(NULL);
}
static void memory_test_snapshot(const char *stage) {
  NxSparseArenaDiagnostics d = {0};
  nx_sparse_arena_get_diagnostics(&d);
  u64 total = 0, used = 0;
  Result tr = svcGetInfo(&total, InfoType_TotalMemorySize, CUR_PROCESS_HANDLE, 0);
  Result ur = svcGetInfo(&used, InfoType_UsedMemorySize, CUR_PROCESS_HANDLE, 0);
  u64 aslr = 0, alias = 0;
  Result ar = svcGetInfo(&aslr, InfoType_AslrRegionSize, CUR_PROCESS_HANDLE, 0);
  Result alr = svcGetInfo(&alias, InfoType_AliasRegionSize, CUR_PROCESS_HANDLE, 0);
  memory_test_report("SPACE aslr_rc=%08x aslr_bytes=%llu alias_rc=%08x alias_bytes=%llu\n"
    " arena_target=%zu donor_capacity=%zu init_stage=%s\n",
    (unsigned)ar, (unsigned long long)aslr, (unsigned)alr,
    (unsigned long long)alias, nx_dynamic_arena_target_bytes(),
    g_heap_donor_capacity, nx_memory_init_stage());
  memory_test_report("MEM %s total_rc=%08x used_rc=%08x total=%llu used=%llu\n"
    " kernel_heap=%zu fixed=%zu loader_prefix=%zu backend=%u\n"
    " donor_active=%llu donor_used=%llu grow=%llu shrink=%llu rc=%08x\n"
    " dynamic_mapped=%llu committed=%llu spill=%llu host=%llu threads=%llu\n"
    " records=%llu quarantine=%llu largest_free=%llu\n",
    stage, (unsigned)tr, (unsigned)ur, (unsigned long long)total,
    (unsigned long long)used, g_kernel_heap_bytes, g_fixed_heap_bytes,
    g_loader_heap_prefix_bytes, d.backing_backend,
    (unsigned long long)d.donor_active_bytes, (unsigned long long)d.donor_used_bytes,
    (unsigned long long)d.donor_grow_calls, (unsigned long long)d.donor_shrink_calls,
    d.donor_last_resize_result, (unsigned long long)d.dynamic_mapped_bytes,
    (unsigned long long)d.committed_bytes, (unsigned long long)d.spill_bytes,
    (unsigned long long)d.host_spill_bytes, (unsigned long long)d.thread_pool_bytes,
    (unsigned long long)d.ownership_records_in_use,
    (unsigned long long)d.quarantined_bytes, (unsigned long long)d.pool_largest_free_bytes);
}
static void memory_test_check(const char *name, int ok) {
  if (!ok) ++memory_test_failed;
  memory_test_report("%s %s\n", ok ? "PASS" : "FAIL", name);
}
static int memory_test_main(void) {
  consoleInit(NULL);
  mkdir("sdmc:/switch", 0777);
  mkdir("sdmc:/switch/gi-runtime-diagnostic", 0777);
  char log_path[160];
  snprintf(log_path, sizeof log_path,
    "sdmc:/switch/gi-runtime-diagnostic/memory-%llx.log",
    (unsigned long long)armGetSystemTick());
  memory_test_log = fopen(log_path, "w");
  memory_test_report("GI wrapper memory HUB 1.4\nNo game files required. No game loaded.\n");
  memory_test_check("open diagnostic log", memory_test_log != NULL);
  memory_test_snapshot("bootstrap");
  check_syscalls();
  validate_fixed_heap_reclaim();
  memory_test_check("original heap boundary validation", 1);
  int context = check_thread_context_bridge();
  memory_test_check("native thread context bridge", context == 0);
  int storage = pthread_storage_self_test();
  memory_test_check("original pthread storage", storage);
  initialize_sparse_arena();
  int ready = g_oc_want == 2;
  memory_test_check("original sparse backing initialized", ready);
  memory_test_report("INIT stage=%s\n", nx_memory_init_stage());
  if (!ready && !nx_dynamic_arena_target_bytes())
    memory_test_report("BLOCKED: original wrapper requires ASLR >64 GiB (39-bit process)\n"
      "and compatible alias capacity for the physical backend. This is virtual address\n"
      "space, not physical RAM. No game or allocation test was executed.\n");
  memory_test_snapshot("arena-ready");
  if (ready && storage) {
    memory_test_report("EXPERIMENT fixed_newlib_MiB=256 original=1024; no game compatibility claim\n");
    int broker_clean = memory_broker_tests();
    if (!broker_clean) ready = 0;
  }
  if (ready && storage) {
    for (unsigned policy = 0; policy < 2; ++policy) {
    size_t batch = (policy ? 32u : 256u) * 1024u * 1024u;
    memory_test_report("POLICY batch_MiB=%u\n", policy ? 32u : 256u);
    if (!nx_memory_diag_set_batch(batch)) {
      memory_test_check("select policy only with all donor backing released", 0);
      break;
    }
    NxSparseArenaDiagnostics before = {0}, after = {0};
    nx_sparse_arena_get_diagnostics(&before);
    const size_t bytes = 72u * 1024u * 1024u;
    void *p = nx_sparse_pool_spill_alloc_aligned(bytes, 64);
    memory_test_check("72 MiB allocation", p != NULL);
    if (p) {
      volatile unsigned char *v = p;
      for (size_t i = 0; i < bytes; i += 4096) v[i] = (unsigned char)(i / 4096);
      int valid = 1;
      for (size_t i = 0; i < bytes; i += 4096)
        if (v[i] != (unsigned char)(i / 4096)) valid = 0;
      memory_test_check("touch and verify each allocation page", valid);
      memory_test_snapshot("72MiB-live");
      memory_test_check("release measured allocation", nx_sparse_pool_spill_release(p));
    }
    nx_sparse_arena_get_diagnostics(&after);
    memory_test_check("allocation restores ownership and mappings",
      after.spill_bytes == before.spill_bytes &&
      after.dynamic_mapped_bytes == before.dynamic_mapped_bytes &&
      after.donor_used_bytes == before.donor_used_bytes &&
      after.ownership_records_in_use == before.ownership_records_in_use &&
      after.quarantined_bytes == before.quarantined_bytes);
    memory_test_snapshot("72MiB-released");
    if (!memory_workload_restored(&before)) {
      memory_test_report("SKIP dependent stages: measured allocation did not clean up\n");
      break;
    }
    if (!memory_workloads()) {
      memory_test_report("SKIP dependent stages: mixed workload did not clean up\n");
      break;
    }
    }
    int clean = nx_memory_diag_set_batch(32u*1024u*1024u);
    memory_test_check("restore optimized 32 MiB policy", clean);
    for (unsigned round = 0; clean && round < 3; ++round) {
      memory_test_report("ROUND %u\n", round);
      memory_test_check("original guest spill lifecycle", sparse_guest_spill_self_test());
      memory_test_report("guest_stage=%s\n", g_sparse_guest_test_failure);
      memory_test_check("original alias mmap lifecycle", sparse_alias_mmap_self_test());
      memory_test_report("mmap_stage=%s\n", g_sparse_mmap_test_failure);
      memory_test_check("original caller-owned thread stack", sparse_thread_stack_self_test());
      memory_test_snapshot("round-finished");
    }
  }
  memory_test_snapshot("end");
  memory_test_report("RESULT failed=%u\nLOG %s\nPress + to exit.\n",
                     memory_test_failed, log_path);
  if (memory_test_log) { fclose(memory_test_log); memory_test_log = NULL; }
  PadState pad; padConfigureInput(1, HidNpadStyleSet_NpadStandard);
  padInitializeDefault(&pad);
  while (appletMainLoop()) {
    padUpdate(&pad);
    if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
    consoleUpdate(NULL);
  }
  consoleExit(NULL);
  return memory_test_failed ? 1 : 0;
}

