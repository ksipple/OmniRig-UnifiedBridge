import time
import threading
import win32com.client
import pythoncom
import config
import network_workers
import os

def kill_omnirig_process_hard():
    """Locates and terminates OmniRig.exe process directly to clear COM hardware line holds."""
    try:
        import subprocess
        subprocess.run("taskkill /f /im OmniRig.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        config.ui_print("💥 OmniRig process terminated hard. COM ports released.")
    except Exception as e:
        config.ui_print(f"⚠️ Error executing process cleanup: {e}")

def omnirig_worker_thread():
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    omnirig = None
    config.ui_print("OmniRig Sync Engine Active.")

    while True:
        current_time = time.time()
        
        if omnirig is None:
            # Standby state if master execution switch or individual radio bounds are inactive
            if not config.omnirig_global_enabled or (not config.rig_polling_enabled[1] and not config.rig_polling_enabled[2]):
                config.status_states["omnirig"] = "offline"
                config.status_states["rig1_hw"] = "offline"
                config.status_states["rig2_hw"] = "offline"
                time.sleep(1.0)
                continue
                
            try:
                try: omnirig = win32com.client.gencache.EnsureDispatch("OmniRig.OmniRigX")
                except: omnirig = win32com.client.Dispatch("OmniRig.OmniRigX")
                config.status_states["omnirig"] = "online"
            except Exception:
                config.status_states["omnirig"] = "offline"
                time.sleep(2.0)
                continue

        with config.queue_lock:
            if config.tune_queue:
                queue_item = config.tune_queue.pop(0)
                radio_num = queue_item[0]
                target_freq = queue_item[1]
                target_mode = queue_item[2]
                origin = queue_item[3]
                target_vfo = queue_item[4].upper() if len(queue_item) > 4 else "A"
                
                if target_mode == "KILL_OMNIRIG":
                    config.ui_print("🛑 Purging OmniRig engine instance...")
                    omnirig = None
                    time.sleep(0.1)
                    kill_omnirig_process_hard()
                    continue
                    
                if target_mode == "RESTART_OMNIRIG":
                    config.ui_print("♻️ Re-initializing OmniRig engine context...")
                    omnirig = None
                    time.sleep(0.1)
                    kill_omnirig_process_hard()
                    continue
                
                if config.omnirig_global_enabled and config.rig_polling_enabled[radio_num] and omnirig:
                    try:
                        target_freq_int = int(target_freq)
                        rig_obj = omnirig.Rig1 if radio_num == 1 else omnirig.Rig2
                        radio_label = config.CONFIG["RADIO_1_NAME"] if radio_num == 1 else config.CONFIG["RADIO_2_NAME"]
                        force_selection = config.CONFIG.get("FORCE_MODE_SELECTION", "DATA").upper()
                        
                        if force_selection == "NONE" or origin != "fldigi":
                            mode_code = config.TO_BITMASK.get(target_mode.upper(), 33554432)
                        else:
                            mode_code = config.TO_BITMASK.get(force_selection, 33554432)

                        if target_vfo == "B":
                            config.ui_print(f"[{origin.upper()} -> Rig {radio_num} VFO-B] Moving {radio_label}: {target_freq_int} Hz")
                            config.rig_blackout_until = current_time + 3.0
                            time.sleep(0.02)
                            rig_obj.FreqB = target_freq_int
                            config.last_freqs_b[radio_num] = target_freq_int
                        else:
                            config.ui_print(f"[{origin.upper()} -> Rig {radio_num}] Moving {radio_label}: {target_freq_int} Hz")
                            config.rig_blackout_until = current_time + 3.0
                            time.sleep(0.02)
                            if radio_num == 1:
                                rig_obj.FreqA = target_freq_int; time.sleep(0.15); rig_obj.Mode = mode_code; time.sleep(0.05); rig_obj.Freq = target_freq_int
                            elif radio_num == 2:
                                rig_obj.FreqA = target_freq_int; time.sleep(0.25); rig_obj.Mode = mode_code; time.sleep(0.05); rig_obj.Freq = target_freq_int 
                            config.last_freqs[radio_num] = target_freq_int
                            config.last_modes[radio_num] = mode_code
                    except Exception as e:
                        config.ui_print(f"❌ Tuning failed: {e}")
                        config.status_states["omnirig"] = "offline"
                        omnirig = None

        # Process Physical VFO Polling loops if master context bounds permit
        if current_time > config.rig_blackout_until and omnirig and config.omnirig_global_enabled:
            # Polling Routine: Rig 1
            if config.rig_polling_enabled[1]:
                try:
                    r1_freq = omnirig.Rig1.Freq
                    r1_mode = omnirig.Rig1.Mode
                    r1_freq_b = omnirig.Rig1.FreqB
                    config.status_states["omnirig"] = "online"
                    
                    if r1_freq > 0 and (abs(r1_freq - config.last_freqs[1]) > config.CONFIG["FREQ_TOLERANCE"] or r1_mode != config.last_modes[1]):
                        friendly_mode = config.OMNIRIG_MODES.get(r1_mode, "USB")
                        config.ui_print(f"[{config.CONFIG['RADIO_1_NAME']} Dial Move] {r1_freq} Hz")
                        threading.Thread(target=network_workers.post_to_wavelog_api, args=(config.CONFIG["RADIO_1_NAME"], r1_freq, friendly_mode), daemon=True).start()
                        if config.current_fldigi_target_rig == 1:
                            config.fldigi_blackout_until = current_time + 1.5
                            threading.Thread(target=network_workers.sync_to_fldigi, args=(r1_freq, friendly_mode), daemon=True).start()
                        config.last_freqs[1] = r1_freq; config.last_modes[1] = r1_mode
                        
                    if r1_freq_b > 0 and abs(r1_freq_b - config.last_freqs_b[1]) > config.CONFIG["FREQ_TOLERANCE"]:
                        config.ui_print(f"[{config.CONFIG['RADIO_1_NAME']} VFO-B Change] {r1_freq_b} Hz")
                        config.last_freqs_b[1] = r1_freq_b
                except: 
                    config.status_states["omnirig"] = "offline"
                    omnirig = None

            # Polling Routine: Rig 2
            if config.rig_polling_enabled[2] and omnirig:
                try:
                    r2_freq = omnirig.Rig2.Freq
                    r2_mode = omnirig.Rig2.Mode
                    r2_freq_b = omnirig.Rig2.FreqB
                    config.status_states["omnirig"] = "online"
                    
                    if r2_freq > 0 and (abs(r2_freq - config.last_freqs[2]) > config.CONFIG["FREQ_TOLERANCE"] or r2_mode != config.last_modes[2]):
                        friendly_mode = config.OMNIRIG_MODES.get(r2_mode, "USB")
                        config.ui_print(f"[{config.CONFIG['RADIO_2_NAME']} Dial Move] {r2_freq} Hz")
                        threading.Thread(target=network_workers.post_to_wavelog_api, args=(config.CONFIG["RADIO_2_NAME"], r2_freq, friendly_mode), daemon=True).start()
                        if config.current_fldigi_target_rig == 2:
                            config.fldigi_blackout_until = current_time + 1.5
                            threading.Thread(target=network_workers.sync_to_fldigi, args=(r2_freq, friendly_mode), daemon=True).start()
                        config.last_freqs[2] = r2_freq; config.last_modes[2] = r2_mode
                        
                    if r2_freq_b > 0 and abs(r2_freq_b - config.last_freqs_b[2]) > config.CONFIG["FREQ_TOLERANCE"]:
                        config.ui_print(f"[{config.CONFIG['RADIO_2_NAME']} VFO-B Change] {r2_freq_b} Hz")
                        config.last_freqs_b[2] = r2_freq_b
                except: 
                    config.status_states["omnirig"] = "offline"
                    omnirig = None
                
        time.sleep(config.CONFIG["POLL_INTERVAL"])