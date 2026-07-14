import time
import socket
import re
import json
import xmlrpc.client
import requests
import threading
import struct
import hashlib
import base64
import config

class TimeoutTransport(xmlrpc.client.Transport):
    """Overrides network layer to prevent indefinite blocks during thread processing."""
    def __init__(self, timeout=1.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = timeout
    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn

# ==========================================
# WEBSOCKET SERVER FOR WAVELOG BRIDGE
# ==========================================
CONNECTED_WS_CLIENTS = set()
WS_CLIENTS_LOCK = threading.Lock()

def start_native_websocket_server():
    """Runs a lightweight native WebSocket server to broadcast WSJT-X targets to the browser."""
    def server_loop():
        ws_port = 2334 
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("127.0.0.1", ws_port))
                server.listen()
                config.ui_print(f"🌐 [WebSocket Server] Listening on ws://127.0.0.1:{ws_port}...")
            except Exception as e:
                config.ui_print(f"❌ WebSocket server failed to start: {e}")
                return

            while True:
                try:
                    conn, addr = server.accept()
                    threading.Thread(target=handle_ws_client, args=(conn,), daemon=True).start()
                except:
                    time.sleep(1)

    threading.Thread(target=server_loop, daemon=True).start()

def handle_ws_client(conn):
    """Performs the WebSocket handshake and keeps the browser socket connection alive."""
    try:
        conn.settimeout(5.0)
        request = conn.recv(4096).decode('utf-8', errors='ignore')
        
        match = re.search(r"Sec-WebSocket-Key:\s*(.+)\r\n", request)
        if not match:
            conn.close()
            return
            
        key = match.group(1).strip()
        magic_guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept_sha1 = hashlib.sha1((key + magic_guid).encode('utf-8')).digest()
        accept_key = base64.b64encode(accept_sha1).decode('utf-8')
        
        handshake = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
        )
        conn.sendall(handshake.encode('utf-8'))
        conn.settimeout(None) 
        
        with WS_CLIENTS_LOCK:
            CONNECTED_WS_CLIENTS.add(conn)
            config.ui_print(f"🔌 [WebSocket] Browser client connected! Total connected: {len(CONNECTED_WS_CLIENTS)}")
        
        while True:
            data = conn.recv(1024)
            if not data: break
    except:
        pass
    finally:
        with WS_CLIENTS_LOCK:
            CONNECTED_WS_CLIENTS.discard(conn)
            config.ui_print(f"🔌 [WebSocket] Browser client disconnected. Total remaining: {len(CONNECTED_WS_CLIENTS)}")
        try: conn.close()
        except: pass

def broadcast_ws_message(payload_str):
    """Wraps text strings inside unmasked WebSocket Text Frames and transmits."""
    payload_bytes = payload_str.encode('utf-8')
    payload_len = len(payload_bytes)
    
    if payload_len <= 125:
        header = struct.pack("!BB", 0x81, payload_len)
    elif payload_len <= 65535:
        header = struct.pack("!BBH", 0x81, 126, payload_len)
    else:
        header = struct.pack("!BBQ", 0x81, 127, payload_len)
        
    frame = header + payload_bytes
    
    with WS_CLIENTS_LOCK:
        active_count = len(CONNECTED_WS_CLIENTS)
        if active_count > 0:
            config.ui_print(f"📤 [WebSocket Broadcast] Broadcasting payload to {active_count} active browser client(s): {payload_str}")
        else:
            config.ui_print("📤 [WebSocket Broadcast] Payload prepared, but 0 active browser clients are currently listening.")
            
        dead_clients = set()
        for client in CONNECTED_WS_CLIENTS:
            try:
                client.sendall(frame)
            except:
                dead_clients.add(client)
        for dead in dead_clients:
            CONNECTED_WS_CLIENTS.discard(dead)

# ==========================================
# STANDARD WAVELOG & FLDIGI WORKERS
# ==========================================
def post_to_wavelog_api(radio_label, freq, mode):
    """Pushes automated tracking configuration events directly up onto cloud stations."""
    payload = {"key": config.CONFIG["WAVELOG_API_KEY"], "radio": radio_label, "frequency": freq, "mode": mode}
    try: 
        resp = requests.post(f"{config.CONFIG['WAVELOG_URL']}/api/radio", json=payload, timeout=2)
        config.status_states["wavelog"] = "online" if resp.status_code == 200 else "offline"
    except:
        config.status_states["wavelog"] = "offline"

