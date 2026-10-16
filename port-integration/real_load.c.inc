/* Diagnostic uses the original export catalog; no substitute imports. */
static uintptr_t memory_real_import(const char *name, void *opaque) {
  (void)opaque;
  return dynlib_find_export(name);
}

/* Same RX/RW page policy as original so_finalize, with recoverable errors.
 * Keep metadata on source addresses because no guest lookup/execution occurs. */
static int memory_real_mapping(so_module *m) {
  size_t pages = m->load_size / 4096;
  unsigned char *exec = calloc(pages, 1);
  memory_test_check("allocate original executable-page bitmap", exec != NULL);
  if (!exec) return 1;
  for (int i=0; i<m->phnum; ++i) {
    const Elf64_Phdr *p=&m->phdr[i];
    if (p->p_type != PT_LOAD || !(p->p_flags & PF_X)) continue;
    size_t first=p->p_vaddr/4096, end=(p->p_vaddr+p->p_memsz+4095)/4096;
    if (first>pages || end>pages) { free(exec); memory_test_check("executable segment page bounds", 0); return 1; }
    for (size_t j=first;j<end;++j) exec[j]=1;
  }
  Result rc=svcMapProcessCodeMemory(envGetOwnProcessHandle(), (u64)m->load_virtbase, (u64)m->load_base, m->load_size);
  memory_test_report("REAL map_rc=%08x destination=%p bytes=%zu\n", rc, m->load_virtbase, m->load_size);
  memory_test_check("map relocated real library with original code-memory SVC", R_SUCCEEDED(rc));
  if (R_FAILED(rc)) { free(exec); return 1; }
  int valid=1;
  for (int want=1;want>=0 && valid;--want) {
    size_t pg=0;
    while (pg<pages) {
      if (exec[pg]!=want) { ++pg; continue; }
      size_t end=pg+1; while(end<pages && exec[end]==want) ++end;
      rc=svcSetProcessMemoryPermission(envGetOwnProcessHandle(), (u64)m->load_virtbase+pg*4096, (end-pg)*4096, want?Perm_Rx:Perm_Rw);
      if (R_FAILED(rc)) { memory_test_report("REAL permissions_rc=%08x page=%zu\n",rc,pg); valid=0; break; }
      pg=end;
    }
  }
  memory_test_check("apply original RX/RW permissions",valid);
  if (valid) {
    for(size_t pg=0;pg<pages;++pg) {
      MemoryInfo info; u32 page_info;
      rc=svcQueryMemory(&info,&page_info,(u64)m->load_virtbase+pg*4096);
      if(R_FAILED(rc) || info.perm!=(exec[pg]?Perm_Rx:Perm_Rw)) { valid=0; break; }
    }
    memory_test_check("query every real-image page: expected permissions and no RWX",valid);
    memory_test_snapshot("real-image-mapped");
  }
  free(exec);
  rc=svcUnmapProcessCodeMemory(envGetOwnProcessHandle(), (u64)m->load_virtbase, (u64)m->load_base, m->load_size);
  memory_test_report("REAL unmap_rc=%08x\n",rc);
  memory_test_check("unmap real library before releasing reservation",R_SUCCEEDED(rc));
  if(R_FAILED(rc)) return 0; /* reservation/source must remain intact until exit */
  MemoryInfo info; u32 page_info;
  rc=svcQueryMemory(&info,&page_info,(u64)m->load_base);
  memory_test_check("source backing becomes writable again after unmap",R_SUCCEEDED(rc) && info.perm==Perm_Rw);
  return 1;
}

static void memory_real_load(void) {
  const char *path = GAME_HOME "/lib/arm64-v8a/libyuanshen.so";
  struct stat st;
  memory_test_report("REAL path=%s\n", path);
  int present = stat(path, &st) == 0 && S_ISREG(st.st_mode);
  memory_test_check("real library exists at configured absolute path", present);
  if (!present) {
    memory_test_report("ACTION copy arm64-v8a contents into %s/lib/arm64-v8a/\n", GAME_HOME);
    return;
  }
  memory_test_report("REAL file_bytes=%llu capacity_bytes=%zu\n",
                     (unsigned long long)st.st_size, heap_so_limit);
  memory_test_snapshot("before-real-load");
  u64 tick = armGetSystemTick();
  int rc = so_load(&game_mod, path, heap_so_base, heap_so_limit);
  memory_test_report("REAL so_load_rc=%d ticks=%llu image_bytes=%zu\n", rc,
                    (unsigned long long)(armGetSystemTick()-tick), game_mod.load_size);
  memory_test_check("original loader streams real ELF into dedicated module region", rc == 0);
  if (rc != 0) return;
  memory_test_snapshot("real-image-resident");
  int matched = supported_game_image();
  memory_test_check("real image matches original 6.7 load span and five instruction fingerprints", matched);
  int valid = 1;
  for (int i=0; i<game_mod.phnum; ++i) {
    const Elf64_Phdr *ph = &game_mod.prog_hdr[i];
    if (ph->p_type != PT_LOAD || ph->p_memsz == ph->p_filesz) continue;
    size_t offset = (size_t)(ph->p_vaddr - (uintptr_t)game_mod.load_virtbase);
    volatile unsigned char *b = (unsigned char *)game_mod.load_base + offset;
    for (size_t j=ph->p_filesz; j<ph->p_memsz; ++j)
      if (b[j]) { valid=0; break; }
  }
  memory_test_check("all real ELF BSS bytes initialized to zero", valid);
  if (matched && valid) {
    memory_test_report("REAL testing original host allocator while library remains resident\n");
    if (memory_broker_tests()) memory_workloads();
  }
  int can_discard=1;
  if (matched && valid) {
    char error[256];
    int preflight=so_preflight_imports(&game_mod,memory_real_import,NULL,error,sizeof(error));
    memory_test_report("REAL preflight_rc=%d detail=%s\n",preflight,error);
    memory_test_check("all real relocations preflight against original import catalog",preflight==0);
    if(preflight==0) {
      int reloc=so_relocate(&game_mod);
      memory_test_check("apply original real ELF relocations",reloc==0);
      int imports=reloc==0?so_resolve_imports(&game_mod,memory_real_import,NULL,error,sizeof(error)):-1;
      memory_test_report("REAL resolve_rc=%d detail=%s\n",imports,error);
      memory_test_check("bind real imports to original wrapper exports",imports==0);
      if(imports==0) can_discard=memory_real_mapping(&game_mod);
    }
  }
  if (!can_discard) {
    memory_test_report("NOTE unmap failed: retain image and reservation until process exit.\n");
    return;
  }
  so_discard_unfinalized(&game_mod);
  memory_test_check("discard real ELF metadata and virtual reservation", game_mod.so_base == NULL && game_mod.load_memrv == NULL);
  memory_test_snapshot("real-load-finished");
  memory_test_report("NOTE module backing is part of fixed retained heap; discard does not release 416 MiB.\n"
                     "NOTE imports/relocations/mapping tested when preflight succeeds; no guest entrypoints executed.\n");
}

