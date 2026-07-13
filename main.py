import threading
import time  # 📌 FIXED: Added missing import statement
import config
import network_workers
import omnirig_engine
import gui_app
import sdrconnect_worker 

def trigger_startup_sync():
    """Reads the current radio state on startup and forces an initial broadcast."""
    # Give the threads and COM port 1-2 seconds to fully open and stabilize
    time.sleep(2.0)
    
    target_rig = config.current_sdrconnect_target_rig  # Usually Rig 1
    
    try:
        # 🎯 FIX: Instead of calling a non-existent function, pull the baseline
        # straight from the memory cache that OmniRig populates during startup.
        current_freq = config.last_freqs.get(target_rig, 0)
        
        # Fallback modes depending on your configuration architecture
        current_mode = "USB" 
        
        if current_freq and current_freq > 0:
            config.ui_print(f"📡 [Startup Sync] Initializing Wavelog with current radio state: {current_freq} Hz")
            
            # Force a direct broadcast to your Wavelog/network handler right now
            if hasattr(network_workers, 'sync_to_wavelog'):
                threading.Thread(
                    target=network_workers.sync_to_wavelog, 
                    args=(current_freq, current_mode), 
                    daemon=True
                ).start()
        else:
            config.ui_print("ℹ️ [Startup Sync] Waiting for OmniRig baseline cache to populate...")
            
    except Exception as e:
        print(f"⚠️ Startup sync helper encountered an error: {e}")

def start_background_subsystems():
    """Spins off processing thread workers once initialization ticks complete."""
    
    if hasattr(omnirig_engine, 'omnirig_processing_loop'):
        threading.Thread(target=omnirig_engine.omnirig_processing_loop, daemon=True, name="OmniRigLoop").start()
    else:
        threading.Thread(target=omnirig_engine.omnirig_worker_thread, daemon=True, name="OmniRigLoop").start()
        
    threading.Thread(target=network_workers.fldigi_polling_listener, daemon=True, name="FldigiListener").start()
    threading.Thread(target=network_workers.parameterized_tcp_listener, args=(1,), daemon=True, name="TCP_Rig1").start()
    threading.Thread(target=network_workers.parameterized_tcp_listener, args=(2,), daemon=True, name="TCP_Rig2").start()
    threading.Thread(target=sdrconnect_worker.sdrconnect_heartbeat_loop, daemon=True, name="SDRconnectWS").start()
    threading.Thread(target=network_workers.wsjtx_udp_tracking_listener, daemon=True, name="WSJTXListener").start()
    threading.Thread(target=trigger_startup_sync, daemon=True, name="StartupSync").start()

if __name__ == '__main__':
    # Initialize UI Window instance
    app = gui_app.BridgeGUIApp()
    
    # Store explicit connection hook for text viewport operations
    config._app_instance = app
    
    # Schedule workers to initiate asynchronously after first frame paint finishes
    app.after(1000, start_background_subsystems)
    
    # Execute primary UI run thread loop
    app.mainloop()