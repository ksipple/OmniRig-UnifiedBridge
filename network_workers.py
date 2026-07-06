import time
import socket
import re
import json
import xmlrpc.client
import requests
import threading
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