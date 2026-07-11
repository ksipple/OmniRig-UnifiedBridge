import json
import time
import threading
import websocket
import config

# Track parameters locally to ensure thread safety
_last_sent_freq = 0
_last_sent_time = 0

def on_message(ws, message):
    """Handles incoming WebSocket telemetry strings from SDRconnect."""
    global _last_sent_freq, _last_sent_time
    current_time = time.time()
    
    try:
        data = json.loads(message)
        
        # Look for frequency update messages broadcasted by SDRconnect
        if data.get("event_type") == "property_changed":
            prop_name = data.get("property")
            
            if prop_name == "device_vfo_frequency":
                raw_val = data.get("value", "0")
                try:
                    sdr_freq = int(raw_val)
                except ValueError:
                    return
                
                target_rig = config.current_sdrconnect_target_rig
                
                # 🎯 RETAIN LOCKOUT: If we recently forced an outbound frequency change,
                # ignore incoming packets that match old cached states for a short window.
                if current_time < _last_sent_time + 1.5:
                    if sdr_freq != _last_sent_freq:
                        return
                
                # If the frequency is genuinely different from our application state
                if sdr_freq > 0 and sdr_freq != config.last_freqs.get(target_rig, 0):
                    config.ui_print(f"📥 [SDRconnect Waterfall Click] Extracted VFO -> {sdr_freq} Hz")
                    
                    config.last_freqs[target_rig] = sdr_freq
                    config.rig_blackout_until = current_time + 1.5
                    config.expected_freqs[target_rig] = sdr_freq
                    config.expected_lock_timeout[target_rig] = current_time + 5.0
                    
                    with config.queue_lock:
                        config.tune_queue.clear()
                        config.tune_queue.append((target_rig, sdr_freq, "USB", "sdrconnect"))

    except Exception:
        pass

def on_error(ws, error):
    config.ui_print(f"❌ [SDRconnect WebSocket] Connection error observed: {error}")
    config.status_states["sdrconnect"] = "offline"  # 🎯 FIX: Changed 'sdrconnect_ws' to 'sdrconnect'

def on_close(ws, close_status_code, close_msg):
    config.ui_print("🔌 [SDRconnect WebSocket] Closed client session connection link.")
    config.status_states["sdrconnect"] = "offline"  # 🎯 FIX: Changed 'sdrconnect_ws' to 'sdrconnect'

def on_open(ws):
    config.ui_print("🚀 [SDRconnect WebSocket] Connection established successfully.")
    config.status_states["sdrconnect"] = "online"   # 🎯 FIX: Changed 'sdrconnect_ws' to 'sdrconnect'

def sdrconnect_heartbeat_loop():
    """Main worker thread maintaining client runtime state and processing outbound pushes."""
    global _last_sent_freq, _last_sent_time
    
    # 🎯 FIX: Updated default port to 5454 and removed the trailing "/ws" path extension
    ip = config.CONFIG.get('SDRCONNECT_IP', '127.0.0.1')
    port = config.CONFIG.get('SDRCONNECT_PORT', 5454)
    ws_url = f"ws://{ip}:{port}/"
    
    while True:
        try:
            config.ui_print(f"🔄 Connecting to SDRconnect WebSocket Server at {ws_url}...")
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Spin off the socket listener daemon context
            ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
            ws_thread.start()
            
            # Give the thread a brief window to attempt connection before entering the check loop
            time.sleep(0.5)
            
            # Periodically scan for outbound requests while the link remains active
            while ws_thread.is_alive():
                time.sleep(0.05)
                
                target_rig = config.current_sdrconnect_target_rig
                
                if hasattr(config, 'sdrconnect_update_queue') and config.sdrconnect_update_queue:
                    try:
                        req_freq, req_mode = config.sdrconnect_update_queue.pop(0)
                    except IndexError:
                        continue
                        
                    if config.status_states.get("sdrconnect_ws") == "online":
                        formatted_freq = f"{req_freq:011d}"
                        
                        _last_sent_freq = req_freq
                        _last_sent_time = time.time()
                        
                        # Structure the VFO parameter update frame
                        vfo_payload = {
                            "event_type": "set_property",
                            "property": "device_vfo_frequency",
                            "value": formatted_freq
                        }
                        ws.send(json.dumps(vfo_payload))
                        
                        # Simultaneously shift the visible spectrum center LO frequency
                        center_payload = {
                            "event_type": "set_property",
                            "property": "device_center_frequency",
                            "value": formatted_freq
                        }
                        ws.send(json.dumps(center_payload))
                        
        except Exception as e:
            config.ui_print(f"⚠️ SDRconnect worker loop experienced an error: {e}")
            config.status_states["sdrconnect_ws"] = "offline"
            
        # Throttles connection retry attempts to avoid flooding the application layout
        time.sleep(4.5)
        
def send_to_sdrconnect_fast(freq, mode="USB", *args, **kwargs):
    """
    Exported hook called by omnirig_engine.py when the physical radio dial turns.
    Safely queues a frequency adjustment command for the SDRconnect WebSocket worker.
    """
    if not hasattr(config, 'sdrconnect_update_queue'):
        config.sdrconnect_update_queue = []
        
    # Append the request as a tuple (frequency, mode)
    config.sdrconnect_update_queue.append((freq, mode))