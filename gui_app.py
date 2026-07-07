import os
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import config
import network_workers

class OptionsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Bridge Settings & Parameters")
        self.geometry("450x430")  # Adjusted down due to removed elements
        self.configure(bg="#252526")
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(1, weight=1)
        self.create_fields()

    def create_fields(self):
        lbl_info = tk.Label(self, text="Configure System Parameters", font=('Helvetica', 11, 'bold'), bg="#252526", fg="#00ffcc")
        lbl_info.grid(row=0, column=0, columnspan=2, pady=15, padx=10, sticky='w')

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

        current_row = 1
        for key, label_text in fields:
            lbl = tk.Label(self, text=label_text, bg="#252526", fg="#ffffff", font=('Helvetica', 9))
            lbl.grid(row=current_row, column=0, sticky='e', padx=15, pady=6)
            
            if key == "FORCE_MODE_SELECTION":
                combobox = ttk.Combobox(self, values=["NONE", "CW", "CW-R", "LSB", "USB", "FM", "AM", "DATA", "DATA-R"], state="readonly")
                curr_val = config.CONFIG.get("FORCE_MODE_SELECTION", "DATA").upper()
                combobox.set(curr_val if curr_val in combobox['values'] else "DATA")
                combobox.grid(row=current_row, column=1, sticky='ew', padx=15, pady=6)
                self.entries[key] = combobox
            elif key == "WAVELOG_API_KEY":
                entry_frame = tk.Frame(self, bg="#252526")
                entry_frame.grid(row=current_row, column=1, sticky='ew', padx=15, pady=6)
                
                ent = tk.Entry(entry_frame, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9), show='*')
                ent.insert(0, str(config.CONFIG[key]))
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
                ent.insert(0, str(config.CONFIG[key]))
                ent.grid(row=current_row, column=1, sticky='ew', padx=15, pady=6)
                self.entries[key] = ent
            current_row += 1

        btn_frame = tk.Frame(self, bg="#252526")
        btn_frame.grid(row=current_row, column=0, columnspan=2, pady=20, sticky='ew')
        
        btn_save = tk.Button(btn_frame, text="Save Parameters", bg="#007acc", fg="white", font=('Helvetica', 9, 'bold'), relief='flat', width=15, command=self.save_settings)
        btn_save.pack(side='right', padx=15)
        
        btn_cancel = tk.Button(btn_frame, text="Cancel", bg="#3c3c3c", fg="white", font=('Helvetica', 9), relief='flat', width=10, command=self.destroy)
        btn_cancel.pack(side='right', padx=5)

    def save_settings(self):
        try:
            p1 = int(self.entries["PORT_RADIO_1"].get())
            p2 = int(self.entries["PORT_RADIO_2"].get())
            tol = int(self.entries["FREQ_TOLERANCE"].get())
            
            config.CONFIG["FLDIGI_URL"] = self.entries["FLDIGI_URL"].get().strip()
            config.CONFIG["FORCE_MODE_SELECTION"] = self.entries["FORCE_MODE_SELECTION"].get().strip()
            config.CONFIG["WAVELOG_URL"] = self.entries["WAVELOG_URL"].get().strip()
            config.CONFIG["WAVELOG_API_KEY"] = self.entries["WAVELOG_API_KEY"].get().strip()
            config.CONFIG["RADIO_1_NAME"] = self.entries["RADIO_1_NAME"].get().strip()
            config.CONFIG["RADIO_2_NAME"] = self.entries["RADIO_2_NAME"].get().strip()
            config.CONFIG["PORT_RADIO_1"] = p1
            config.CONFIG["PORT_RADIO_2"] = p2
            config.CONFIG["FREQ_TOLERANCE"] = tol

            self.master.update_labels_from_config()
            config.fldigi_blackout_until = time.time() + 1.0
            config.save_config()
            
            config.ui_print("⚙️ Configuration maps updated and saved to config.json.")
            self.destroy()
        except ValueError:
            messagebox.showerror("Validation Error", "Ports and Tolerance properties must be valid integers.")


class BridgeGUIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniRig - Fldigi - Wavelog Configurable Bridge")
        self.geometry("820x565")
        self.configure(bg="#1e1e1e")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background='#1e1e1e', foreground='#ffffff')
        self.style.configure('TLabelframe', background='#1e1e1e', foreground='#ffffff', bordercolor='#333333')
        self.style.configure('TLabelframe.Label', background='#1e1e1e', foreground='#00ffcc', font=('Helvetica', 10, 'bold'))
        self.style.configure('TCombobox', fieldbackground='#2d2d2d', background='#2d2d2d', foreground='#ffffff')
        
        config._app_instance = self
        
        # Ensure individual radio polling loops default to active state when master switch is enabled
        config.rig_polling_enabled[1] = True
        config.rig_polling_enabled[2] = True
        
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

        ops_lf = ttk.LabelFrame(sys_frame, text=" ROUTING & UTILITIES ")
        ops_lf.pack(side='right', fill='both', padx=5, pady=5, expand=True)
        
        target_container = tk.Frame(ops_lf, bg="#1e1e1e")
        target_container.pack(fill='x', padx=10, pady=6)
        
        lbl_target = tk.Label(target_container, text="Fldigi Target Rig:", bg="#1e1e1e", fg="#ffffff", font=('Helvetica', 9, 'bold'))
        lbl_target.pack(side='left', padx=5)
        
        self.combo_target = ttk.Combobox(target_container, state="readonly", width=25)
        self.combo_target.pack(side='left', padx=5)
        self.combo_target.bind("<<ComboboxSelected>>", self.on_fldigi_target_changed)
        
        btn_row = tk.Frame(ops_lf, bg="#1e1e1e")
        btn_row.pack(fill='x', padx=10, pady=6, side='bottom')

        btn_options = tk.Button(btn_row, text="⚙️ Options", bg="#3a3a3a", fg="white",
                                font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                command=self.open_options_dialog)
        btn_options.pack(side='left', expand=True, fill='x', padx=2)

        btn_omni_settings = tk.Button(btn_row, text="📻 Omnirig Setup", bg="#3a3a3a", fg="white",
                                      font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                      command=self.open_omnirig_dialog)
        btn_omni_settings.pack(side='left', expand=True, fill='x', padx=2)

        # Global Master On/Off Button
        self.btn_toggle_omni = tk.Button(btn_row, text="🟢 OmniRig: Enabled", bg="#1b5e20", fg="white",
                                         font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                         command=self.toggle_omnirig_global)
        self.btn_toggle_omni.pack(side='left', expand=True, fill='x', padx=2)

        cards_frame = tk.Frame(self, bg="#1e1e1e")
        cards_frame.pack(fill='x', padx=15, pady=5)

        # Rig 1 Visual Panel Block
        self.rig1_lf = ttk.LabelFrame(cards_frame, text=" RIG 1 ")
        self.rig1_lf.pack(side='left', fill='both', expand=True, padx=5, pady=5)

        self.lbl_r1_freq = tk.Label(self.rig1_lf, text="0.000.000 MHz", font=('Courier New', 16, 'bold'), bg="#1e1e1e", fg="#ffffff")
        self.lbl_r1_freq.pack(pady=12)
        self.lbl_r1_freq_b = tk.Label(self.rig1_lf, text="VFO-B / Sub: --", font=('Courier New', 10), bg="#1e1e1e", fg="#888888")
        self.lbl_r1_freq_b.pack(pady=2)
        self.lbl_r1_mode = tk.Label(self.rig1_lf, text="MODE: --", font=('Helvetica', 10), bg="#1e1e1e", fg="#aaaaaa")
        self.lbl_r1_mode.pack(pady=6)

        # Rig 2 Visual Panel Block
        self.rig2_lf = ttk.LabelFrame(cards_frame, text=" RIG 2 ")
        self.rig2_lf.pack(side='right', fill='both', expand=True, padx=5, pady=5)

        self.lbl_r2_freq = tk.Label(self.rig2_lf, text="0.000.000 MHz", font=('Courier New', 16, 'bold'), bg="#1e1e1e", fg="#ffffff")
        self.lbl_r2_freq.pack(pady=12)
        self.lbl_r2_freq_b = tk.Label(self.rig2_lf, text="VFO-B / Sub: --", font=('Courier New', 10), bg="#1e1e1e", fg="#888888")
        self.lbl_r2_freq_b.pack(pady=2)
        self.lbl_r2_mode = tk.Label(self.rig2_lf, text="MODE: --", font=('Helvetica', 10), bg="#1e1e1e", fg="#aaaaaa")
        self.lbl_r2_mode.pack(pady=6)

        log_lf = ttk.LabelFrame(self, text=" LIVE SYSTEM ACTIVITY LOG ")
        log_lf.pack(fill='both', expand=True, padx=15, pady=10)
        self.log_area = scrolledtext.ScrolledText(log_lf, wrap=tk.WORD, height=10, bg="#111111", fg="#33ff33", font=('Consolas', 9), insertbackground='white')
        self.log_area.pack(fill='both', expand=True, padx=5, pady=5)

        self.update_labels_from_config()
        
    def open_options_dialog(self):
        OptionsDialog(self)

    def open_omnirig_dialog(self):
        config.ui_print("⚙️ Requesting OmniRig Settings Setup Interface App...")
        def run():
            paths = [
                r"C:\Program Files (x86)\Afreet\OmniRig\OmniRig.exe",
                r"C:\Program Files\Afreet\OmniRig\OmniRig.exe"
            ]
            exe_path = None
            for p in paths:
                if os.path.exists(p):
                    exe_path = p
                    break
            if exe_path:
                try:
                    subprocess.Popen([exe_path])
                    config.ui_print(f"✅ Executed OmniRig sub-app setup: {exe_path}")
                except Exception as e:
                    config.ui_print(f"❌ Execution failed: {e}")
            else:
                config.ui_print("❌ Could not locate OmniRig.exe setup app paths.")
        threading.Thread(target=run, daemon=True).start()

    def update_labels_from_config(self):
        self.rig1_lf.config(text=f" RIG 1: {config.CONFIG['RADIO_1_NAME']} " + ("[FLDIGI TARGET]" if config.current_fldigi_target_rig == 1 else ""))
        self.rig2_lf.config(text=f" RIG 2: {config.CONFIG['RADIO_2_NAME']} " + ("[FLDIGI TARGET]" if config.current_fldigi_target_rig == 2 else ""))
        
        r1_val = f"Rig 1: {config.CONFIG['RADIO_1_NAME']}"
        r2_val = f"Rig 2: {config.CONFIG['RADIO_2_NAME']}"
        self.combo_target['values'] = [r1_val, r2_val]
        self.combo_target.set(r1_val if config.current_fldigi_target_rig == 1 else r2_val)

    def toggle_omnirig_global(self):
        config.omnirig_global_enabled = not config.omnirig_global_enabled
        if config.omnirig_global_enabled:
            self.btn_toggle_omni.config(text="🟢 OmniRig: Enabled", bg="#1b5e20")
            config.ui_print("⚙️ Master Switch: OmniRig integration global sub-layer ENABLED.")
        else:
            self.btn_toggle_omni.config(text="🔴 OmniRig: Disabled", bg="#b71c1c")
            config.ui_print("⚙️ Master Switch: OmniRig integration global sub-layer DISABLED.")
        self.evaluate_omnirig_process_rules()

    def evaluate_omnirig_process_rules(self):
        """Sends clean state change tasks into the worker queue based on master context variables."""
        if not config.omnirig_global_enabled:
            config.ui_print("🛑 OmniRig processing stopped. Issuing direct hard-kill command sequence...")
            with config.queue_lock:
                config.tune_queue.append((0, 0, "KILL_OMNIRIG", "system"))
        else:
            config.ui_print("🔄 Actively spinning up / recycling OmniRig driver instance connection context...")
            with config.queue_lock:
                config.tune_queue.append((0, 0, "RESTART_OMNIRIG", "system"))

    def on_fldigi_target_changed(self, event):
        val = self.combo_target.get()
        config.current_fldigi_target_rig = 1 if val.startswith("Rig 1") else 2
        config.fldigi_blackout_until = time.time() + 1.0
        self.update_labels_from_config()
        config.ui_print(f"🎯 Fldigi sync target route changed to: Rig {config.current_fldigi_target_rig}")
        
        target_rig = config.current_fldigi_target_rig
        freq_to_push = config.last_freqs[target_rig]
        mode_code = config.last_modes[target_rig]
        friendly_mode = config.OMNIRIG_MODES.get(mode_code, "USB")
        
        if freq_to_push > 0:
            config.ui_print(f"🔄 Sync Target Shifted: Immediately sending Rig {target_rig} VFO ({freq_to_push} Hz) to Fldigi...")
            threading.Thread(target=network_workers.sync_to_fldigi, args=(freq_to_push, friendly_mode), daemon=True).start()

    def draw_status_dot(self, canvas, color):
        canvas.delete("all")
        canvas.create_oval(2, 2, 9, 9, fill=color, outline="#333333")

    def log_message(self, message):
        def append():
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
        self.after(0, append)

    def update_gui_indicators(self):
        f1, f1_b = config.last_freqs[1], config.last_freqs_b[1]
        m1 = config.OMNIRIG_MODES.get(config.last_modes[1], "--") if config.last_modes[1] else "--"
        if f1 > 0:
            self.lbl_r1_freq.config(text=f"{f1 / 1_000_000:,.6f} MHz")
            self.lbl_r1_mode.config(text=f"MODE: {m1}")
        else:
            self.lbl_r1_freq.config(text="0.000.000 MHz")
            self.lbl_r1_mode.config(text="MODE: --")
        self.lbl_r1_freq_b.config(text=f"VFO-B: {f1_b / 1_000_000:,.6f} MHz" if f1_b > 0 else "VFO-B: --", fg="#00ffcc" if f1_b > 0 else "#aaaaaa")

        f2, f2_b = config.last_freqs[2], config.last_freqs_b[2]
        m2 = config.OMNIRIG_MODES.get(config.last_modes[2], "--") if config.last_modes[2] else "--"
        if f2 > 0:
            self.lbl_r2_freq.config(text=f"{f2 / 1_000_000:,.6f} MHz")
            self.lbl_r2_mode.config(text=f"MODE: {m2}")
        else:
            self.lbl_r2_freq.config(text="0.000.000 MHz")
            self.lbl_r2_mode.config(text="MODE: --")
        self.lbl_r2_freq_b.config(text=f"VFO-B: {f2_b / 1_000_000:,.6f} MHz" if f2_b > 0 else "VFO-B: --", fg="#00ffcc" if f2_b > 0 else "#aaaaaa")

        self.draw_status_dot(self.canvas_omni, "#00ff00" if config.status_states["omnirig"] == "online" else "#ff0000")
        self.lbl_omni.config(text="OmniRig: Connected" if config.status_states["omnirig"] == "online" else "OmniRig: Offline", fg="#ffffff" if config.status_states["omnirig"] == "online" else "#ff8888")

        self.draw_status_dot(self.canvas_fldigi, "#00ff00" if config.status_states["fldigi"] == "online" else "#ff0000")
        self.lbl_fldigi.config(text="Fldigi Link: Active" if config.status_states["fldigi"] == "online" else "Fldigi Link: Offline", fg="#ffffff" if config.status_states["fldigi"] == "online" else "#ff8888")

        self.draw_status_dot(self.canvas_wave, "#00ff00" if config.status_states["wavelog"] == "online" else "#ff0000")
        self.lbl_wave.config(text="Wavelog Cloud: Connected" if config.status_states["wavelog"] == "online" else "Wavelog Cloud: Offline", fg="#ffffff" if config.status_states["wavelog"] == "online" else "#ff8888")

        self.after(200, self.update_gui_indicators)

    def on_close(self): self.destroy(); import sys; sys.exit(0)