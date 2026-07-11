import json
import time
import websocket # standard python websocket-client library
import config

def sync_to_sdrconnect(frequency, mode):
    """
    Transmits property frames over the JSON WebSocket API to synchronize 
    SDRconnect directly with the active transceiver hardware.
    """
    if not config.CONFIG.get("SDRCONNECT_ENABLED", False):
        return

    host = config.CONFIG.get("SDRCONNECT_HOST", "127.0.0.1")
    port = int(config.CONFIG.get("SDRCONNECT_PORT", 5454))
    ws_url = f"ws://{host}:{port}"
    
    try:
        # SDRconnect expects an 11-digit string padded with leading zeros for frequency
        freq_str = f"{int(frequency):011d}"
        
        # Build the protocol compliant JSON frames
        freq_payload = {
            "event_type": "set_property",
            "property": "device_vfo_frequency",
            "value": freq_str
        }
        
        # Open an on-the-fly ephemeral socket connection
        ws = websocket.create_connection(ws_url, timeout=1.0)
        
        # Send VFO Frequency change command
        ws.send(json.dumps(freq_payload))
        
        # Optional: Apply mode configuration profile if required
        # Map digital modes down to sideband specifications
        sdr_mode = "USB" if "DATA" in mode or "FT" in mode or "SSB" in mode else mode
        mode_payload = {
            "event_type": "apply_device_profile",
            "property": "",
            "value": sdr_mode
        }
        time.sleep(0.02)
        ws.send(json.dumps(mode_payload))
        
        ws.close()
        config.status_states["sdrconnect"] = "online"
        
    except Exception:
        # Gracefully flag offline indicator without logging spam
        config.status_states["sdrconnect"] = "offline"
        
def sdrconnect_heartbeat_loop():
    """Periodically verifies connectivity to the SDRconnect WebSocket server."""
    while True:
        if config.CONFIG.get("SDRCONNECT_ENABLED", False):
            host = config.CONFIG.get("SDRCONNECT_HOST", "127.0.0.1")
            port = int(config.CONFIG.get("SDRCONNECT_PORT", 5454))
            ws_url = f"ws://{host}:{port}"
            try:
                # Attempt an ephemeral quick connection check
                ws = websocket.create_connection(ws_url, timeout=1.0)
                ws.close()
                config.status_states["sdrconnect"] = "online"
            except Exception:
                config.status_states["sdrconnect"] = "offline"
        else:
            config.status_states["sdrconnect"] = "offline"
            
        time.sleep(2.0) # Check every 2 seconds