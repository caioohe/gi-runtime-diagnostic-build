/* Bounded generated workloads. Never load client files or exhaust process RAM. */
typedef struct {
  unsigned char *pointer;
  size_t size;
  unsigned char seed;
} MemoryProbe;
static int memory_probe_verify(const MemoryProbe *p) {
  if (!p->pointer) return 1;
  volatile unsigned char *v = p->pointer;
  for (size_t i = 0; i < p->size; i += 4096)
    if (i != p->size - 1 && v[i] != (unsigned char)(p->seed + i / 4096)) return 0;
  return v[p->size - 1] == (unsigned char)(p->seed ^ 0xa5);
}
static int memory_probe_allocate(MemoryProbe *p, size_t bytes,
                                 size_t align, unsigned char seed, u64 *ticks) {
  u64 start = armGetSystemTick();
  p->pointer = nx_sparse_pool_spill_alloc_aligned(bytes, align);
  *ticks += armGetSystemTick() - start;
  p->size = bytes; p->seed = seed;
  if (!p->pointer) return 0;
  int aligned = !((uintptr_t)p->pointer & (align - 1));
  volatile unsigned char *v = p->pointer;
  for (size_t i = 0; i < bytes; i += 4096)
    v[i] = (unsigned char)(seed + i / 4096);
  v[bytes - 1] = (unsigned char)(seed ^ 0xa5);
  /* For size 1 or page-aligned final offset, the tail deliberately replaces
   * the page marker. Verify it separately rather than expecting both values. */
  return aligned;
}
static int memory_probe_release(MemoryProbe *p, u64 *ticks) {
  if (!p->pointer) return 1;
  u64 start = armGetSystemTick();
  int ok = nx_sparse_pool_spill_release(p->pointer);
  *ticks += armGetSystemTick() - start;
  if (ok) p->pointer = NULL;
  return ok;
}
static int memory_workload_restored(const NxSparseArenaDiagnostics *before) {
  NxSparseArenaDiagnostics d = {0}; nx_sparse_arena_get_diagnostics(&d);
  return d.spill_bytes == before->spill_bytes &&
    d.host_spill_bytes == before->host_spill_bytes &&
    d.thread_pool_bytes == before->thread_pool_bytes &&
    d.dynamic_mapped_bytes == before->dynamic_mapped_bytes &&
    d.donor_used_bytes == before->donor_used_bytes &&
    d.committed_bytes == before->committed_bytes &&
    d.reserved_bytes == before->reserved_bytes &&
    d.ownership_records_in_use == before->ownership_records_in_use &&
    d.quarantined_bytes == before->quarantined_bytes;
}
static int memory_workloads(void) {
  /* At most 208 MiB requested simultaneously; existing 8 MiB segments may
   * back more. A failed allocation triggers cleanup, not an exhaustion loop. */
  const size_t sizes[] = {1, 4095, 4096, 4097, 1048575,
                         8u*1048576+1, 33u*1048576, 72u*1048576};
  const unsigned order[] = {3, 0, 6, 2, 7, 1, 5, 4};
  NxSparseArenaDiagnostics before = {0}, after = {0};
  nx_sparse_arena_get_diagnostics(&before);
  u64 alloc_ticks = 0, free_ticks = 0;
  unsigned completed = 0;
  int all_ok = 1, cleanup_ok = 1;
  for (unsigned cycle = 0; cycle < 12; ++cycle) {
    MemoryProbe probes[8] = {0};
    int ok = 1;
    for (unsigned i = 0; i < 8; ++i) {
      size_t align = i & 1 ? 4096 : 64;
      if (!memory_probe_allocate(&probes[i], sizes[i], align,
                                 (unsigned char)(cycle*13+i), &alloc_ticks)) {
        ok = 0; break;
      }
    }
    for (unsigned i = 0; i < 8; ++i)
      if (!memory_probe_verify(&probes[i])) ok = 0;
    if (cycle == 0) memory_test_snapshot("mixed-live");
    if (ok) {
      /* Punch holes while retaining large allocations; refill one hole with
       * a larger request. Other live pages must remain unchanged. */
      ok = memory_probe_release(&probes[1], &free_ticks) &&
           memory_probe_release(&probes[5], &free_ticks);
      if (ok) ok = memory_probe_allocate(&probes[1], 96u*1048576,
                                          4096, 0x61, &alloc_ticks);
      for (unsigned i = 0; i < 8; ++i)
        if (!memory_probe_verify(&probes[i])) ok = 0;
      if (cycle == 0) memory_test_snapshot("fragmented-refilled");
    }
    for (unsigned i = 0; i < 8; ++i) {
      unsigned slot = order[i];
      if (!memory_probe_verify(&probes[slot])) ok = 0;
      if (!memory_probe_release(&probes[slot], &free_ticks)) cleanup_ok = 0;
      /* Catch corruption of survivors immediately after each out-of-order free. */
      for (unsigned j = 0; cleanup_ok && j < 8; ++j)
        if (!memory_probe_verify(&probes[j])) ok = 0;
    }
    int restored = cleanup_ok && memory_workload_restored(&before);
    memory_test_report("MIX cycle=%u integrity=%d restored=%d\n", cycle, ok, restored);
    if (!ok || !restored) { all_ok = 0; break; }
    ++completed;
  }
  nx_sparse_arena_get_diagnostics(&after);
  memory_test_report("MIX completed=%u alloc_ticks=%llu free_ticks=%llu grow_calls=%llu shrink_calls=%llu\n",
    completed, (unsigned long long)alloc_ticks, (unsigned long long)free_ticks,
    (unsigned long long)(after.donor_grow_calls-before.donor_grow_calls),
    (unsigned long long)(after.donor_shrink_calls-before.donor_shrink_calls));
  memory_test_check("mixed sizes, alignment, holes, live integrity and out-of-order cleanup",
                     all_ok && completed == 12);
  memory_test_snapshot("mixed-finished");
  return cleanup_ok && memory_workload_restored(&before);
}

