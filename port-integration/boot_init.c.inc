/* Diagnostic boot and one render; no login/download/gameplay loop. */
extern void memory_runtime_trace(const char *format, ...);
static uintptr_t memory_boot_host_tp;
static u64 memory_boot_main_thread;
static void memory_boot_checkpoint(const char *stage) {
  uintptr_t current=read_thread_pointer();
  write_thread_pointer(memory_boot_host_tp);
  memory_test_report("BOOT checkpoint=%s\n",stage);
  memory_runtime_trace("BOOT %s",stage);
  memory_test_snapshot(stage);
  write_thread_pointer(current);
}
void memory_boot_constructor_checkpoint(int index, uintptr_t address) {
  u64 id=0;
  if(R_FAILED(svcGetThreadId(&id,CUR_THREAD_HANDLE)) || id!=memory_boot_main_thread) return;
  uintptr_t guest=read_thread_pointer();
  write_thread_pointer(memory_boot_host_tp);
  memory_test_report("BOOT constructor=%d address=0x%llx before-call\n",index,(unsigned long long)address);
  memory_test_snapshot("constructor-before-call");
  write_thread_pointer(guest);
}
static int memory_boot_requirements(void) {
  struct Requirement { const char *path; uint64_t minimum; };
  static const struct Requirement required[]={
    {LIB_GAME,300ULL*1024*1024},
    {"assets/bin/Data/globalgamemanagers",1024},
    {"assets/bin/Data/Managed/Metadata/global-metadata.dat",1024*1024},
    {"assets/bin/Data/Managed/Metadata/global-metadata.md5",32},
    {"assets/bin/Data/Managed/Metadata/startup-metadata.dat",1024*1024},
    {"assets/bin/Data/boot.config",16}, {"assets/bin/Data/level0",1024},
    {"assets/AssetBundles/data_revision",1},
    {"assets/data_versions_streaming",1}, {"assets/res_versions_streaming",1},
    {"assets/svc_catalog",1}, {"certs/cacert.pem",100*1024},
    {"lib/arm64-v8a/libMHYComboCrypto.so",1}
  };
  int ok=1;
  for(size_t i=0;i<sizeof(required)/sizeof(required[0]);++i) {
    uint64_t size=0; int present=data_regular_size(required[i].path,&size) && size>=required[i].minimum;
    memory_test_report("PREREQ %s path=%s/%s bytes=%llu minimum=%llu\n",present?"PASS":"MISSING",GAME_HOME,required[i].path,(unsigned long long)size,(unsigned long long)required[i].minimum);
    if(!present) ok=0;
  }
  if(ok) {
    ok=file_contains("certs/cacert.pem","-----BEGIN CERTIFICATE-----") && file_contains("assets/bin/Data/globalgamemanagers","2017.4.30f1");
    memory_test_check("CA bundle and Unity version markers",ok);
  }
  memory_test_check("all startup prerequisites present",ok);
  return ok;
}
/* Geometry failed before this path called nativeRecreateGfxState. Recover
 * diagnostics only if the default window has no configured buffer owner. */