def sync_to_fldigi(freq, mode):
    """Updates upstream Fldigi layout values securely matching VFO parameters."""
    try:
        fldigi = xmlrpc.client.ServerProxy(config.CONFIG["FLDIGI_URL"], transport=TimeoutTransport(timeout=1.5))
        if abs(fldigi.main.get_frequency() - freq) > config.CONFIG["FREQ_TOLERANCE"]:
            config.last_pushed_to_fldigi = int(freq)
            fldigi.main.set_frequency(float(freq))
        config.status_states["fldigi"] = "online"
    except:
        config.status_states["fldigi"] = "offline"

def fldigi_polling_listener():
    """Continuously observes Fldigi for interaction updates and waterfall clicks."""
    last_fldigi_freq = 0
    while True:
        current_time = time.time()
        try:
            fldigi = xmlrpc.client.ServerProxy(config.CONFIG["FLDIGI_URL"], transport=TimeoutTransport(timeout=1.0))
            fldigi_freq = fldigi.main.get_frequency()
            fldigi_freq_int = int(fldigi_freq)
            config.status_states["fldigi"] = "online"
            
            if abs(fldigi_freq - last_fldigi_freq) > config.CONFIG["FREQ_TOLERANCE"]:
                if abs(fldigi_freq_int - config.last_pushed_to_fldigi) <= config.CONFIG["FREQ_TOLERANCE"]:
                    last_fldigi_freq = fldigi_freq
                    time.sleep(0.5)
                    continue
                if current_time > config.fldigi_blackout_until and last_fldigi_freq != 0:
                    try: fldigi_mode = fldigi.main.get_modem_name()
                    except: fldigi_mode = "USB"
                    config.ui_print(f"[Fldigi Click] Intercepted Frequency -> {fldigi_freq_int} Hz")
                    with config.queue_lock:
                        config.tune_queue.append((config.current_fldigi_target_rig, fldigi_freq_int, fldigi_mode, "fldigi"))
                last_fldigi_freq = fldigi_freq
        except:
            config.status_states["fldigi"] = "offline"
        time.sleep(0.5)

def parameterized_tcp_listener(assigned_radio_index):
    """Listens on the dynamically tracked configuration port matching the radio slot index."""
    while True:
        port = config.CONFIG["PORT_RADIO_1"] if assigned_radio_index == 1 else config.CONFIG["PORT_RADIO_2"]
        config.active_ports[assigned_radio_index] = port
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server_socket.bind((config.CONFIG["HOST"], port))
                server_socket.listen()
                server_socket.settimeout(1.0)
                config.ui_print(f"Started TCP port {port} listener forced to Rig {assigned_radio_index}")
            except Exception:
                time.sleep(2.0)
                continue

            while True:
                if config.CONFIG["PORT_RADIO_1" if assigned_radio_index == 1 else "PORT_RADIO_2"] != config.active_ports[assigned_radio_index]:
                    config.ui_print(f"🔄 Recycling listener loop to target new structural port parameters...")
                    break
                    
                try: conn, addr = server_socket.accept()
                except socket.timeout: continue
                
                with conn:
                    conn.settimeout(1.0)
                    while True:
                        try:
                            data = conn.recv(4096)
                            if not data: break
                        except socket.timeout: break
                        
                        json_payload = json.dumps({"status": "success", "message": f"Radio {assigned_radio_index} targeted"})
                        http_response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(json_payload)}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n{json_payload}"
                        try: conn.sendall(http_response.encode('utf-8'))
                        except: pass
                        
                        raw_string = data.decode('utf-8', errors='ignore')
                        if "OPTIONS" in raw_string: break
                        
                        raw_string_lower = raw_string.lower()
                        target_vfo = "A"
                        if "vfo_b" in raw_string_lower or "vfo-b" in raw_string_lower or "vfob" in raw_string_lower or "sub" in raw_string_lower:
                            target_vfo = "B"
                        
                        match = re.search(r'/(\d{5,9})/([a-zA-Z0-9\-]+)', raw_string)
                        if match:
                            extracted_freq = int(match.group(1))
                            extracted_mode = match.group(2).upper()
                            radio_label = config.CONFIG["RADIO_1_NAME"] if assigned_radio_index == 1 else config.CONFIG["RADIO_2_NAME"]
                            
                            config.ui_print(f"[Port {port}] Intercepted Wavelog Command -> {extracted_freq} Hz ({'VFO-B / Sub' if target_vfo == 'B' else 'VFO-A / Main'})")
                            with config.queue_lock:
                                config.tune_queue.append((assigned_radio_index, extracted_freq, extracted_mode, "wavelog", target_vfo))
                            threading.Thread(target=post_to_wavelog_api, args=(radio_label, extracted_freq, extracted_mode), daemon=True).start()
                        break

