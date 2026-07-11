import time
import threading
import win32com.client
import win32con
import config
import network_workers
import sdrconnect_worker

def omnirig_worker_thread():
    """Main background engine monitoring physical transceivers via OmniRig with Smart Polling Lock."""
    omnirig = None
    config.ui_print("🚀 Initializing OmniRig COM client engine...")
    
    # Initialize smart lock tracking variables in config if missing
    if not hasattr(config, 'expected_freqs'):
        config.expected_freqs = {1: 0, 2: 0}
    if not hasattr(config, 'expected_lock_timeout'):
        config.expected_lock_timeout = {1: 0.0, 2: 0.0}
    
    while True:
        current_time = time.time()
        
        if omnirig is None:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                omnirig = win32com.client.Dispatch("OmniRig.OmniRigX")
                config.ui_print("✅ Connected to OmniRig Engine Successfully.")
            except Exception as e:
                config.ui_print(f"❌ Failed to bind OmniRig COM Object: {e}. Retrying...")
                config.status_states["rig1_hw"] = "offline"
                config.status_states["rig2_hw"] = "offline"
                time.sleep(5.0)
                continue

        # --- OUTBOUND: Handle incoming Tune Requests from Fldigi/SDRconnect/Wavelog ---
        with config.queue_lock:
            if config.tune_queue:
                latest_request = None
                remaining_queue = []
                
                # Dynamic index checking to prevent structural length unpacking crashes (e.g. Wavelog 5-item tuples)
                queue_item = config.tune_queue[0]
                prime_rig = queue_item[0] if len(queue_item) > 0 else 1
                prime_freq = queue_item[1] if len(queue_item) > 1 else 0
                prime_mode = queue_item[2] if len(queue_item) > 2 else "USB"
                prime_source = queue_item[3] if len(queue_item) > 3 else "unknown"
                
                if not prime_rig or prime_rig == 0:
                    prime_rig = 1
                
                # 🚀 SQUASH THE QUEUE: Discard lagging intermediate scroll steps from the same source
                if prime_source in ['sdrconnect', 'fldigi', 'wavelog']:
                    for req in reversed(config.tune_queue):
                        current_req_source = req[3] if len(req) > 3 else "unknown"
                        current_req_rig = req[0] if (len(req) > 0 and req[0] and req[0] != 0) else 1
                        if current_req_source == prime_source and current_req_rig == prime_rig:
                            latest_request = req
                            break
                    
                    if latest_request:
                        for req in config.tune_queue:
                            current_req_source = req[3] if len(req) > 3 else "unknown"
                            current_req_rig = req[0] if (len(req) > 0 and req[0] and req[0] != 0) else 1
                            if current_req_source == prime_source and current_req_rig == prime_rig:
                                if req != latest_request:
                                    continue # Drop historical redundant queue entries
                            remaining_queue.append(req)
                        config.tune_queue = remaining_queue
                
                # Safe array pull assignment
                raw_pop_item = config.tune_queue.pop(0)
                target_rig = raw_pop_item[0] if len(raw_pop_item) > 0 else 1
                target_freq = raw_pop_item[1] if len(raw_pop_item) > 1 else 0
                target_mode = raw_pop_item[2] if len(raw_pop_item) > 2 else "USB"
                source = raw_pop_item[3] if len(raw_pop_item) > 3 else "unknown"
                
                if not target_rig or target_rig == 0:
                    target_rig = 1
                
                try:
                    rig_obj = omnirig.Rig1 if target_rig == 1 else omnirig.Rig2
                    print(f"📥 [QUEUE PROCESSING] Forcing raw COM write: Rig {target_rig} -> {target_freq} Hz ({target_mode}) via {source}")
                    
                    # 🛑 HARD LOCK WINDOW: Keep inbound loops entirely quiet while the slow serial interface settles
                    config.rig_blackout_until = current_time + 1.20  
                    config.expected_freqs[target_rig] = target_freq
                    config.expected_lock_timeout[target_rig] = current_time + 5.0
                    
                    # Map text mode to OmniRig binary map index 
                    mode_enum = next((k for k, v in config.OMNIRIG_MODES.items() if v == target_mode), 1)
                    
                    import pythoncom
                    
                    # Resolve Mode ID safely
                    mode_id = rig_obj._oleobj_.GetIDsOfNames("Mode")
                    if not isinstance(mode_id, int):
                        mode_id = mode_id[0]
                        
                    # 🎯 TARGET FREQA INSTEAD OF GENERIC FREQ:
                    # Explicitly writing to FreqA tells OmniRig to hammer VFO-A directly,
                    # bypassing any internal OmniRig state machine ambiguity.
                    freq_id = rig_obj._oleobj_.GetIDsOfNames("FreqA")
                    if not isinstance(freq_id, int):
                        freq_id = freq_id[0]
                    
                    # Execute direct property puts down the Windows API pipeline using pythoncom
                    # 1. Write Mode
                    rig_obj._oleobj_.Invoke(
                        mode_id, 0, pythoncom.DISPATCH_PROPERTYPUT, True, int(mode_enum)
                    )
                    time.sleep(0.04)
                    
                    # 2. Write Frequency to FreqA
                    rig_obj._oleobj_.Invoke(
                        freq_id, 0, pythoncom.DISPATCH_PROPERTYPUT, True, int(target_freq)
                    )
                    
                    # Synchronize track memories locally so loops match immediately
                    config.last_freqs[target_rig] = target_freq
                    config.last_modes[target_rig] = mode_enum
                    
                except Exception as e:
                    print(f"⚠️ Raw OLE Invoke Write Error: {e}")

        # --- INBOUND: Track Physical Hardware VFO Dial Adjustments ---
        if current_time > config.rig_blackout_until and omnirig:
            
            # --- Rig 1 Hardware Monitoring ---
            if config.rig_polling_enabled[1]:
                try:
                    r1_status = int(omnirig.Rig1.Status)
                    r1_status_str = getattr(omnirig.Rig1, "StatusStr", "").lower()
                    
                    if r1_status < 3 or "not" in r1_status_str or "err" in r1_status_str:
                        if config.status_states["rig1_hw"] != "not_responding":
                            config.status_states["rig1_hw"] = "not_responding"
                    else:
                        r1_freq = omnirig.Rig1.Freq
                        r1_mode = omnirig.Rig1.Mode
                        r1_freq_b = omnirig.Rig1.FreqB
                        
                        config.status_states["rig1_hw"] = "online" if r1_freq > 0 else "offline"
                        friendly_mode = config.OMNIRIG_MODES.get(r1_mode, "USB")
                        
                        if config.status_states["rig1_hw"] == "online":
                            skip_rig1_processing = False
                            
                            # 🎯 DYNAMIC TOLERANCE PATCH:
                            # Expanded deadzone window to prevent old VFO polling values from fighting waterfall updates
                            if config.expected_freqs[1] > 0:
                                if abs(r1_freq - config.expected_freqs[1]) <= 2000:
                                    config.expected_freqs[1] = 0 
                                    config.last_freqs[1] = r1_freq  
                                elif current_time > config.expected_lock_timeout[1]:
                                    config.expected_freqs[1] = 0
                                else:
                                    skip_rig1_processing = True

                            if not skip_rig1_processing:
                                is_changed = (abs(r1_freq - config.last_freqs[1]) > config.CONFIG["FREQ_TOLERANCE"] or r1_mode != config.last_modes[1])
                                is_timeout = (current_time - config.last_wavelog_push_time[1] > config.CONFIG["WAVELOG_MAX_INTERVAL"])
                                
                                if is_changed or is_timeout:
                                    if not (is_timeout and not is_changed):
                                        print(f"📡 [Elecraft K3 Dial Action] VFO: {r1_freq} Hz | Mode: {friendly_mode}")
                                        
                                    threading.Thread(target=network_workers.post_to_wavelog_api, args=(config.CONFIG["RADIO_1_NAME"], r1_freq, friendly_mode), daemon=True).start()
                                    
                                    if config.current_fldigi_target_rig == 1 and is_changed:
                                        config.fldigi_blackout_until = current_time + 1.5
                                        threading.Thread(target=network_workers.sync_to_fldigi, args=(r1_freq, friendly_mode), daemon=True).start()
                                        
                                    if config.current_sdrconnect_target_rig == 1 and is_changed:
                                        if config.CONFIG.get("SDRCONNECT_ENABLED", False):
                                            sdrconnect_worker.send_to_sdrconnect_fast(r1_freq, friendly_mode)
                                        
                                    config.last_freqs[1] = r1_freq
                                    config.last_modes[1] = r1_mode
                                    config.last_wavelog_push_time[1] = current_time
                                    
                                if r1_freq_b > 0 and abs(r1_freq_b - config.last_freqs_b[1]) > config.CONFIG["FREQ_TOLERANCE"]:
                                    config.last_freqs_b[1] = r1_freq_b
                except Exception: 
                    config.status_states["rig1_hw"] = "not_responding"

            # --- Rig 2 Hardware Monitoring ---
            if config.rig_polling_enabled[2] and omnirig:
                try:
                    r2_status = int(omnirig.Rig2.Status)
                    r2_status_str = getattr(omnirig.Rig2, "StatusStr", "").lower()
                    
                    if r2_status < 3 or "not" in r2_status_str or "err" in r2_status_str:
                        if config.status_states["rig2_hw"] != "not_responding":
                            config.status_states["rig2_hw"] = "not_responding"
                    else:
                        r2_freq = omnirig.Rig2.Freq
                        r2_mode = omnirig.Rig2.Mode
                        r2_freq_b = omnirig.Rig2.FreqB
                        
                        config.status_states["rig2_hw"] = "online" if r2_freq > 0 else "offline"
                        friendly_mode = config.OMNIRIG_MODES.get(r2_mode, "USB")

                        if config.status_states["rig2_hw"] == "online":
                            skip_rig2_processing = False
                            if config.expected_freqs[2] > 0:
                                if abs(r2_freq - config.expected_freqs[2]) <= 2000:
                                    config.expected_freqs[2] = 0
                                    config.last_freqs[2] = r2_freq
                                elif current_time > config.expected_lock_timeout[2]:
                                    config.expected_freqs[2] = 0
                                else:
                                    skip_rig2_processing = True

                            if not skip_rig2_processing:
                                is_changed = (abs(r2_freq - config.last_freqs[2]) > config.CONFIG["FREQ_TOLERANCE"] or r2_mode != config.last_modes[2])
                                is_timeout = (current_time - config.last_wavelog_push_time[2] > config.CONFIG["WAVELOG_MAX_INTERVAL"])
                                
                                if is_changed or is_timeout:
                                    if not (is_timeout and not is_changed):
                                        print(f"📡 [{config.CONFIG['RADIO_2_NAME']} Dial Action] VFO: {r2_freq} Hz | Mode: {friendly_mode}")
                                        
                                    threading.Thread(target=network_workers.post_to_wavelog_api, args=(config.CONFIG["RADIO_2_NAME"], r2_freq, friendly_mode), daemon=True).start()
                                    
                                    if config.current_fldigi_target_rig == 2 and is_changed:
                                        config.fldigi_blackout_until = current_time + 1.5
                                        threading.Thread(target=network_workers.sync_to_fldigi, args=(r2_freq, friendly_mode), daemon=True).start()
                                        
                                    if config.current_sdrconnect_target_rig == 2 and is_changed:
                                        if config.CONFIG.get("SDRCONNECT_ENABLED", False):
                                            sdrconnect_worker.send_to_sdrconnect_fast(r2_freq, friendly_mode)
                                            
                                    config.last_freqs[2] = r2_freq
                                    config.last_modes[2] = r2_mode
                                    config.last_wavelog_push_time[2] = current_time
                                    
                                if r2_freq_b > 0 and abs(r2_freq_b - config.last_freqs_b[2]) > config.CONFIG["FREQ_TOLERANCE"]:
                                    config.last_freqs_b[2] = r2_freq_b
                except Exception: 
                    config.status_states["rig2_hw"] = "not_responding"

        # Safe pacing interval to protect CPU core utilization and prevent serial queue blocking
        time.sleep(0.015)