/* Force public malloc entrypoints across the primary/fallback boundary without
 * filling the primary heap with artificial live allocations. */
void *nx_primary_malloc(size_t size);
void nx_primary_free(void *pointer);
static int memory_broker_tests(void) {
  const size_t big = 320u * 1048576u;
  NxSparseArenaDiagnostics baseline = {0}, live = {0};
  nx_sparse_arena_get_diagnostics(&baseline);
  void *primary = nx_primary_malloc(big);
  memory_test_check("320 MiB exceeds fixed primary heap", primary == NULL);
  if (primary) { nx_primary_free(primary); return 1; }
  for (unsigned kind = 0; kind < 3; ++kind) {
    unsigned char *p = NULL;
    if (kind == 0) p = malloc(big);
    else if (kind == 1) p = calloc(1, big);
    else { void *aligned = NULL; if (!posix_memalign(&aligned, 4096, big)) p = aligned; }
    memory_test_report("BROKER kind=%u requested=%zu\n", kind, big);
    memory_test_check("public allocation falls back after primary failure", p != NULL);
    if (!p) continue;
    nx_sparse_arena_get_diagnostics(&live);
    memory_test_check("fallback allocation tracked as host ownership",
                       live.host_spill_bytes >= baseline.host_spill_bytes + big);
    int valid = kind != 2 || !((uintptr_t)p & 4095);
    if (kind == 1) {
      /* Scan entire calloc range, not just sampled pages. */
      volatile unsigned char *v = p;
      for (size_t i = 0; i < big; ++i) if (v[i]) { valid = 0; break; }
    }
    for (size_t i = 0; i < big; i += 4096) p[i] = (unsigned char)(i/4096 + 17);
    p[big-1] = 0x71;
    unsigned char *replacement = realloc(p, big + 16u*1048576u);
    memory_test_check("grow fallback realloc", replacement != NULL);
    if (replacement) p = replacement;
    for (size_t i = 0; i < big; i += 4096)
      if (p[i] != (unsigned char)(i/4096 + 17)) valid = 0;
    if (p[big-1] != 0x71) valid = 0;
    memory_test_check("calloc/alignment and realloc preserve original bytes", valid);
    memory_test_snapshot("broker-live");
    free(p);
    int restored = memory_workload_restored(&baseline);
    memory_test_check("public free releases host ownership and mappings", restored);
    if (!restored) return 0;
  }
  memory_test_snapshot("broker-finished");
  return memory_workload_restored(&baseline);
}