# ==========================================
# WEBSOCKET SERVER FOR WAVELOG BRIDGE
# ==========================================
CONNECTED_WS_CLIENTS = set()
WS_CLIENTS_LOCK = threading.Lock()

# Global variables to track current focus state
current_active_call = ""
current_active_grid = ""

def start_native_websocket_server():
    """Runs a lightweight native WebSocket server to broadcast WSJT-X targets to the browser."""
    def server_loop():
        ws_port = 2334 
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("127.0.0.1", ws_port))
                server.listen()
                config.ui_print(f"🌐 [WebSocket Server] Listening on ws://127.0.0.1:{ws_port}...")
            except Exception as e:
                config.ui_print(f"❌ WebSocket server failed to start: {e}")
                return

            while True:
                try:
                    conn, addr = server.accept()
                    threading.Thread(target=handle_ws_client, args=(conn,), daemon=True).start()
                except:
                    time.sleep(1)

    threading.Thread(target=server_loop, daemon=True).start()

def handle_ws_client(conn):
    """Performs the WebSocket handshake and keeps the browser socket connection alive."""
    global current_active_call, current_active_grid
    try:
        conn.settimeout(5.0)
        request = conn.recv(4096).decode('utf-8', errors='ignore')
        
        match = re.search(r"Sec-WebSocket-Key:\s*(.+)\r\n", request)
        if not match:
            conn.close()
            return
            
        key = match.group(1).strip()
        magic_guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept_sha1 = hashlib.sha1((key + magic_guid).encode('utf-8')).digest()
        accept_key = base64.b64encode(accept_sha1).decode('utf-8')
        
        handshake = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
        )
        conn.sendall(handshake.encode('utf-8'))
        conn.settimeout(None) 
        
        with WS_CLIENTS_LOCK:
            CONNECTED_WS_CLIENTS.add(conn)
            config.ui_print(f"🔌 [WebSocket] Browser client connected! Total connected: {len(CONNECTED_WS_CLIENTS)}")
            
            # INSTANT PUSH: If we already have an active station, send it to the new client right away!
            if current_active_call:
                config.ui_print(f"⚡ [WebSocket Sync] Instantly pushing current active target '{current_active_call}' to new client.")
                payload_bytes = json.dumps({"callsign": current_active_call, "locator": current_active_grid}).encode('utf-8')
                frame = struct.pack("!BB", 0x81, len(payload_bytes)) + payload_bytes
                try:
                    conn.sendall(frame)
                except:
                    pass
        
        while True:
            data = conn.recv(1024)
            if not data: break
    except:
        pass
    finally:
        with WS_CLIENTS_LOCK:
            CONNECTED_WS_CLIENTS.discard(conn)
            config.ui_print(f"🔌 [WebSocket] Browser client disconnected. Total remaining: {len(CONNECTED_WS_CLIENTS)}")
        try: conn.close()
        except: pass

def broadcast_ws_message(payload_str):
    """Wraps text strings inside unmasked WebSocket Text Frames and transmits."""
    payload_bytes = payload_str.encode('utf-8')
    payload_len = len(payload_bytes)
    
    if payload_len <= 125:
        header = struct.pack("!BB", 0x81, payload_len)
    elif payload_len <= 65535:
        header = struct.pack("!BBH", 0x81, 126, payload_len)
    else:
        header = struct.pack("!BBQ", 0x81, 127, payload_len)
        
    frame = header + payload_bytes
    
    with WS_CLIENTS_LOCK:
        active_count = len(CONNECTED_WS_CLIENTS)
        if active_count > 0:
            config.ui_print(f"📤 [WebSocket Broadcast] Sending to {active_count} client(s): {payload_str}")
        else:
            config.ui_print("📤 [WebSocket Broadcast] No active browser clients are listening to receive this update.")
            
        dead_clients = set()
        for client in CONNECTED_WS_CLIENTS:
            try:
                client.sendall(frame)
            except:
                dead_clients.add(client)
        for dead in dead_clients:
            CONNECTED_WS_CLIENTS.discard(dead)

def decode_utf8_string(buffer, offset):
    """Parses a Qt-serialized byte string prefixed by a 4-byte length header."""
    if offset + 4 > len(buffer):
        return "", offset
    length = struct.unpack(">I", buffer[offset:offset+4])[0]
    offset += 4
    if length == 0xFFFFFFFF or length == 0:
        return "", offset
    if offset + length > len(buffer):
        return "", offset
    string_bytes = buffer[offset:offset+length]
    return string_bytes.decode('utf-8', errors='ignore'), offset + length

