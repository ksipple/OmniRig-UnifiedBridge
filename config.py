import os
import json
import threading

# Dynamic Configuration Map
CONFIG = {
    "FLDIGI_URL": "http://localhost:7362/",
    "FORCE_MODE_SELECTION": "DATA",
    "WAVELOG_URL": "https://wavelog.example.com",
    "WAVELOG_API_KEY": "YOUR_API_KEY_HERE",
    "RADIO_1_NAME": "Radio 1",
    "RADIO_2_NAME": "Radio 2",
    "HOST": "127.0.0.1",
    "PORT_RADIO_1": 54321,
    "PORT_RADIO_2": 54322,
    "POLL_INTERVAL": 0.2,
    "FREQ_TOLERANCE": 10,
    "STARTUP_POLL_RIG_1": True,
    "STARTUP_POLL_RIG_2": True
}

def load_config():
    """Loads runtime configurations from local storage on execution startup."""
    global CONFIG, rig_polling_enabled
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if k in CONFIG:
                        CONFIG[k] = type(CONFIG[k])(v)
            rig_polling_enabled[1] = CONFIG["STARTUP_POLL_RIG_1"]
            rig_polling_enabled[2] = CONFIG["STARTUP_POLL_RIG_2"]
        except Exception as e:
            print(f"Error loading config.json: {e}")

def save_config():
    """Persists current memory mapping adjustments directly to disk filesystem."""
    config_path = "config.json"
    try:
        with open(config_path, "w") as f:
            json.dump(CONFIG, f, indent=4)
    except Exception as e:
        print(f"Error saving config.json: {e}")

# Transceiver Register Bitmasks Maps
OMNIRIG_MODES = {
    16777216: "CW", 8388608: "CW-R", 67108864: "LSB", 33554432: "USB",
    1073741824: "FM", 536870912: "AM", 268435456: "DATA", 134217728: "DATA-R"
}

TO_BITMASK = {
    "CW": 16777216, "CW-R": 8388608, "LSB": 67108864, "USB": 33554432,
    "SSB": 33554432, "FM": 1073741824, "AM": 536870912, "DATA": 134217728,
    "DATA-R": 268435456, "FT8": 268435456, "FT4": 268435456, "RTTY": 134217728  
}

tune_queue = []
queue_lock = threading.Lock()

last_freqs = {1: 0, 2: 0}
last_freqs_b = {1: 0, 2: 0}
last_modes = {1: 0, 2: 0}

rig_blackout_until = 0
fldigi_blackout_until = 0
last_pushed_to_fldigi = 0

rig_polling_enabled = {1: False, 2: False}
status_states = {
    "omnirig": "offline", 
    "fldigi": "offline", 
    "wavelog": "offline",
    "rig1_hw": "offline",  
    "rig2_hw": "offline"   
}
current_fldigi_target_rig = 1  
active_ports = {1: CONFIG["PORT_RADIO_1"], 2: CONFIG["PORT_RADIO_2"]}

_app_instance = None

def ui_print(msg):
    print(msg)
    if _app_instance is not None:
        _app_instance.log_message(msg)

load_config()