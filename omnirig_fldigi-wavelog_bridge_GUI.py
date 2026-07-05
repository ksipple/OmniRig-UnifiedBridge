import sys
import os
import time
import threading
import socket
import re
import json
import xmlrpc.client
import requests
import win32com.client
import pythoncom
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ==========================================
# ---       DYNAMIC CONFIGURATION        ---
# ==========================================
# These parameters can now be updated on the fly via the GUI Options Dialog
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
    "FREQ_TOLERANCE": 10
}

def load_config():
    global CONFIG
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if k in CONFIG:
                        CONFIG[k] = type(CONFIG[k])(v)
        except Exception as e:
            print(f"Error loading config.json: {e}")

def save_config():
    config_path = "config.json"
    try:
        with open(config_path, "w") as f:
            json.dump(CONFIG, f, indent=4)
    except Exception as e:
        print(f"Error saving config.json: {e}")

# Load configuration on startup
load_config()


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

# --- Global Tracking States for Controls & Status Flags ---
rig_polling_enabled = {1: True, 2: True}
status_states = {"omnirig": "offline", "fldigi": "offline", "wavelog": "offline"}
current_fldigi_target_rig = 1  

# Track structural socket changes to force listener teardowns automatically if ports change
active_ports = {1: CONFIG["PORT_RADIO_1"], 2: CONFIG["PORT_RADIO_2"]}

# ==========================================
# ---        GUI OPTIONS DIALOG          ---
# ==========================================

class OptionsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Bridge Settings & Parameters")
        self.geometry("450x450")
        self.configure(bg="#252526")
        self.transient(parent)
        self.grab_set()
        
        # Grid weight configuration
        self.grid_columnconfigure(1, weight=1)
        
        # Setup form layout elements
        self.create_fields()

    def create_fields(self):
        # Header text
        lbl_info = tk.Label(self, text="Configure System Parameters", font=('Helvetica', 11, 'bold'), bg="#252526", fg="#00ffcc")
        lbl_info.grid(row=0, column=0, columnspan=2, pady=15, padx=10, sticky='w')

        # Form fields helper logic
        self.entries = {}
        fields = [
            ("FLDIGI_URL", "Fldigi XML-RPC URL:"),
            ("FORCE_MODE_SELECTION", "Force Mode Selection:"),
            ("WAVELOG_URL", "Wavelog URL:"),
            ("WAVELOG_API_KEY", "Wavelog API Key:"),
            ("RADIO_1_NAME", "Rig 1 Radio Name:"),
            ("RADIO_2_NAME", "Rig 2 Radio Name:"),
            ("PORT_RADIO_1", "Rig 1 TCP Inbound Port:"),
            ("PORT_RADIO_2", "Rig 2 TCP Inbound Port:"),
            ("FREQ_TOLERANCE", "Frequency Sync Tolerance (Hz):")
        ]

        for idx, (key, label_text) in enumerate(fields, start=1):
            lbl = tk.Label(self, text=label_text, bg="#252526", fg="#ffffff", font=('Helvetica', 9))
            lbl.grid(row=idx, column=0, sticky='e', padx=15, pady=6)
            
            if key == "FORCE_MODE_SELECTION":
                combobox = ttk.Combobox(self, values=["NONE", "CW", "CW-R", "LSB", "USB", "FM", "AM", "DATA", "DATA-R"], state="readonly")
                curr_val = CONFIG.get("FORCE_MODE_SELECTION", "DATA").upper()
                if curr_val in combobox['values']:
                    combobox.set(curr_val)
                else:
                    combobox.set("DATA")
                combobox.grid(row=idx, column=1, sticky='ew', padx=15, pady=6)
                self.entries[key] = combobox
            elif key == "WAVELOG_API_KEY":
                entry_frame = tk.Frame(self, bg="#252526")
                entry_frame.grid(row=idx, column=1, sticky='ew', padx=15, pady=6)
                
                ent = tk.Entry(entry_frame, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9), show='*')
                ent.insert(0, str(CONFIG[key]))
                ent.pack(side='left', fill='x', expand=True)
                self.entries[key] = ent
                
                def toggle_api_key_visibility(e=ent):
                    if e.cget('show') == '*':
                        e.config(show='')
                        btn_toggle.config(text="🙈")
                    else:
                        e.config(show='*')
                        btn_toggle.config(text="👁️")
                
                btn_toggle = tk.Button(entry_frame, text="👁️", bg="#3c3c3c", fg="white", font=('Helvetica', 8), relief='flat', command=toggle_api_key_visibility, width=3)
                btn_toggle.pack(side='right', padx=(5, 0))
            else:
                ent = tk.Entry(self, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
                ent.insert(0, str(CONFIG[key]))
                ent.grid(row=idx, column=1, sticky='ew', padx=15, pady=6)
                self.entries[key] = ent

        # Action Buttons frame
        btn_frame = tk.Frame(self, bg="#252526")
        btn_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=20, sticky='ew')
        
        btn_save = tk.Button(btn_frame, text="Save Parameters", bg="#007acc", fg="white", font=('Helvetica', 9, 'bold'), relief='flat', width=15, command=self.save_settings)
        btn_save.pack(side='right', padx=15)
        
        btn_cancel = tk.Button(btn_frame, text="Cancel", bg="#3c3c3c", fg="white", font=('Helvetica', 9), relief='flat', width=10, command=self.destroy)
        btn_cancel.pack(side='right', padx=5)

    def save_settings(self):
        global active_ports, fldigi_blackout_until
        try:
            # Validate input types before saving
            p1 = int(self.entries["PORT_RADIO_1"].get())
            p2 = int(self.entries["PORT_RADIO_2"].get())
            tol = int(self.entries["FREQ_TOLERANCE"].get())
            
            # Commit mutations directly to global space
            CONFIG["FLDIGI_URL"] = self.entries["FLDIGI_URL"].get().strip()
            CONFIG["FORCE_MODE_SELECTION"] = self.entries["FORCE_MODE_SELECTION"].get().strip()
            CONFIG["WAVELOG_URL"] = self.entries["WAVELOG_URL"].get().strip()
            CONFIG["WAVELOG_API_KEY"] = self.entries["WAVELOG_API_KEY"].get().strip()
            CONFIG["RADIO_1_NAME"] = self.entries["RADIO_1_NAME"].get().strip()
            CONFIG["RADIO_2_NAME"] = self.entries["RADIO_2_NAME"].get().strip()
            CONFIG["PORT_RADIO_1"] = p1
            CONFIG["PORT_RADIO_2"] = p2
            CONFIG["FREQ_TOLERANCE"] = tol

            # Update parent application container panel labels instantly
            self.master.update_labels_from_config()
            fldigi_blackout_until = time.time() + 1.0
            
            # Save configuration to file
            save_config()
            
            ui_print("⚙️ Configuration maps updated and saved to config.json.")
            self.destroy()
        except ValueError:
            messagebox.showerror("Validation Error", "Ports and Tolerance properties must be valid integers.")

# ==========================================
# ---         MAIN APP INTERFACE         ---
# ==========================================

class BridgeGUIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniRig - Fldigi - Wavelog Configurable Bridge")
        self.geometry("780x615")
        self.configure(bg="#1e1e1e")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background='#1e1e1e', foreground='#ffffff')
        self.style.configure('TLabelframe', background='#1e1e1e', foreground='#ffffff', bordercolor='#333333')
        self.style.configure('TLabelframe.Label', background='#1e1e1e', foreground='#00ffcc', font=('Helvetica', 10, 'bold'))
        self.style.configure('TCheckbutton', background='#1e1e1e', foreground='#ffffff', font=('Helvetica', 9))
        self.style.configure('TCombobox', fieldbackground='#2d2d2d', background='#2d2d2d', foreground='#ffffff')
        
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_gui_indicators()

    def create_widgets(self):
        header_frame = tk.Frame(self, bg="#2d2d2d", height=45)
        header_frame.pack(fill='x', side='top')
        lbl_title = tk.Label(header_frame, text="📡 MULTI-RIG INTEGRATED CONTROLLER", font=('Helvetica', 12, 'bold'), bg="#2d2d2d", fg="#00ffcc")
        lbl_title.pack(pady=10)

        sys_frame = tk.Frame(self, bg="#1e1e1e")
        sys_frame.pack(fill='x', padx=15, pady=5)

        # Status Indicators Frame
        status_lf = ttk.LabelFrame(sys_frame, text=" LINK STATUS ")
        status_lf.pack(side='left', fill='both', padx=5, pady=5, expand=True)

        self.canvas_omni = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_omni.grid(row=0, column=0, padx=8, pady=5)
        self.lbl_omni = tk.Label(status_lf, text="OmniRig: Checking...", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_omni.grid(row=0, column=1, sticky='w', padx=2)

        self.canvas_fldigi = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_fldigi.grid(row=1, column=0, padx=8, pady=5)
        self.lbl_fldigi = tk.Label(status_lf, text="Fldigi Link: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_fldigi.grid(row=1, column=1, sticky='w', padx=2)

        self.canvas_wave = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_wave.grid(row=2, column=0, padx=8, pady=5)
        self.lbl_wave = tk.Label(status_lf, text="Wavelog Cloud: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_wave.grid(row=2, column=1, sticky='w', padx=2)

        # Controls & Routing Frame
        ops_lf = ttk.LabelFrame(sys_frame, text=" ROUTING & UTILITIES ")
        ops_lf.pack(side='right', fill='both', padx=5, pady=5, expand=True)
        
        target_container = tk.Frame(ops_lf, bg="#1e1e1e")
        target_container.pack(fill='x', padx=10, pady=6)
        
        lbl_target = tk.Label(target_container, text="Fldigi Target Rig:", bg="#1e1e1e", fg="#ffffff", font=('Helvetica', 9, 'bold'))
        lbl_target.pack(side='left', padx=5)
        
        self.combo_target = ttk.Combobox(target_container, state="readonly", width=25)
        self.combo_target.pack(side='left', padx=5)
        self.combo_target.bind("<<ComboboxSelected>>", self.on_fldigi_target_changed)
        
        # Buttons Row (Kill, Setup & Options)
        btn_row = tk.Frame(ops_lf, bg="#1e1e1e")
        btn_row.pack(fill='x', padx=10, pady=6, side='bottom')

        btn_options = tk.Button(btn_row, text="⚙️ Options...", bg="#3a3a3a", fg="white",
                                font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                command=self.open_options_dialog)
        btn_options.pack(side='left', expand=True, fill='x', padx=2)

        btn_omni_settings = tk.Button(btn_row, text="📻 OmniRig Setup", bg="#3a3a3a", fg="white",
                                      font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                      command=self.open_omnirig_dialog)
        btn_omni_settings.pack(side='left', expand=True, fill='x', padx=2)

        btn_kill_omni = tk.Button(btn_row, text="💥 Kill OmniRig", bg="#b71c1c", fg="white", 
                                  font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                  command=self.force_kill_omni_process)
        btn_kill_omni.pack(side='right', expand=True, fill='x', padx=2)

        # Radio Cards
        cards_frame = tk.Frame(self, bg="#1e1e1e")
        cards_frame.pack(fill='x', padx=15, pady=5)

        self.rig1_lf = ttk.LabelFrame(cards_frame, text=" RIG 1 ")
        self.rig1_lf.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        self.lbl_r1_freq = tk.Label(self.rig1_lf, text="0.000.000 MHz", font=('Courier New', 16, 'bold'), bg="#1e1e1e", fg="#ffffff")
        self.lbl_r1_freq.pack(pady=2)
        self.lbl_r1_freq_b = tk.Label(self.rig1_lf, text="VFO-B: 0.000.000 MHz", font=('Courier New', 11), bg="#1e1e1e", fg="#888888")
        self.lbl_r1_freq_b.pack(pady=2)
        self.lbl_r1_mode = tk.Label(self.rig1_lf, text="MODE: --", font=('Helvetica', 10), bg="#1e1e1e", fg="#aaaaaa")
        self.lbl_r1_mode.pack(pady=2)
        self.reg1_enabled_var = tk.BooleanVar(value=True)
        cb_r1 = ttk.Checkbutton(self.rig1_lf, text="Enable OmniRig Polling", variable=self.reg1_enabled_var, command=self.toggle_r1)
        cb_r1.pack(pady=6)

        self.rig2_lf = ttk.LabelFrame(cards_frame, text=" RIG 2 ")
        self.rig2_lf.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        self.lbl_r2_freq = tk.Label(self.rig2_lf, text="0.000.000 MHz", font=('Courier New', 16, 'bold'), bg="#1e1e1e", fg="#ffffff")
        self.lbl_r2_freq.pack(pady=2)
        self.lbl_r2_freq_b = tk.Label(self.rig2_lf, text="VFO-B: 0.000.000 MHz", font=('Courier New', 11), bg="#1e1e1e", fg="#888888")
        self.lbl_r2_freq_b.pack(pady=2)
        self.lbl_r2_mode = tk.Label(self.rig2_lf, text="MODE: --", font=('Helvetica', 10), bg="#1e1e1e", fg="#aaaaaa")
        self.lbl_r2_mode.pack(pady=2)
        self.reg2_enabled_var = tk.BooleanVar(value=True)
        cb_r2 = ttk.Checkbutton(self.rig2_lf, text="Enable OmniRig Polling", variable=self.reg2_enabled_var, command=self.toggle_r2)
        cb_r2.pack(pady=6)

        # Log Terminal Output console
        log_lf = ttk.LabelFrame(self, text=" LIVE SYSTEM ACTIVITY LOG ")
        log_lf.pack(fill='both', expand=True, padx=15, pady=10)
        self.log_area = scrolledtext.ScrolledText(log_lf, wrap=tk.WORD, height=10, bg="#111111", fg="#33ff33", font=('Consolas', 9), insertbackground='white')
        self.log_area.pack(fill='both', expand=True, padx=5, pady=5)

        # Apply initial configuration map labels
        self.update_labels_from_config()
        
    def open_options_dialog(self):
        OptionsDialog(self)

    def open_omnirig_dialog(self):
        ui_print("⚙️ Requesting OmniRig Settings Dialog...")
        def run():
            import subprocess
            paths = [
                r"C:\Program Files (x86)\Afreet\OmniRig\OmniRig.exe",
                r"C:\Program Files\Afreet\OmniRig\OmniRig.exe"
            ]
            exe_path = None
            for p in paths:
                if os.path.exists(p):
                    exe_path = p
                    break
            
            if not exe_path:
                try:
                    import winreg
                    for view in [0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY]:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Afreet\OmniRig", 0, winreg.KEY_READ | view)
                            val, _ = winreg.QueryValueEx(key, "Path")
                            winreg.CloseKey(key)
                            if val:
                                candidate = os.path.join(val, "OmniRig.exe")
                                if os.path.exists(candidate):
                                    exe_path = candidate
                                    break
                        except OSError:
                            pass
                except Exception:
                    pass
            
            if exe_path:
                try:
                    subprocess.Popen([exe_path])
                    ui_print(f"✅ OmniRig settings program launched: {exe_path}")
                except Exception as e:
                    ui_print(f"❌ Failed to launch OmniRig executable: {e}")
            else:
                ui_print("❌ OmniRig executable not found on this system. Please check your installation.")
        threading.Thread(target=run, daemon=True).start()

    def update_labels_from_config(self):
        """Forces container frames to redraw labels when configuration changes."""
        self.rig1_lf.config(text=f" RIG 1: {CONFIG['RADIO_1_NAME']} " + ("[FLDIGI TARGET]" if current_fldigi_target_rig == 1 else ""))
        self.rig2_lf.config(text=f" RIG 2: {CONFIG['RADIO_2_NAME']} " + ("[FLDIGI TARGET]" if current_fldigi_target_rig == 2 else ""))
        
        r1_val = f"Rig 1: {CONFIG['RADIO_1_NAME']}"
        r2_val = f"Rig 2: {CONFIG['RADIO_2_NAME']}"
        self.combo_target['values'] = [r1_val, r2_val]
        
        if current_fldigi_target_rig == 1:
            self.combo_target.set(r1_val)
        else:
            self.combo_target.set(r2_val)

    def toggle_r1(self): rig_polling_enabled[1] = self.reg1_enabled_var.get()
    def toggle_r2(self): rig_polling_enabled[2] = self.reg2_enabled_var.get()

    def on_fldigi_target_changed(self, event):
        global current_fldigi_target_rig, fldigi_blackout_until
        val = self.combo_target.get()
        current_fldigi_target_rig = 1 if val.startswith("Rig 1") else 2
        fldigi_blackout_until = time.time() + 1.0
        self.update_labels_from_config()
        ui_print(f"🎯 Fldigi sync target route changed to: Rig {current_fldigi_target_rig}")

    def force_kill_omni_process(self):
        if messagebox.askyesno("Confirm Process Kill", "Are you sure you want to force terminate OmniRig.exe via taskkill?"):
            ui_print("⚠️ Initiating emergency process termination sequence...")
            try:
                if os.system("taskkill /f /im OmniRig.exe") == 0:
                    ui_print("✅ Process OmniRig.exe was terminated successfully.")
                else:
                    ui_print("局 Request dispatched (Process may already be inactive).")
            except Exception as e: ui_print(f"❌ Operation failed: {e}")

    def draw_status_dot(self, canvas, color):
        canvas.delete("all")
        canvas.create_oval(2, 2, 11, 11, fill=color, outline="#333333")

    def log_message(self, message):
        def append():
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
        self.after(0, append)

    def update_gui_indicators(self):
        # Update Rig 1 Displays
        if rig_polling_enabled[1]:
            f1 = last_freqs[1]
            f1_b = last_freqs_b[1]
            m1 = OMNIRIG_MODES.get(last_modes[1], "--") if last_modes[1] else "--"
            if f1 > 0:
                self.lbl_r1_freq.config(text=f"{f1 / 1_000_000:,.6f} MHz", fg="#ffffff")
                self.lbl_r1_mode.config(text=f"MODE: {m1}")
            if f1_b > 0:
                self.lbl_r1_freq_b.config(text=f"VFO-B: {f1_b / 1_000_000:,.6f} MHz", fg="#00ffcc")
            else:
                self.lbl_r1_freq_b.config(text="VFO-B: --.------ MHz", fg="#aaaaaa")
        else:
            self.lbl_r1_freq.config(text="PAUSED / DISABLED", fg="#ff4444")
            self.lbl_r1_freq_b.config(text="VFO-B: --", fg="#ff4444")
            self.lbl_r1_mode.config(text="MODE: --")

        # Update Rig 2 Displays
        if rig_polling_enabled[2]:
            f2 = last_freqs[2]
            f2_b = last_freqs_b[2]
            m2 = OMNIRIG_MODES.get(last_modes[2], "--") if last_modes[2] else "--"
            if f2 > 0:
                self.lbl_r2_freq.config(text=f"{f2 / 1_000_000:,.6f} MHz", fg="#ffffff")
                self.lbl_r2_mode.config(text=f"MODE: {m2}")
            if f2_b > 0:
                self.lbl_r2_freq_b.config(text=f"VFO-B: {f2_b / 1_000_000:,.6f} MHz", fg="#00ffcc")
            else:
                self.lbl_r2_freq_b.config(text="VFO-B: --.------ MHz", fg="#aaaaaa")
        else:
            self.lbl_r2_freq.config(text="PAUSED / DISABLED", fg="#ff4444")
            self.lbl_r2_freq_b.config(text="VFO-B: --", fg="#ff4444")
            self.lbl_r2_mode.config(text="MODE: --")

        # Status Dot Render Engines
        self.draw_status_dot(self.canvas_omni, "#00ff00" if status_states["omnirig"] == "online" else "#ff0000")
        self.lbl_omni.config(text="OmniRig: Connected" if status_states["omnirig"] == "online" else "OmniRig: Offline / Disconnected", fg="#ffffff" if status_states["omnirig"] == "online" else "#ff8888")

        self.draw_status_dot(self.canvas_fldigi, "#00ff00" if status_states["fldigi"] == "online" else "#ff0000")
        self.lbl_fldigi.config(text="Fldigi Link: Active" if status_states["fldigi"] == "online" else "Fldigi Link: Offline", fg="#ffffff" if status_states["fldigi"] == "online" else "#ff8888")

        self.draw_status_dot(self.canvas_wave, "#00ff00" if status_states["wavelog"] == "online" else "#ff0000")
        self.lbl_wave.config(text="Wavelog Cloud: Connected" if status_states["wavelog"] == "online" else "Wavelog Cloud: Unreachable", fg="#ffffff" if status_states["wavelog"] == "online" else "#ff8888")

        self.after(100, self.update_gui_indicators)

    def on_close(self): self.destroy(); sys.exit(0)

def ui_print(msg):
    print(msg)
    if 'app' in globals() and app: app.log_message(msg)

class TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout=1.0, *args, **kwargs): super().__init__(*args, **kwargs); self.timeout = timeout
    def make_connection(self, host): conn = super().make_connection(host); conn.timeout = self.timeout; return conn

# ==========================================
# ---        OMNIRIG ENGINE THREAD       ---
# ==========================================

def omnirig_worker_thread():
    global rig_blackout_until, fldigi_blackout_until, last_pushed_to_fldigi
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    omnirig = None
    ui_print("OmniRig Sync Engine Active.")

    while True:
        current_time = time.time()
        if omnirig is None:
            try:
                try: omnirig = win32com.client.gencache.EnsureDispatch("OmniRig.OmniRigX")
                except: omnirig = win32com.client.Dispatch("OmniRig.OmniRigX")
                status_states["omnirig"] = "online"
            except Exception: status_states["omnirig"] = "offline"; time.sleep(2.0); continue

        with queue_lock:
            if tune_queue:
                radio_num, target_freq, target_mode, origin = tune_queue.pop(0)
                if not rig_polling_enabled[radio_num]: continue
                try:
                    target_freq_int = int(target_freq)
                    rig_obj = omnirig.Rig1 if radio_num == 1 else omnirig.Rig2
                    radio_label = CONFIG["RADIO_1_NAME"] if radio_num == 1 else CONFIG["RADIO_2_NAME"]
                    force_selection = CONFIG.get("FORCE_MODE_SELECTION", "DATA").upper()
                    if force_selection == "NONE" or origin != "fldigi":
                        mode_code = TO_BITMASK.get(target_mode.upper(), 33554432)
                    else:
                        mode_code = TO_BITMASK.get(force_selection, 33554432)

                    ui_print(f"[{origin.upper()} -> Rig {radio_num}] Moving {radio_label}: {target_freq_int} Hz")
                    rig_blackout_until = current_time + 3.0
                    time.sleep(0.02)

                    if radio_num == 1:
                        rig_obj.Freq = target_freq_int; time.sleep(0.15); rig_obj.Mode = mode_code
                    elif radio_num == 2:
                        rig_obj.FreqA = target_freq_int; time.sleep(0.25); rig_obj.Mode = mode_code; time.sleep(0.05); rig_obj.Freq = target_freq_int 

                    last_freqs[radio_num] = target_freq_int; last_modes[radio_num] = mode_code
                except Exception as e: ui_print(f"❌ Tuning failed: {e}"); status_states["omnirig"] = "offline"; omnirig = None

        if current_time > rig_blackout_until and omnirig:
            # Rig 1 Monitoring Loop
            if rig_polling_enabled[1]:
                try:
                    r1_freq = omnirig.Rig1.Freq; r1_mode = omnirig.Rig1.Mode; status_states["omnirig"] = "online"
                    r1_freq_b = omnirig.Rig1.FreqB
                    
                    if r1_freq > 0 and (abs(r1_freq - last_freqs[1]) > CONFIG["FREQ_TOLERANCE"] or r1_mode != last_modes[1]):
                        friendly_mode = OMNIRIG_MODES.get(r1_mode, "USB")
                        ui_print(f"[{CONFIG['RADIO_1_NAME']} Dial Move] {r1_freq} Hz")
                        threading.Thread(target=post_to_wavelog_api, args=(CONFIG["RADIO_1_NAME"], r1_freq, friendly_mode), daemon=True).start()
                        if current_fldigi_target_rig == 1:
                            fldigi_blackout_until = current_time + 1.5
                            threading.Thread(target=sync_to_fldigi, args=(r1_freq, friendly_mode), daemon=True).start()
                        last_freqs[1] = r1_freq; last_modes[1] = r1_mode
                        
                    if r1_freq_b > 0 and abs(r1_freq_b - last_freqs_b[1]) > CONFIG["FREQ_TOLERANCE"]:
                        ui_print(f"[{CONFIG['RADIO_1_NAME']} VFO-B Change] {r1_freq_b} Hz")
                        last_freqs_b[1] = r1_freq_b
                except: status_states["omnirig"] = "offline"; omnirig = None

            # Rig 2 Monitoring Loop
            if rig_polling_enabled[2] and omnirig:
                try:
                    r2_freq = omnirig.Rig2.Freq; r2_mode = omnirig.Rig2.Mode; status_states["omnirig"] = "online"
                    r2_freq_b = omnirig.Rig2.FreqB
                    
                    if r2_freq > 0 and (abs(r2_freq - last_freqs[2]) > CONFIG["FREQ_TOLERANCE"] or r2_mode != last_modes[2]):
                        friendly_mode = OMNIRIG_MODES.get(r2_mode, "USB")
                        ui_print(f"[{CONFIG['RADIO_2_NAME']} Dial Move] {r2_freq} Hz")
                        threading.Thread(target=post_to_wavelog_api, args=(CONFIG["RADIO_2_NAME"], r2_freq, friendly_mode), daemon=True).start()
                        if current_fldigi_target_rig == 2:
                            fldigi_blackout_until = current_time + 1.5
                            threading.Thread(target=sync_to_fldigi, args=(r2_freq, friendly_mode), daemon=True).start()
                        last_freqs[2] = r2_freq; last_modes[2] = r2_mode
                        
                    if r2_freq_b > 0 and abs(r2_freq_b - last_freqs_b[2]) > CONFIG["FREQ_TOLERANCE"]:
                        ui_print(f"[{CONFIG['RADIO_2_NAME']} VFO-B Change] {r2_freq_b} Hz")
                        last_freqs_b[2] = r2_freq_b
                except: status_states["omnirig"] = "offline"; omnirig = None
        time.sleep(CONFIG["POLL_INTERVAL"])

# ==========================================
# ---       NETWORK SYNC UTILITIES       ---
# ==========================================

def post_to_wavelog_api(radio_label, freq, mode):
    payload = {"key": CONFIG["WAVELOG_API_KEY"], "radio": radio_label, "frequency": freq, "mode": mode}
    try: 
        resp = requests.post(f"{CONFIG['WAVELOG_URL']}/api/radio", json=payload, timeout=2)
        status_states["wavelog"] = "online" if resp.status_code == 200 else "offline"
    except: status_states["wavelog"] = "offline"

def sync_to_fldigi(freq, mode):
    global last_pushed_to_fldigi
    try:
        fldigi = xmlrpc.client.ServerProxy(CONFIG["FLDIGI_URL"], transport=TimeoutTransport(timeout=1.5))
        if abs(fldigi.main.get_frequency() - freq) > CONFIG["FREQ_TOLERANCE"]:
            last_pushed_to_fldigi = int(freq); fldigi.main.set_frequency(float(freq))
        status_states["fldigi"] = "online"
    except: status_states["fldigi"] = "offline"

# ==========================================
# ---        INBOUND TRACKING LOOPS      ---
# ==========================================

def fldigi_polling_listener():
    global fldigi_blackout_until, last_pushed_to_fldigi
    last_fldigi_freq = 0
    while True:
        current_time = time.time()
        try:
            fldigi = xmlrpc.client.ServerProxy(CONFIG["FLDIGI_URL"], transport=TimeoutTransport(timeout=1.0))
            fldigi_freq = fldigi.main.get_frequency(); fldigi_freq_int = int(fldigi_freq)
            status_states["fldigi"] = "online"
            
            if abs(fldigi_freq - last_fldigi_freq) > CONFIG["FREQ_TOLERANCE"]:
                if abs(fldigi_freq_int - last_pushed_to_fldigi) <= CONFIG["FREQ_TOLERANCE"]:
                    last_fldigi_freq = fldigi_freq; time.sleep(0.5); continue
                if current_time > fldigi_blackout_until and last_fldigi_freq != 0:
                    try: fldigi_mode = fldigi.main.get_modem_name()
                    except: fldigi_mode = "USB"
                    ui_print(f"[Fldigi Click] Intercepted Frequency -> {fldigi_freq_int} Hz")
                    with queue_lock: tune_queue.append((current_fldigi_target_rig, fldigi_freq_int, fldigi_mode, "fldigi"))
                last_fldigi_freq = fldigi_freq
        except: status_states["fldigi"] = "offline"
        time.sleep(0.5)

def parameterized_tcp_listener(assigned_radio_index):
    """Listens on the dynamically tracked configuration port matching the radio slot index."""
    while True:
        # Dynamically sample configuration bindings at the loop step entry boundary
        port = CONFIG["PORT_RADIO_1"] if assigned_radio_index == 1 else CONFIG["PORT_RADIO_2"]
        active_ports[assigned_radio_index] = port
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server_socket.bind((CONFIG["HOST"], port))
                server_socket.listen()
                server_socket.settimeout(1.0)
                ui_print(f"Started TCP port {port} listener forced to Rig {assigned_radio_index}")
            except Exception as e:
                time.sleep(2.0)
                continue

            while True:
                # Break out and rebuild the socket structure if the user changed the target port in Options
                if CONFIG["PORT_RADIO_1" if assigned_radio_index == 1 else "PORT_RADIO_2"] != active_ports[assigned_radio_index]:
                    ui_print(f"🔄 Recycling listener loop to target new structural port parameters...")
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
                        
                        match = re.search(r'/(\d{5,9})/([a-zA-Z0-9\-]+)', raw_string)
                        if match:
                            extracted_freq = int(match.group(1))
                            extracted_mode = match.group(2).upper()
                            radio_label = CONFIG["RADIO_1_NAME"] if assigned_radio_index == 1 else CONFIG["RADIO_2_NAME"]
                            
                            ui_print(f"[Port {port}] Intercepted Wavelog Command -> {extracted_freq} Hz")
                            with queue_lock: tune_queue.append((assigned_radio_index, extracted_freq, extracted_mode, "wavelog"))
                            threading.Thread(target=post_to_wavelog_api, args=(radio_label, extracted_freq, extracted_mode), daemon=True).start()
                        break

# ==========================================
# ---         RUNTIME SCHEDULER          ---
# ==========================================

def start_background_subsystems():
    threading.Thread(target=omnirig_worker_thread, daemon=True).start()
    threading.Thread(target=fldigi_polling_listener, daemon=True).start()
    threading.Thread(target=parameterized_tcp_listener, args=(1,), daemon=True).start()
    threading.Thread(target=parameterized_tcp_listener, args=(2,), daemon=True).start()

if __name__ == '__main__':
    app = BridgeGUIApp()
    app.after(1000, start_background_subsystems)
    app.mainloop()