# ==========================================
# WSJT-X UDP DECODER & RUNNER
# ==========================================
def wsjtx_udp_tracking_listener():
    """Listens for live WSJT-X Status Packets and updates Wavelog's working cache."""
    global current_active_call, current_active_grid
    
    # Start the local helper WebSocket engine up front
    start_native_websocket_server()
    
    config.ui_print("📡 [WSJT-X Listener] Spinning up network background worker...")
    
    # Internal tracker flag to evaluate true state transitions
    was_callsign_active = False
    
    while True:
        # WSJTX_ENABLE is now controlled safely from the Settings Dialog
        if not config.CONFIG.get("WSJTX_ENABLE", True):
            time.sleep(2.0)
            continue
            
        ip = config.CONFIG.get("WSJTX_IP", "224.0.0.1")
        port = int(config.CONFIG.get("WSJTX_PORT", 2237))
        mode = config.CONFIG.get("WSJTX_MODE", "Multicast")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(2.0)
            
            if mode == "Multicast":
                sock.bind(('', port))
                mreq = struct.pack("4sl", socket.inet_aton(ip), socket.INADDR_ANY)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                config.ui_print(f"🌐 [WSJT-X Socket] Bound and subscribed to Multicast Group {ip}:{port}")
            else:
                sock.bind((ip, port))
                config.ui_print(f"🌐 [WSJT-X Socket] Bound to Unicast Interface {ip}:{port}")
                
            config.status_states["wsjtx_link"] = "online"
            
            while config.CONFIG.get("WSJTX_ENABLE", True):
                try:
                    message, addr = sock.recvfrom(2048)
                    
                    if len(message) < 12:
                        continue
                    
                    magic_number = struct.unpack(">I", message[0:4])[0]
                    if magic_number not in (0xADBCCBDA, 0xADBCCBDB):
                        continue
                        
                    packet_type = struct.unpack(">I", message[8:12])[0]
                    
                    if packet_type == 1: # Status Packet
                        offset = 12
                        _, offset = decode_utf8_string(message, offset) # ID
                        dial_freq = struct.unpack(">Q", message[offset:offset+8])[0]
                        offset += 8 # Dial Freq
                        _, offset = decode_utf8_string(message, offset) # Mode
                        
                        dx_callsign, offset = decode_utf8_string(message, offset)
                        dx_callsign = dx_callsign.strip() if dx_callsign else ""
                        
                        _, offset = decode_utf8_string(message, offset) # Report
                        _, offset = decode_utf8_string(message, offset) # Tx Mode
                        offset += 3 # Skip Tx Enabled, Transmitting, Decoding bools
                        offset += 8 # Skip Rx DF, Tx DF
                        _, offset = decode_utf8_string(message, offset) # DE Call
                        _, offset = decode_utf8_string(message, offset) # DE Grid
                        
                        dx_grid, offset = decode_utf8_string(message, offset)
                        dx_grid = dx_grid.strip() if dx_grid else ""
                        
                        # --- CONFIGURED LOGIC STATE TRACKER EVALUATION ---
                        if dx_callsign == "":
                            # Case A: Transitioning from filled callsign to empty space
                            if was_callsign_active:
                                config.ui_print("📉 [WSJT-X Clear Focus] Callsign cleared in UI. Sending command to reset browser form layout.")
                                current_active_call = ""
                                current_active_grid = ""
                                was_callsign_active = False
                                
                                if config.CONFIG.get("SEND_TO_BROWSER", True):
                                    clear_payload = json.dumps({"clear": True})
                                    broadcast_ws_message(clear_payload)
                        else:
                            # Case B: Target focus updated or added
                            was_callsign_active = True
                            if dx_callsign != current_active_call or dx_grid != current_active_grid:
                                current_active_call = dx_callsign
                                current_active_grid = dx_grid
                                
                                config.ui_print(f"🎯 [WSJT-X Focus] Active: {dx_callsign} | Grid: {dx_grid or 'None'}")
                                
                                if config.CONFIG.get("SEND_TO_BROWSER", True):
                                    ws_payload = json.dumps({
                                        "callsign": dx_callsign,
                                        "locator": dx_grid
                                    })
                                    broadcast_ws_message(ws_payload)
                                else:
                                    config.ui_print("⏸️ [Bridge paused] Update received but Browser Outbound is suspended.")
                                
                except socket.timeout:
                    continue
                except Exception as e:
                    config.ui_print(f"⚠️ Error parsing WSJT-X network packet: {e}")
                    
        except Exception as net_err:
            config.ui_print(f"❌ WSJT-X Network binding failed: {net_err}. Retrying in 10s...")
            config.status_states["wsjtx_link"] = "offline"
            time.sleep(10.0)