import json
import time
import websocket
import threading
import config

# Connection state tracking variables
_ws_client = None
_ws_lock = threading.Lock()
_connected = False

def get_sdrconnect_ws():
    """Retrieves or creates a persistent background WebSocket client connection."""
    global _ws_client, _connected
    
    if not config.CONFIG.get("SDRCONNECT_ENABLED", False):
        config.status_states["sdrconnect"] = "offline"
        return None
        
    with _ws_lock:
        if _connected and _ws_client and _ws_client.connected:
            config.status_states["sdrconnect"] = "online"
            return _ws_client
            
        _connected = False
        if _ws_client:
            try:
                _ws_client.close()
            except Exception:
                pass
            _ws_client = None
            
        host = config.CONFIG.get("SDRCONNECT_HOST", "127.0.0.1")
        port = config.CONFIG.get("SDRCONNECT_PORT", 5454)
        ws_url = f"ws://{host}:{port}/api/ws"
        
        try:
            _ws_client = websocket.create_connection(ws_url, timeout=0.5)
            _connected = True
            config.status_states["sdrconnect"] = "online"
            config.ui_print("✅ Connected to SDRconnect API WebSocket Engine.")
            return _ws_client
        except Exception as e:
            config.status_states["sdrconnect"] = "offline"
            return None

def send_to_sdrconnect_fast(frequency_hz, mode_str, force_center=False):
    """Dispatches targeted frequency adjustments directly to SDRconnect via WebSocket."""
    ws = get_sdrconnect_ws()
    if not ws:
        return

    try:
        if force_center:
            center_payload = {
                "event_type": "set_property",
                "property": "device_center_frequency",
                "value": str(int(frequency_hz))
            }
            ws.send(json.dumps(center_payload))
            time.sleep(0.04)
            
        vfo_payload = {
            "event_type": "set_property",
            "property": "device_vfo_frequency",
            "value": str(int(frequency_hz))
        }
        ws.send(json.dumps(vfo_payload))
        
        sdr_mode = mode_str.upper()
        if sdr_mode == "CW": sdr_mode = "CW_U"
        
        mode_payload = {
            "event_type": "set_property",
            "property": "device_vfo_mode",
            "value": sdr_mode
        }
        ws.send(json.dumps(mode_payload))
        config.status_states["sdrconnect"] = "online"

    except Exception as e:
        global _connected
        print(f"⚠️ SDRconnect WS transmission error: {e}")
        with _ws_lock:
            _connected = False
            config.status_states["sdrconnect"] = "offline"

def sync_to_sdrconnect(frequency_hz, mode_str):
    """Alias mapping wrapper for UI compatibility."""
    send_to_sdrconnect_fast(frequency_hz, mode_str, force_center=False)

def sdrconnect_heartbeat_loop():
    """Background thread loop handling both keepalive pings and inbound event streaming."""
    last_ping_time = 0
    last_processed_freq = 0  # Deduplicate rapid identical packets
    
    while True:
        ws = get_sdrconnect_ws()
        if not ws:
            time.sleep(2.0)
            continue
            
        try:
            current_time = time.time()
            
            # 1. Send keepalive ping every 5 seconds
            if current_time - last_ping_time >= 5.0:
                ws.send(json.dumps({"event_type": "ping"}))
                last_ping_time = current_time
            
            # 2. Block briefly to look for incoming VFO changes from SDRconnect software
            ws.settimeout(0.1)
            try:
                message = ws.recv()
                if message:
                    data = json.loads(message)
                    event = data.get("event_type")
                    prop = data.get("property")
                    
                    # Intercept waterfall clicks or software tuning events
                    if event in ["property_changed", "get_property_response"] and prop == "device_vfo_frequency":
                        sdr_freq = int(data.get("value", 0))
                        
                        if sdr_freq > 0 and sdr_freq != last_processed_freq:
                            target_rig = config.current_sdrconnect_target_rig
                            
                            # Check tolerance against last known hardware frequency
                            if abs(sdr_freq - config.last_freqs[target_rig]) > config.CONFIG["FREQ_TOLERANCE"]:
                                
                                # OPTIMIZED: Use a highly responsive 300ms window instead of a multi-second lockout
                                if not hasattr(config, 'last_sdr_write_time') or (current_time - config.last_sdr_write_time > 0.3):
                                    print(f"📥 [SDRconnect Waterfall Click] Extracted VFO -> {sdr_freq} Hz")
                                    
                                    # Update sync trackers instantly before the queue processing loop executes
                                    config.last_sdr_write_time = current_time
                                    config.last_freqs[target_rig] = sdr_freq
                                    last_processed_freq = sdr_freq
                                    
                                    # Tell the OmniRig engine to immediately update the rig
                                    with config.queue_lock:
                                        # Clear pending outdated items to keep response snappier
                                        config.tune_queue.clear() 
                                        config.tune_queue.append((target_rig, sdr_freq, "USB", "sdrconnect"))
                                        
            except websocket.WebSocketTimeoutException:
                pass  # Timeout releases the socket lock briefly, which is expected behavior
                
        except Exception as e:
            print(f"⚠️ SDRconnect event processing error: {e}")
            global _connected
            with _ws_lock:
                _connected = False
            config.status_states["sdrconnect"] = "offline"
            time.sleep(1.0)