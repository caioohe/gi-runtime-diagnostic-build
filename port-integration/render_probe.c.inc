  /* Continue after presentation: at most 60 seconds/3600 additional calls.
   * Clock checks are between calls and cannot interrupt a blocked render. */
  extern unsigned nx_memory_present_returns(void);
  const char *probe_stop="iteration-limit";
  write_thread_pointer(memory_boot_host_tp);
  uint64_t probe_start=armGetSystemTick();
  write_thread_pointer(guest_tp);
  unsigned probe_calls=0;
  for(unsigned extra=1;extra<=3600;extra++) {
    if(!rendered) { probe_stop="render-returned-false"; break; }
    if(jni_quit_requested) { probe_stop="guest-quit-request"; break; }
    write_thread_pointer(memory_boot_host_tp);
    uint64_t now=armGetSystemTick();
    int app_running=appletMainLoop();
    int in_focus=appletGetFocusState()==AppletFocusState_InFocus;
    write_thread_pointer(guest_tp);
    if(!app_running || !in_focus) { probe_stop=app_running?"focus-lost":"applet-stop"; break; }
    if(now-probe_start>=UINT64_C(60)*19200000u) { probe_stop="time-limit"; break; }
    (void)android_native_looper_pump_callbacks(8);
    if(jni_quit_requested) { probe_stop="guest-quit-request"; break; }
    /* Callbacks may consume the remaining budget or request applet changes. */
    write_thread_pointer(memory_boot_host_tp);
    app_running=appletMainLoop();
    in_focus=appletGetFocusState()==AppletFocusState_InFocus;
    now=armGetSystemTick();
    write_thread_pointer(guest_tp);
    if(!app_running || !in_focus) { probe_stop=app_running?"focus-lost":"applet-stop"; break; }
    if(now-probe_start>=UINT64_C(60)*19200000u) { probe_stop="time-limit"; break; }
    int sampled=extra<=8 || !(extra&63);
    nx_guest_termination_set_stage("extra-nativeRender-begin");
    if(sampled) memory_boot_teardown_checkpoint("extra-nativeRender-begin");
    if(sampled) memory_runtime_trace("RENDER probe begin extra=%u max_extra=3600",extra);
    jni_boundary_begin("nativeRender");
    /* Logging/JNI setup can also take time; recheck at the actual call boundary. */
    write_thread_pointer(memory_boot_host_tp);
    now=armGetSystemTick();
    write_thread_pointer(guest_tp);
    if(now-probe_start>=UINT64_C(60)*19200000u) {
      jni_boundary_end();
      nx_guest_termination_set_stage("extra-nativeRender-skipped-deadline");
      probe_stop="time-limit";
      break;
    }
    rendered=render(fake_env,fake_unityplayer_thiz);
    jni_boundary_end();
    ++probe_calls;
    nx_guest_termination_set_stage("extra-nativeRender-returned");
    if(sampled || !rendered) memory_boot_teardown_checkpoint("extra-nativeRender-returned");
    if(sampled || !rendered) memory_runtime_trace("RENDER probe returned extra=%u result=%d",extra,rendered);
  }
  if(!rendered) probe_stop="render-returned-false";
  else if(jni_quit_requested) probe_stop="guest-quit-request";
  memory_boot_teardown_checkpoint("render-probe-finished");
  memory_runtime_trace("RENDER probe stop reason=%s calls=%u present_returns=%u",probe_stop,probe_calls,nx_memory_present_returns());

  write_thread_pointer(memory_boot_host_tp);
  uint64_t probe_elapsed=armGetSystemTick()-probe_start;
  memory_test_report("BOOT render_probe_stop=%s calls=%u present_returns=%u elapsed_ticks=%llu (between-call limit)\n",probe_stop,probe_calls,nx_memory_present_returns(),(unsigned long long)probe_elapsed);
  write_thread_pointer(guest_tp);


