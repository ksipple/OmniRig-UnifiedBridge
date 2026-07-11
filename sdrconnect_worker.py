import time
import json
import websocket
import threading
import config

# Global variables for the shared state
_shared_ws = None
_ws_lock = threading.Lock()

def send_to_sdrconnect_fast(freq, mode):
    """Sends immediate outbound parameters with explicit string coercion to prevent formatting shifts."""
    global _shared_ws
    if not config.CONFIG.get("SDRCONNECT_ENABLED", False):
        return

    config.sdrconnect_blackout_until = time.time() + 2.5

    # Force format as a direct string representation of the integer Hz 
    # to avoid JSON floating point or scientific notation truncation bugs.
    freq_str = str(int(freq))

    payload = {
        "event_type": "set_property",
        "property": "device_vfo_frequency",
        "value": freq_str
    }

    def _async_send():
        global _shared_ws
        with _ws_lock:
            if _shared_ws is None:
                return
            try:
                _shared_ws.send(json.dumps(payload))
            except Exception as e:
                config.ui_print(f"⚠️ Outbound send failed: {e}")

    threading.Thread(target=_async_send, daemon=True).start()


def sdrconnect_heartbeat_loop():
    """Main background supervisor. Handles connections, cleanups, and auto-recovers gracefully."""
    global _shared_ws
    
    if not hasattr(config, 'sdrconnect_blackout_until'):
        config.sdrconnect_blackout_until = 0.0

    while True:
        if config.CONFIG.get("SDRCONNECT_ENABLED", False):
            host = config.CONFIG.get("SDRCONNECT_HOST", "127.0.0.1")
            port = int(config.CONFIG.get("SDRCONNECT_PORT", 5454))
            ws_url = f"ws://{host}:{port}"
            
            try:
                # Attempt to establish/re-establish connection
                with _ws_lock:
                    if _shared_ws is None:
                        _shared_ws = websocket.create_connection(ws_url, timeout=3.0)
                        config.status_states["sdrconnect"] = "online"
                        config.ui_print("🔌 Persistent link established with SDRconnect API.")
                
                # Active streaming listener loop
                while config.CONFIG.get("SDRCONNECT_ENABLED", False):
                    try:
                        # Grab streaming socket packets
                        message = _shared_ws.recv()
                        data = json.loads(message)
                        
                        # 1. Drop outbound confirmation reflections 
                        if data.get("event_type") == "set_property_response":
                            continue

                        # 2. Drop updates if our physical radio dial blackout is active
                        if time.time() < config.sdrconnect_blackout_until:
                            continue

                        # 3. Capture real user mouse clicks on the waterfall
                        if data.get("event_type") == "property_changed" and data.get("property") == "device_vfo_frequency":
                            # Strip any leading zeros or whitespace that SDRconnect might be padding
                            raw_val = data.get("value", "0").strip()
                            new_freq = int(raw_val)
                            
                            target_rig = config.current_sdrconnect_target_rig
                            
                            if abs(new_freq - config.last_freqs[target_rig]) > config.CONFIG["FREQ_TOLERANCE"]:
                                config.ui_print(f"🎯 [SDRconnect Mouse Click] Waterfall Match: {new_freq} Hz")
                                
                                with config.queue_lock:
                                    config.tune_queue.append((target_rig, new_freq, "USB", "sdrconnect"))
                                    
                    except websocket.WebSocketTimeoutException:
                        continue # Timeouts are fine, loop back and listen for more data
                        
            except Exception as e:
                # Connection dropped, reset the tracking state
                config.status_states["sdrconnect"] = "offline"
                config.ui_print(f"📡 SDRconnect disconnected or offline. Retrying in 3s...")
                
                with _ws_lock:
                    if _shared_ws:
                        try:
                            _shared_ws.close()
                        except:
                            pass
                        _shared_ws = None
        else:
            config.status_states["sdrconnect"] = "offline"
            with _ws_lock:
                if _shared_ws:
                    try: _shared_ws.close()
                    except: pass
                    _shared_ws = None
            
        # Quiet cooldown delay before attempting a full reconnection cycle
        time.sleep(3.0)