static int memory_boot_recover_geometry_console(void) {
  NWindow *window=nwindowGetDefault();
  if(!window || !nwindowIsValid(window)) {
    memory_test_report("BOOT console recovery unavailable: invalid default window\n");
    return 0;
  }
  mutexLock(&window->mutex);
  int available=window->slots_configured==0;
  mutexUnlock(&window->mutex);
  if(!available) {
    memory_test_report("BOOT console recovery unavailable: window buffers still configured\n");
    return 0;
  }
  memory_console_active=consoleInit(NULL)!=NULL;
  memory_test_report("BOOT geometry failure console_restored=%d\n",memory_console_active);
  return memory_console_active;
}
/* Teardown records avoid allocator snapshots and temporarily use host TLS. */
static void memory_boot_teardown_checkpoint(const char *stage) {
  uintptr_t current=read_thread_pointer();
  write_thread_pointer(memory_boot_host_tp);
  memory_runtime_trace("BOOT %s",stage);
  write_thread_pointer(current);
}
/* Only before opensles, module loading and guest constructors. */
static void memory_boot_cleanup_early_services(int sdl_attempted, int auth_started) {
  if(sdl_attempted) {
    memory_boot_teardown_checkpoint("init-failure-SDL-begin");
    SDL_Quit();
    memory_boot_teardown_checkpoint("init-failure-SDL-returned");
  }
  if(auth_started) {
    memory_boot_teardown_checkpoint("init-failure-auth-begin");
    combo_auth_shutdown();
    memory_boot_teardown_checkpoint("init-failure-auth-returned");
  }
  if(socket_started) {
    memory_boot_teardown_checkpoint("init-failure-sockets-begin");
    socketExit();
    socket_started=0; g_net_on=0;
    memory_boot_teardown_checkpoint("init-failure-sockets-returned");
  }
  if(nifm_started) {
    memory_boot_teardown_checkpoint("init-failure-nifm-begin");
    nifmExit();
    nifm_started=0;
    memory_boot_teardown_checkpoint("init-failure-nifm-returned");
  }
}
/* Only rejection before any slab/plugin/finalize/constructor acquisition. */
static void memory_boot_discard_pre_slab_failure(void *saved_base, size_t saved_limit) {
  if(game_mod.finalized || !so_is_loaded_module(&game_mod)) {
    memory_test_report("BOOT pre-slab cleanup refused: unexpected module lifecycle\n");
    return;
  }
  memory_boot_teardown_checkpoint("pre-slab-failure-discard-begin");
  so_discard_unfinalized(&game_mod);
  heap_so_base=saved_base; heap_so_limit=saved_limit;
  memory_boot_teardown_checkpoint("pre-slab-failure-discard-returned");
  memory_boot_teardown_checkpoint("pre-slab-failure-opensles-begin");
  opensles_shutdown();
  memory_boot_teardown_checkpoint("pre-slab-failure-opensles-returned");
  memory_boot_cleanup_early_services(1,1);
}
static void memory_boot_cleanup_slab_failure(void *saved_base, size_t saved_limit) {
  UnitySlabMmapDiagnostics d={0};
  int available=mmap_get_unity_slab_diagnostics(&d);
  memory_test_report("BOOT slab failure snapshot=%d state=%u base=0x%llx size=%llu committed=%u\n",
    available,(unsigned)d.reservation_state,(unsigned long long)d.reservation_base,
    (unsigned long long)d.reservation_size,(unsigned)d.committed_chunks);
  /* Pinned wrapper state 0 is EMPTY. This is a pre-guest snapshot, not
   * synchronization against a future concurrent slab claimant. */
  if(!available || d.reservation_state!=0 || d.reservation_base ||
     d.reservation_size || d.committed_chunks) {
    memory_boot_teardown_checkpoint("slab-failure-cleanup-deferred");
    return;
  }
  memory_boot_discard_pre_slab_failure(saved_base,saved_limit);
}
static void memory_boot_graphics(uintptr_t guest_tp) {
  extern void *fake_env, *fake_unityplayer_thiz, *fake_context_obj, *fake_surface_obj;
  write_thread_pointer(guest_tp);
  memory_boot_checkpoint("NativeLoader.load-begin");
  const GenshinJniNativeMethod *loader=(const GenshinJniNativeMethod *)((uintptr_t)game_mod.load_virtbase+GENSHIN_NATIVELOADER_TABLE_RVA);
  validate_native_table(loader,GENSHIN_NATIVELOADER_COUNT,"NativeLoader");
  NativeLoaderLoadFn load=(NativeLoaderLoadFn)find_native(loader,GENSHIN_NATIVELOADER_COUNT,"load","(Ljava/lang/String;)Z");
  void *path=jni_make_string(DATA_ROOT "/" LIB_GAME);
  jni_boundary_begin("NativeLoader.load"); int ok=load(fake_env,fake_unityplayer_thiz,path); jni_boundary_end();
  write_thread_pointer(memory_boot_host_tp); memory_test_check("original NativeLoader.load",ok); write_thread_pointer(guest_tp);
  if(!ok) { write_thread_pointer(memory_boot_host_tp); return; }
  const GenshinJniNativeMethod *table=(const GenshinJniNativeMethod *)((uintptr_t)game_mod.load_virtbase+GENSHIN_UNITY_TABLE_RVA);
  validate_native_table(table,GENSHIN_UNITY_TABLE_COUNT,"UnityPlayer");
  fn_initJni init=(fn_initJni)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"initJni","(Landroid/content/Context;)V");
  fn_gfxstate gfx=(fn_gfxstate)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"nativeRecreateGfxState","(ILandroid/view/Surface;)V");
  fn_v resume=(fn_v)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"nativeResume","()V");
  fn_vz focus=(fn_vz)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"nativeFocusChanged","(Z)V");
  fn_z render=(fn_z)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"nativeRender","()Z");
  NativePauseFn pause=(NativePauseFn)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"nativePause","()Z");
  fn_v done=(fn_v)find_native(table,GENSHIN_UNITY_TABLE_COUNT,"nativeDone","()V");
  memory_boot_checkpoint("Unity.initJni-begin");
  jni_boundary_begin("initJni"); init(fake_env,fake_unityplayer_thiz,fake_context_obj); jni_boundary_end();
  memory_boot_checkpoint("Unity.initJni-returned");
  /* Give the original renderer exclusive ownership of the default NWindow. */
  write_thread_pointer(memory_boot_host_tp); consoleExit(NULL); memory_console_active=0;
  write_thread_pointer(guest_tp);
  memory_boot_checkpoint("window-geometry-begin");
  int geometry=android_native_apply_window_geometry();
  if(geometry!=0) {
    write_thread_pointer(memory_boot_host_tp);
    memory_test_check("native window geometry",0);
    memory_test_report("BOOT geometry_error=%d\n",geometry);
    (void)memory_boot_recover_geometry_console();
    memory_boot_checkpoint("window-geometry-failed");
    return;
  }
  memory_boot_checkpoint("nativeRecreateGfxState-begin");
  jni_boundary_begin("nativeRecreateGfxState"); gfx(fake_env,fake_unityplayer_thiz,0,fake_surface_obj); jni_boundary_end();
  memory_boot_checkpoint("nativeRecreateGfxState-returned");
  jni_boundary_begin("resume/focus"); resume(fake_env,fake_unityplayer_thiz); focus(fake_env,fake_unityplayer_thiz,1); jni_boundary_end();
  opensles_set_focus(1); combo_bridge_set_focus(1);
  (void)android_native_looper_pump_callbacks(8);
  memory_boot_checkpoint("first-nativeRender-begin");
  jni_boundary_begin("nativeRender"); int rendered=render(fake_env,fake_unityplayer_thiz); jni_boundary_end();
  write_thread_pointer(memory_boot_host_tp);
  memory_test_report("BOOT nativeRender_return=%d (return is not proof of a visible frame)\n",rendered);
  write_thread_pointer(guest_tp); memory_boot_checkpoint("first-nativeRender-returned");
  memory_boot_checkpoint("graphics-shutdown-begin");
  memory_boot_teardown_checkpoint("shutdown-audio-focus-begin");
  opensles_set_focus(0);
  memory_boot_teardown_checkpoint("shutdown-audio-focus-returned");
  memory_boot_teardown_checkpoint("shutdown-bridge-focus-begin");
  combo_bridge_set_focus(0);
  memory_boot_teardown_checkpoint("shutdown-bridge-focus-returned");
  jni_boundary_begin("shutdown focus/pause");
  memory_boot_teardown_checkpoint("shutdown-nativeFocusChanged-begin");
  focus(fake_env,fake_unityplayer_thiz,0);
  memory_boot_teardown_checkpoint("shutdown-nativeFocusChanged-returned");
  memory_boot_teardown_checkpoint("shutdown-nativePause-begin");
  (void)pause(fake_env,fake_unityplayer_thiz);
  memory_boot_teardown_checkpoint("shutdown-nativePause-returned");
  jni_boundary_end();
  memory_boot_teardown_checkpoint("shutdown-combo-bridge-begin");
  combo_bridge_shutdown();
  memory_boot_teardown_checkpoint("shutdown-combo-bridge-returned");
  jni_boundary_begin("shutdown graphics/done");
  memory_boot_teardown_checkpoint("shutdown-nativeRecreateGfxState-begin");
  gfx(fake_env,fake_unityplayer_thiz,0,NULL);
  memory_boot_teardown_checkpoint("shutdown-nativeRecreateGfxState-returned");
  memory_boot_teardown_checkpoint("shutdown-nativeDone-begin");
  done(fake_env,fake_unityplayer_thiz);
  memory_boot_teardown_checkpoint("shutdown-nativeDone-returned");
  jni_boundary_end();
  write_thread_pointer(memory_boot_host_tp);
  memory_boot_teardown_checkpoint("shutdown-host-begin");
  memory_host_shutdown_trace=memory_boot_teardown_checkpoint;
  shutdown_host();
  memory_host_shutdown_trace=NULL;
  memory_boot_teardown_checkpoint("shutdown-host-returned");
  memory_boot_teardown_checkpoint("shutdown-consoleInit-begin");
  consoleInit(NULL); memory_console_active=1;
  memory_boot_teardown_checkpoint("shutdown-consoleInit-returned");
  memory_boot_checkpoint("graphics-shutdown-finished");
  memory_test_report("NOTE one nativeRender call attempted; no login/gameplay claim.\n");
}
static int memory_string_broker_test(void) {
  const size_t bytes=320u*1024u*1024u;
  NxSparseArenaDiagnostics before={0},after={0};
  nx_sparse_arena_get_diagnostics(&before);
  char *source=malloc(bytes);
  memory_test_check("allocate 320 MiB string source",source!=NULL);
  if(!source) return 0;
  memset(source,'S',bytes-1); source[bytes-1]=0;
  char *(*volatile duplicate)(const char *)=strdup;
  char *copy=duplicate(source);
  int valid=copy && copy!=source;
  if(copy) {
    for(size_t j=0;j<bytes-1;++j) if(copy[j]!='S') { valid=0; break; }
    if(copy[bytes-1]!=0) valid=0;
  }
  memory_test_check("strdup larger than primary heap preserves entire string and terminator",valid);
  memory_test_snapshot("large-strdup-live");
  free(copy); free(source);
  char *(*volatile bounded)(const char *,size_t)=strndup;
  const char input[3]={'a','b','c'};
  char *small=bounded(input,3);
  int bounded_ok=small && !memcmp(small,"abc",4);
  memory_test_check("strndup accepts bounded input without an existing terminator",bounded_ok);
  free(small);
  nx_sparse_arena_get_diagnostics(&after);
  int released=after.host_spill_bytes==before.host_spill_bytes && after.dynamic_mapped_bytes==before.dynamic_mapped_bytes && after.ownership_records_in_use==before.ownership_records_in_use;
  memory_test_check("string duplication cleanup restores broker ownership and mappings",released);
  return valid && bounded_ok && released;
}
static void memory_boot_init(void) {
  if(!memory_string_broker_test()) return;
  memory_boot_host_tp=read_thread_pointer();
  if(R_FAILED(svcGetThreadId(&memory_boot_main_thread,CUR_THREAD_HANDLE))) { memory_test_check("identify main thread for constructor logging",0); return; }
  /* Run separator preserves all existing exception records. */
  FILE *fatal=fopen(GAME_HOME "/fatal.txt","ab");
  if(fatal) { fprintf(fatal,"\n=== HUB 1.10 RUN tick=%llu ===\n",(unsigned long long)armGetSystemTick()); fflush(fatal); fclose(fatal); }
  FILE *trace=fopen(GAME_HOME "/runtime-trace.txt","wb");
  if(trace) { fputs("HUB 1.10 runtime trace; maximum 4 MiB; contended records may be dropped\n",trace); fclose(trace); }
  memory_boot_checkpoint("prerequisites-begin");
  if(chdir(DATA_ROOT)!=0) { memory_test_check("enter game directory",0); return; }
  /* Existing packs may be read; never call prepare_game_data/build/cleanup. */
  (void)asset_pack_open_existing(DATA_ROOT);
  if(!memory_boot_requirements()) {
    memory_test_report("ACTION supply every MISSING path above; no guest code executed.\n");
    return;
  }
  memory_test_check("exact original 6.7 library SHA256",exact_game_library_hash());
  if(memory_test_failed) return;
  make_runtime_dirs();
  const char *config_path=DATA_ROOT "/" CONFIG_NAME;
  if(read_config(config_path)!=0) write_config(config_path);
  memory_test_check("original Vulkan configuration enabled",config.force_vulkan);
  if(!config.force_vulkan) return;
  memory_boot_checkpoint("host-services-begin");
  nifm_started=R_SUCCEEDED(nifmInitialize(NifmServiceType_User));
  SocketInitConfig sockets=*socketGetDefaultInitConfig(); sockets.num_bsd_sessions=NETWORK_BSD_SESSION_COUNT;
  Result rc=socketInitialize(&sockets); socket_started=R_SUCCEEDED(rc); g_net_on=socket_started;
  memory_test_report("BOOT sockets_rc=%08x\n",rc);
  memory_test_check("original socket services initialized",socket_started);
  if(!socket_started) {
    /* No auth, SDL or guest code has started on this failure path. */
    if(nifm_started) {
      memory_boot_teardown_checkpoint("socket-failure-nifmExit-begin");
      nifmExit();
      nifm_started=0;
      memory_boot_teardown_checkpoint("socket-failure-nifmExit-returned");
    }
    return;
  }
  network_configure_long_stream_receive_window(sockets.tcp_rx_buf_size,sockets.tcp_rx_buf_max_size);
  int auth_result=combo_auth_init();
  memory_test_check("original HTTPS client initialization",auth_result==0);
  if(memory_test_failed) { memory_boot_cleanup_early_services(0,auth_result==0); return; }
  initialize_network_state(); (void)android_native_update_mode();
  SDL_SetMainReady(); memory_test_check("original SDL audio/input initialization",SDL_Init(SDL_INIT_AUDIO|SDL_INIT_GAMECONTROLLER)==0);
  if(memory_test_failed) { memory_boot_cleanup_early_services(1,1); return; }
  (void)opensles_initialize();
  memory_boot_checkpoint("real-load-begin");
  void *module_heap_base=heap_so_base; size_t module_heap_limit=heap_so_limit;
  int loaded=load_game_module(); memory_test_check("original game module load and imports",loaded==0);
  if(loaded!=0) {
    /* so_load has rolled back its temporary metadata/reservation; imports
     * and constructors have not run. Preserve its error and heap cursor. */
    memory_boot_teardown_checkpoint("load-failure-opensles-begin");
    opensles_shutdown();
    memory_boot_teardown_checkpoint("load-failure-opensles-returned");
    memory_boot_cleanup_early_services(1,1);
    return;
  }
  memory_test_check("supported original image fingerprints",supported_game_image());
  if(memory_test_failed) { memory_boot_discard_pre_slab_failure(module_heap_base,module_heap_limit); return; }
  void *slab=NULL; size_t slab_size=0;
  memory_test_check("original Unity slab virtual reservation",mmap_prepare_unity_slab_reservation(&slab,&slab_size));
  if(memory_test_failed) { memory_boot_cleanup_slab_failure(module_heap_base,module_heap_limit); return; }
  memory_boot_checkpoint("asset-access-checks-begin");
  memory_boot_teardown_checkpoint("asset-check-cpu-begin");
  check_synthetic_cpu_topology_read();
  memory_boot_teardown_checkpoint("asset-check-cpu-returned");
  memory_boot_teardown_checkpoint("asset-check-vulkan-sentinel-begin");
  check_force_vulkan_sentinel();
  memory_boot_teardown_checkpoint("asset-check-vulkan-sentinel-returned");
  memory_boot_teardown_checkpoint("asset-check-egl-begin");
  check_vulkan_egl_configuration();
  memory_boot_teardown_checkpoint("asset-check-egl-returned");
  memory_boot_teardown_checkpoint("asset-check-globalgamemanagers-begin");
  check_globalgamemanagers_seek_read();
  memory_boot_teardown_checkpoint("asset-check-globalgamemanagers-returned");
  memory_boot_teardown_checkpoint("asset-check-metadata-digest-begin");
  check_global_metadata_digest_read();
  memory_boot_teardown_checkpoint("asset-check-metadata-digest-returned");
  memory_boot_teardown_checkpoint("asset-check-startup-mapping-begin");
  check_startup_metadata_mapping();
  memory_boot_teardown_checkpoint("asset-check-startup-mapping-returned");
  g_il2cpp_base=(uintptr_t)game_mod.load_virtbase; g_il2cpp_size=game_mod.load_size;
  memory_boot_teardown_checkpoint("plugin-init-begin");
  int plugin_result=plugin_loader_init(heap_so_base,heap_so_limit,DATA_ROOT);
  memory_boot_teardown_checkpoint("plugin-init-returned");
  memory_test_check("original plugin loader for native crypto",plugin_result==0);
  if(memory_test_failed) { memory_boot_teardown_checkpoint("plugin-init-failed-cleanup-deferred"); return; }
  memory_boot_checkpoint("finalize-begin");
  so_finalize(&game_mod); so_flush_caches(&game_mod);
  patch_unity_java_class_resolution(); patch_genshin_transfer_int32_guard();
  patch_mmoron_managed_directory_path(); patch_unity_slab_activation();
  memory_runtime_trace("MODULE base=0x%llx bytes=%llu",(unsigned long long)game_mod.load_virtbase,(unsigned long long)game_mod.load_size);
  memory_boot_checkpoint("constructors-begin");
  static uint8_t tls[BIONIC_TLS_SIZE] __attribute__((aligned(16)));
  install_bionic_tls(tls);
  so_execute_init_array(&game_mod);
  memory_boot_checkpoint("constructors-returned");
  int bridge=combo_bridge_init(&game_mod);
  if(bridge!=0) { write_thread_pointer(memory_boot_host_tp); memory_test_check("original Unity callback transport",0); return; }
  so_free_temp(&game_mod);
  jni_init();
  if(!jni_reference_self_test()) { write_thread_pointer(memory_boot_host_tp); memory_test_check("original JNI ownership self-test",0); return; }
  unity_environment_init(DATA_ROOT);
  if(!unity_storage_paths_self_test()) { write_thread_pointer(memory_boot_host_tp); memory_test_check("original JNI storage paths",0); return; }
  android_native_input_init();
  memory_boot_checkpoint("native-crypto-begin");
  if(combo_crypto_init()!=0) {
    write_thread_pointer(memory_boot_host_tp); memory_test_report("BOOT crypto_error=%s\n",combo_crypto_error()); memory_test_check("original native crypto initialization",0); return;
  }
  memory_boot_checkpoint("JNI_OnLoad-begin");
  extern void *fake_vm;
  JniOnLoadFn entry=(JniOnLoadFn)so_try_find_addr_rx(&game_mod,"JNI_OnLoad");
  if(!entry) { write_thread_pointer(memory_boot_host_tp); memory_test_check("JNI_OnLoad export exists",0); return; }
  jni_boundary_begin("JNI_OnLoad"); int version=entry(fake_vm,NULL); jni_boundary_end();
  uintptr_t guest_tp=read_thread_pointer();
  write_thread_pointer(memory_boot_host_tp);
  memory_test_report("BOOT JNI_OnLoad_version=%08x\n",version);
  memory_test_check("real JNI_OnLoad returns JNI 1.6",version==JNI_VERSION_1_6);
  memory_boot_checkpoint("JNI_OnLoad-finished");
  if(version==JNI_VERSION_1_6) memory_boot_graphics(guest_tp);
}



