import os
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import config
import network_workers
import sdrconnect_worker

class OptionsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Bridge Settings & Parameters")
        self.geometry("480x880")  # Resized to fit beautifully structured sections
        self.configure(bg="#252526")
        self.transient(parent)
        self.grab_set()
        
        self.container = tk.Frame(self, bg="#252526", padx=10, pady=10)
        self.container.pack(fill="both", expand=True)
        self.container.grid_columnconfigure(0, weight=1)
        
        self.create_fields()

    def create_fields(self):
        lbl_info = tk.Label(self.container, text="Configure System Parameters", font=('Helvetica', 12, 'bold'), bg="#252526", fg="#00ffcc")
        lbl_info.pack(anchor="w", pady=(0, 15))

        self.entries = {}

        # Configure dropdown population style for system dialogs with high contrast
        self.option_add('*TCombobox*Listbox.background', '#1e1e1e')
        self.option_add('*TCombobox*Listbox.foreground', '#ffffff')
        self.option_add('*TCombobox*Listbox.selectBackground', '#007acc')
        self.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')

        # ----------------------------------------------------
        # SECTION 1: Core Logging & Wavelog Services
        # ----------------------------------------------------
        sec_wavelog = tk.LabelFrame(self.container, text=" Core Logging & Wavelog Services ", bg="#252526", fg="#00ffcc", font=('Helvetica', 9, 'bold'), padx=10, pady=8)
        sec_wavelog.pack(fill="x", pady=6)
        sec_wavelog.grid_columnconfigure(1, weight=1)

        wavelog_fields = [
            ("FLDIGI_URL", "Fldigi XML-RPC URL:", 0),
            ("FORCE_MODE_SELECTION", "Force Mode Selection:", 1),
            ("WAVELOG_URL", "Wavelog URL:", 2),
            ("WAVELOG_API_KEY", "Wavelog API Key:", 3),
            ("WAVELOG_MAX_INTERVAL", "Max Update Interval (s):", 4)
        ]

        for key, label_text, r_idx in wavelog_fields:
            lbl = tk.Label(sec_wavelog, text=label_text, bg="#252526", fg="#ffffff", font=('Helvetica', 9))
            lbl.grid(row=r_idx, column=0, sticky='e', padx=5, pady=4)

            if key == "FORCE_MODE_SELECTION":
                combobox = ttk.Combobox(sec_wavelog, values=["NONE", "CW", "CW-R", "LSB", "USB", "FM", "AM", "DATA", "DATA-R"], state="readonly")
                curr_val = config.CONFIG.get("FORCE_MODE_SELECTION", "DATA").upper()
                combobox.set(curr_val if curr_val in combobox['values'] else "DATA")
                combobox.grid(row=r_idx, column=1, sticky='ew', padx=5, pady=4)
                self.entries[key] = combobox
            elif key == "WAVELOG_API_KEY":
                entry_frame = tk.Frame(sec_wavelog, bg="#252526")
                entry_frame.grid(row=r_idx, column=1, sticky='ew', padx=5, pady=4)
                
                ent = tk.Entry(entry_frame, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9), show='*')
                ent.insert(0, str(config.CONFIG.get(key, "")))
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
                ent = tk.Entry(sec_wavelog, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
                ent.insert(0, str(config.CONFIG.get(key, "")))
                ent.grid(row=r_idx, column=1, sticky='ew', padx=5, pady=4)
                self.entries[key] = ent

        # ----------------------------------------------------
        # SECTION 2: Rig Connection & Polling
        # ----------------------------------------------------
        sec_rigs = tk.LabelFrame(self.container, text=" Rig Connection & Polling Settings ", bg="#252526", fg="#00ffcc", font=('Helvetica', 9, 'bold'), padx=10, pady=8)
        sec_rigs.pack(fill="x", pady=6)
        sec_rigs.grid_columnconfigure(1, weight=1)

        rig_fields = [
            ("RADIO_1_NAME", "Rig 1 Radio Name:", 0),
            ("RADIO_2_NAME", "Rig 2 Radio Name:", 1),
            ("PORT_RADIO_1", "Rig 1 TCP Port:", 2),
            ("PORT_RADIO_2", "Rig 2 TCP Port:", 3),
            ("FREQ_TOLERANCE", "Freq Tolerance (Hz):", 4)
        ]

        for key, label_text, r_idx in rig_fields:
            lbl = tk.Label(sec_rigs, text=label_text, bg="#252526", fg="#ffffff", font=('Helvetica', 9))
            lbl.grid(row=r_idx, column=0, sticky='e', padx=5, pady=4)
            ent = tk.Entry(sec_rigs, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
            ent.insert(0, str(config.CONFIG.get(key, "")))
            ent.grid(row=r_idx, column=1, sticky='ew', padx=5, pady=4)
            self.entries[key] = ent

        # Add start-polling checkboxes inline with proper contrasting colors
        r_idx = len(rig_fields)
        self.var_poll_r1 = tk.BooleanVar(value=config.CONFIG.get("START_POLL_RIG_1", True))
        lbl_p1 = tk.Label(sec_rigs, text="Poll Rig 1 on Startup:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_p1.grid(row=r_idx, column=0, sticky='e', padx=5, pady=4)
        chk_p1 = tk.Checkbutton(sec_rigs, variable=self.var_poll_r1, bg="#252526", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#252526", activeforeground="#ffffff")
        chk_p1.grid(row=r_idx, column=1, sticky='w', padx=5, pady=4)

        r_idx += 1
        self.var_poll_r2 = tk.BooleanVar(value=config.CONFIG.get("START_POLL_RIG_2", True))
        lbl_p2 = tk.Label(sec_rigs, text="Poll Rig 2 on Startup:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_p2.grid(row=r_idx, column=0, sticky='e', padx=5, pady=4)
        chk_p2 = tk.Checkbutton(sec_rigs, variable=self.var_poll_r2, bg="#252526", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#252526", activeforeground="#ffffff")
        chk_p2.grid(row=r_idx, column=1, sticky='w', padx=5, pady=4)

        # ----------------------------------------------------
        # SECTION 3: SDRconnect Integration
        # ----------------------------------------------------
        sec_sdr = tk.LabelFrame(self.container, text=" SDRconnect Integration ", bg="#252526", fg="#00ffcc", font=('Helvetica', 9, 'bold'), padx=10, pady=8)
        sec_sdr.pack(fill="x", pady=6)
        sec_sdr.grid_columnconfigure(1, weight=1)

        self.var_sdr_enabled = tk.BooleanVar(value=config.CONFIG.get("SDRCONNECT_ENABLED", False))
        lbl_sdr = tk.Label(sec_sdr, text="Enable WebSocket Sync:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_sdr.grid(row=0, column=0, sticky='e', padx=5, pady=4)
        chk_sdr = tk.Checkbutton(sec_sdr, variable=self.var_sdr_enabled, bg="#252526", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#252526", activeforeground="#ffffff")
        chk_sdr.grid(row=0, column=1, sticky='w', padx=5, pady=4)

        lbl_sdr_host = tk.Label(sec_sdr, text="WebSocket Host IP:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_sdr_host.grid(row=1, column=0, sticky='e', padx=5, pady=4)
        self.ent_sdr_host = tk.Entry(sec_sdr, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
        self.ent_sdr_host.insert(0, str(config.CONFIG.get("SDRCONNECT_HOST", "127.0.0.1")))
        self.ent_sdr_host.grid(row=1, column=1, sticky='ew', padx=5, pady=4)

        lbl_sdr_port = tk.Label(sec_sdr, text="WebSocket API Port:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_sdr_port.grid(row=2, column=0, sticky='e', padx=5, pady=4)
        self.ent_sdr_port = tk.Entry(sec_sdr, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
        self.ent_sdr_port.insert(0, str(config.CONFIG.get("SDRCONNECT_PORT", 5454)))
        self.ent_sdr_port.grid(row=2, column=1, sticky='ew', padx=5, pady=4)

        # ----------------------------------------------------
        # SECTION 4: WSJT-X Network Receiver Link
        # ----------------------------------------------------
        sec_wsjtx = tk.LabelFrame(self.container, text=" WSJT-X / FT8 Receiver Link ", bg="#252526", fg="#00ffcc", font=('Helvetica', 9, 'bold'), padx=10, pady=8)
        sec_wsjtx.pack(fill="x", pady=6)
        sec_wsjtx.grid_columnconfigure(1, weight=1)

        self.var_wsjtx_enabled = tk.BooleanVar(value=config.CONFIG.get("WSJTX_ENABLE", True))
        lbl_ws_enable = tk.Label(sec_wsjtx, text="Enable WSJT-X Listener:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_ws_enable.grid(row=0, column=0, sticky='e', padx=5, pady=4)
        chk_ws = tk.Checkbutton(sec_wsjtx, variable=self.var_wsjtx_enabled, bg="#252526", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#252526", activeforeground="#ffffff")
        chk_ws.grid(row=0, column=1, sticky='w', padx=5, pady=4)

        lbl_wsjtx_mode = tk.Label(sec_wsjtx, text="Network Mode:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_wsjtx_mode.grid(row=1, column=0, sticky='e', padx=5, pady=4)
        self.combo_dialog_mode = ttk.Combobox(sec_wsjtx, values=["Multicast", "Unicast"], state="readonly", width=12)
        self.combo_dialog_mode.set(config.CONFIG.get("WSJTX_MODE", "Multicast"))
        self.combo_dialog_mode.grid(row=1, column=1, sticky='w', padx=5, pady=4)

        lbl_wsjtx_ip = tk.Label(sec_wsjtx, text="WSJT-X IP Address:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_wsjtx_ip.grid(row=2, column=0, sticky='e', padx=5, pady=4)
        self.ent_dialog_ip = tk.Entry(sec_wsjtx, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
        self.ent_dialog_ip.insert(0, str(config.CONFIG.get("WSJTX_IP", "224.0.0.1")))
        self.ent_dialog_ip.grid(row=2, column=1, sticky='ew', padx=5, pady=4)

        lbl_wsjtx_port = tk.Label(sec_wsjtx, text="UDP Listener Port:", bg="#252526", fg="#ffffff", font=('Helvetica', 9))
        lbl_wsjtx_port.grid(row=3, column=0, sticky='e', padx=5, pady=4)
        self.ent_dialog_port = tk.Entry(sec_wsjtx, bg="#1e1e1e", fg="#ffffff", insertbackground='white', relief='flat', font=('Consolas', 9))
        self.ent_dialog_port.insert(0, str(config.CONFIG.get("WSJTX_PORT", 2237)))
        self.ent_dialog_port.grid(row=3, column=1, sticky='ew', padx=5, pady=4)

        # Action Control Panel (Save / Cancel)
        btn_frame = tk.Frame(self.container, bg="#252526")
        btn_frame.pack(fill='x', pady=(15, 5))
        
        btn_save = tk.Button(btn_frame, text="Save Parameters", bg="#007acc", fg="white", font=('Helvetica', 9, 'bold'), relief='flat', width=15, command=self.save_settings)
        btn_save.pack(side='right', padx=5)
        
        btn_cancel = tk.Button(btn_frame, text="Cancel", bg="#3c3c3c", fg="white", font=('Helvetica', 9), relief='flat', width=10, command=self.destroy)
        btn_cancel.pack(side='right', padx=5)

    def save_settings(self):
        try:
            p1 = int(self.entries["PORT_RADIO_1"].get())
            p2 = int(self.entries["PORT_RADIO_2"].get())
            tol = int(self.entries["FREQ_TOLERANCE"].get())
            w_max = int(self.entries["WAVELOG_MAX_INTERVAL"].get())
            sdr_port = int(self.ent_sdr_port.get())
            ws_port = int(self.ent_dialog_port.get() or 2237)
            
            config.CONFIG["FLDIGI_URL"] = self.entries["FLDIGI_URL"].get().strip()
            config.CONFIG["FORCE_MODE_SELECTION"] = self.entries["FORCE_MODE_SELECTION"].get().strip()
            config.CONFIG["WAVELOG_URL"] = self.entries["WAVELOG_URL"].get().strip()
            config.CONFIG["WAVELOG_API_KEY"] = self.entries["WAVELOG_API_KEY"].get().strip()
            config.CONFIG["RADIO_1_NAME"] = self.entries["RADIO_1_NAME"].get().strip()
            config.CONFIG["RADIO_2_NAME"] = self.entries["RADIO_2_NAME"].get().strip()
            config.CONFIG["PORT_RADIO_1"] = p1
            config.CONFIG["PORT_RADIO_2"] = p2
            config.CONFIG["FREQ_TOLERANCE"] = tol
            config.CONFIG["WAVELOG_MAX_INTERVAL"] = w_max
            config.CONFIG["START_POLL_RIG_1"] = self.var_poll_r1.get()
            config.CONFIG["START_POLL_RIG_2"] = self.var_poll_r2.get()
            
            config.CONFIG["SDRCONNECT_ENABLED"] = self.var_sdr_enabled.get()
            config.CONFIG["SDRCONNECT_HOST"] = self.ent_sdr_host.get().strip()
            config.CONFIG["SDRCONNECT_PORT"] = sdr_port

            # Save WSJT-X parameters from rearranged section
            config.CONFIG["WSJTX_ENABLE"] = self.var_wsjtx_enabled.get()
            config.CONFIG["WSJTX_MODE"] = self.combo_dialog_mode.get()
            config.CONFIG["WSJTX_IP"] = self.ent_dialog_ip.get().strip()
            config.CONFIG["WSJTX_PORT"] = ws_port

            self.master.update_labels_from_config()
            config.fldigi_blackout_until = time.time() + 1.0
            config.save_config()
            
            config.ui_print("⚙️ Configuration maps updated and saved to config.json.")
            self.destroy()
        except ValueError:
            messagebox.showerror("Validation Error", "Ports, Tolerance, and Durations must be valid integers.")


class BridgeGUIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OmniRig - Fldigi - Wavelog Configurable Bridge")
        self.geometry("820x680")
        self.configure(bg="#1e1e1e")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Base UI Theme Color definitions
        self.style.configure('.', background='#1e1e1e', foreground='#ffffff')
        self.style.configure('TLabelframe', background='#1e1e1e', foreground='#ffffff', bordercolor='#333333')
        self.style.configure('TLabelframe.Label', background='#1e1e1e', foreground='#00ffcc', font=('Helvetica', 10, 'bold'))
        
        # High Contrast Dropdown Field Configurations (Ensuring dark background and white text when NOT active/selected)
        self.style.configure('TCombobox', 
                             fieldbackground='#121212', 
                             background='#252526', 
                             foreground='#ffffff',
                             arrowcolor='#ffffff')
        self.style.map('TCombobox', 
                       fieldbackground=[('readonly', '#121212'), ('disabled', '#222222')],
                       foreground=[('readonly', '#ffffff'), ('disabled', '#777777')])
        
        # Setup contrasting fallback colors for combobox popup list boxes globally
        self.option_add('*TCombobox*Listbox.background', '#121212')
        self.option_add('*TCombobox*Listbox.foreground', '#ffffff')
        self.option_add('*TCombobox*Listbox.selectBackground', '#007acc')
        self.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        
        config._app_instance = self
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.sync_polling_buttons_to_state()
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

        self.canvas_r1_hw = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_r1_hw.grid(row=0, column=0, padx=8, pady=4)
        self.lbl_r1_hw = tk.Label(status_lf, text="Rig 1 Comm: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_r1_hw.grid(row=0, column=1, sticky='w', padx=2)

        self.canvas_r2_hw = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_r2_hw.grid(row=1, column=0, padx=8, pady=4)
        self.lbl_r2_hw = tk.Label(status_lf, text="Rig 2 Comm: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_r2_hw.grid(row=1, column=1, sticky='w', padx=2)

        self.canvas_fldigi = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_fldigi.grid(row=2, column=0, padx=8, pady=4)
        self.lbl_fldigi = tk.Label(status_lf, text="Fldigi Link: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_fldigi.grid(row=2, column=1, sticky='w', padx=2)

        self.canvas_wave = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_wave.grid(row=3, column=0, padx=8, pady=4)
        self.lbl_wave = tk.Label(status_lf, text="Wavelog Cloud: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_wave.grid(row=3, column=1, sticky='w', padx=2)

        self.canvas_sdr = tk.Canvas(status_lf, width=12, height=12, bg="#1e1e1e", highlightthickness=0)
        self.canvas_sdr.grid(row=4, column=0, padx=8, pady=4)
        self.lbl_sdr_status = tk.Label(status_lf, text="SDRconnect Link: Offline", bg="#1e1e1e", fg="#aaaaaa", font=('Helvetica', 9))
        self.lbl_sdr_status.grid(row=4, column=1, sticky='w', padx=2)

        ops_lf = ttk.LabelFrame(sys_frame, text=" ROUTING & UTILITIES ")
        ops_lf.pack(side='right', fill='both', padx=5, pady=5, expand=True)
        
        target_container = tk.Frame(ops_lf, bg="#1e1e1e")
        target_container.pack(fill='x', padx=10, pady=6)
        
        lbl_target = tk.Label(target_container, text="Fldigi Target Rig:", bg="#1e1e1e", fg="#ffffff", font=('Helvetica', 9, 'bold'))
        lbl_target.pack(side='left', padx=5)
        
        self.combo_target = ttk.Combobox(target_container, state="readonly", width=25)
        self.combo_target.pack(side='left', padx=5)
        self.combo_target.bind("<<ComboboxSelected>>", self.on_fldigi_target_changed)
        
        sdr_target_container = tk.Frame(ops_lf, bg="#1e1e1e")
        sdr_target_container.pack(fill='x', padx=10, pady=6)
        
        lbl_sdr_target = tk.Label(sdr_target_container, text="SDRconnect Target Rig:", bg="#1e1e1e", fg="#ffffff", font=('Helvetica', 9, 'bold'))
        lbl_sdr_target.pack(side='left', padx=5)
        
        self.combo_sdr_target = ttk.Combobox(sdr_target_container, state="readonly", width=25)
        self.combo_sdr_target.pack(side='left', padx=5)
        self.combo_sdr_target.bind("<<ComboboxSelected>>", self.on_sdrconnect_target_changed)

        # Dynamic utility grid row 1 (Legacy Configuration Buttons)
        btn_row_one = tk.Frame(ops_lf, bg="#1e1e1e")
        btn_row_one.pack(fill='x', padx=10, pady=(4, 2))

        btn_options = tk.Button(btn_row_one, text="⚙️ Options", bg="#3a3a3a", fg="white",
                                font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                command=self.open_options_dialog)
        btn_options.pack(side='left', expand=True, fill='x', padx=2)

        btn_omni_settings = tk.Button(btn_row_one, text="📻 Omnirig Setup", bg="#3a3a3a", fg="white",
                                      font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                      command=self.open_omnirig_dialog)
        btn_omni_settings.pack(side='left', expand=True, fill='x', padx=2)

        # Dynamic utility grid row 2 (Integration Control Buttons)
        btn_row_two = tk.Frame(ops_lf, bg="#1e1e1e")
        btn_row_two.pack(fill='x', padx=10, pady=(2, 6))

        # Configured identical heights and packing states to make buttons the exact same size
        self.btn_toggle_omni = tk.Button(btn_row_two, text="🟢 OmniRig: Enabled", bg="#1b5e20", fg="white",
                                         font=('Helvetica', 9, 'bold'), relief='flat', overrelief='groove',
                                         height=1, command=self.toggle_omnirig_global)
        self.btn_toggle_omni.pack(side='left', expand=True, fill='both', padx=2)

        # Browser Link Button matches OmniRig button size parameters completely
        self.btn_send_toggle = tk.Button(
            btn_row_two,
            font=("Helvetica", 9, "bold"),
            command=self.toggle_browser_sharing,
            relief="flat",
            bd=0,
            overrelief='groove',
            height=1
        )
        self.btn_send_toggle.pack(side='left', expand=True, fill='both', padx=2)
        self.update_browser_toggle_visuals()

        # Rig Cards Section
        cards_frame = tk.Frame(self, bg="#1e1e1e")
        cards_frame.pack(fill='x', padx=15, pady=5)

        self.rig1_lf = ttk.LabelFrame(cards_frame, text=" RIG 1 ")
        self.rig1_lf.pack(side='left', fill='both', expand=True, padx=5, pady=5)

        self.lbl_r1_freq = tk.Label(self.rig1_lf, text="0.000.000 MHz", font=('Courier New', 16, 'bold'), bg="#1e1e1e", fg="#ffffff")
        self.lbl_r1_freq.pack(pady=8)
        self.lbl_r1_freq_b = tk.Label(self.rig1_lf, text="VFO-B / Sub: --", font=('Courier New', 10), bg="#1e1e1e", fg="#888888")
        self.lbl_r1_freq_b.pack(pady=2)
        self.lbl_r1_mode = tk.Label(self.rig1_lf, text="MODE: --", font=('Helvetica', 10), bg="#1e1e1e", fg="#aaaaaa")
        self.lbl_r1_mode.pack(pady=4)
        
        self.btn_poll_r1 = tk.Button(self.rig1_lf, text="Polling: Active", bg="#1b5e20", fg="white", 
                                     font=('Helvetica', 8, 'bold'), relief='flat', command=lambda: self.toggle_rig_polling(1))
        self.btn_poll_r1.pack(pady=6)

        self.rig2_lf = ttk.LabelFrame(cards_frame, text=" RIG 2 ")
        self.rig2_lf.pack(side='right', fill='both', expand=True, padx=5, pady=5)

        self.lbl_r2_freq = tk.Label(self.rig2_lf, text="0.000.000 MHz", font=('Courier New', 16, 'bold'), bg="#1e1e1e", fg="#ffffff")
        self.lbl_r2_freq.pack(pady=8)
        self.lbl_r2_freq_b = tk.Label(self.rig2_lf, text="VFO-B / Sub: --", font=('Courier New', 10), bg="#1e1e1e", fg="#888888")
        self.lbl_r2_freq_b.pack(pady=2)
        self.lbl_r2_mode = tk.Label(self.rig2_lf, text="MODE: --", font=('Helvetica', 10), bg="#1e1e1e", fg="#aaaaaa")
        self.lbl_r2_mode.pack(pady=4)
        
        self.btn_poll_r2 = tk.Button(self.rig2_lf, text="Polling: Active", bg="#1b5e20", fg="white", 
                                     font=('Helvetica', 8, 'bold'), relief='flat', command=lambda: self.toggle_rig_polling(2))
        self.btn_poll_r2.pack(pady=6)

        # Logging View Panel
        log_lf = ttk.LabelFrame(self, text=" LIVE SYSTEM ACTIVITY LOG ")
        log_lf.pack(fill='both', expand=True, padx=15, pady=10)
        self.log_area = scrolledtext.ScrolledText(log_lf, wrap=tk.WORD, height=10, bg="#111111", fg="#33ff33", font=('Consolas', 9), insertbackground='white')
        self.log_area.pack(fill='both', expand=True, padx=5, pady=5)

        self.update_labels_from_config()

    def toggle_browser_sharing(self):
        """Toggles the pipeline of packet payloads streaming out to Wavelog's Tampermonkey bridge."""
        is_sharing = config.CONFIG.get("SEND_TO_BROWSER", True)
        config.CONFIG["SEND_TO_BROWSER"] = not is_sharing
        config.save_config()
        self.update_browser_toggle_visuals()

    def update_browser_toggle_visuals(self):
        """Redraws the quick-switch button to accurately match configuration memory."""
        is_sharing = config.CONFIG.get("SEND_TO_BROWSER", True)
        if is_sharing:
            self.btn_send_toggle.config(
                text="🟢 Browser Link: ACTIVE", 
                bg="#1b5e20", 
                fg="white", 
                activebackground="#1b5e20"
            )
            config.ui_print("📡 Sending packets dynamically to active browser session enabled.")
        else:
            self.btn_send_toggle.config(
                text="🔴 Browser Link: PAUSED", 
                bg="#b71c1c", 
                fg="white", 
                activebackground="#b71c1c"
            )
            config.ui_print("⏸️ Paused packet pipeline to Browser extension.")

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
        self.rig1_lf.config(text=f" RIG 1: {config.CONFIG.get('RADIO_1_NAME', 'Rig 1')} " + ("[FLDIGI TARGET]" if config.current_fldigi_target_rig == 1 else ""))
        self.rig2_lf.config(text=f" RIG 2: {config.CONFIG.get('RADIO_2_NAME', 'Rig 2')} " + ("[FLDIGI TARGET]" if config.current_fldigi_target_rig == 2 else ""))
        
        r1_val = f"Rig 1: {config.CONFIG.get('RADIO_1_NAME', 'Rig 1')}"
        r2_val = f"Rig 2: {config.CONFIG.get('RADIO_2_NAME', 'Rig 2')}"
        
        self.combo_target['values'] = [r1_val, r2_val]
        self.combo_target.set(r1_val if config.current_fldigi_target_rig == 1 else r2_val)

        self.combo_sdr_target['values'] = [r1_val, r2_val]
        self.combo_sdr_target.set(r1_val if config.current_sdrconnect_target_rig == 1 else r2_val)

    def sync_polling_buttons_to_state(self):
        for num in (1, 2):
            btn = self.btn_poll_r1 if num == 1 else self.btn_poll_r2
            if config.rig_polling_enabled[num]:
                btn.config(text="Polling: Active", bg="#1b5e20")
            else:
                btn.config(text="Polling: Paused", bg="#b71c1c")

    def toggle_rig_polling(self, rig_num):
        config.rig_polling_enabled[rig_num] = not config.rig_polling_enabled[rig_num]
        btn = self.btn_poll_r1 if rig_num == 1 else self.btn_poll_r2
        if config.rig_polling_enabled[rig_num]:
            btn.config(text="Polling: Active", bg="#1b5e20")
            config.ui_print(f"📡 Polling loop for Rig {rig_num} ENABLED.")
        else:
            btn.config(text="Polling: Paused", bg="#b71c1c")
            config.ui_print(f"🛑 Polling loop for Rig {rig_num} PAUSED.")

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
        
        if freq_to_push > 0 and config.status_states[f"rig{target_rig}_hw"] == "online":
            config.ui_print(f"🔄 Sync Target Shifted: Immediately sending Rig {target_rig} VFO ({freq_to_push} Hz) to Fldigi...")
            threading.Thread(target=network_workers.sync_to_fldigi, args=(freq_to_push, friendly_mode), daemon=True).start()
            
            if config.CONFIG.get("SDRCONNECT_ENABLED", False):
                import sdrconnect_worker
                threading.Thread(target=sdrconnect_worker.sync_to_sdrconnect, args=(freq_to_push, friendly_mode), daemon=True).start()
    
    def on_sdrconnect_target_changed(self, event):
        val = self.combo_sdr_target.get()
        config.current_sdrconnect_target_rig = 1 if val.startswith("Rig 1") else 2
        config.ui_print(f"🎯 SDRconnect sync target route changed to: Rig {config.current_sdrconnect_target_rig}")
        
        target_rig = config.current_sdrconnect_target_rig
        freq_to_push = config.last_freqs[target_rig]
        mode_code = config.last_modes[target_rig]
        friendly_mode = config.OMNIRIG_MODES.get(mode_code, "USB")
        
        if freq_to_push > 0 and config.status_states[f"rig{target_rig}_hw"] == "online":
            if config.CONFIG.get("SDRCONNECT_ENABLED", False):
                config.ui_print(f"🔄 Sync Target Shifted: Immediately sending Rig {target_rig} VFO ({freq_to_push} Hz) to SDRconnect...")
                threading.Thread(target=sdrconnect_worker.sync_to_sdrconnect, args=(freq_to_push, friendly_mode), daemon=True).start()

    def draw_status_dot(self, canvas, color):
        canvas.delete("all")
        canvas.create_oval(2, 2, 10, 10, fill=color, outline="#333333")

    def log_message(self, message):
        def append():
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
        self.after(0, append)

    def update_gui_indicators(self):
        sdr_status = config.status_states.get("sdrconnect", "offline")
        is_sdr_active = config.CONFIG.get("SDRCONNECT_ENABLED", False)

        sdr_color = "#555555" if not is_sdr_active else ("#00ff00" if sdr_status == "online" else "#ff0000")
        
        def get_color_for_state(state, is_enabled):
            if not is_enabled: return "#555555"          
            if state == "online": return "#00ff00"       
            if state == "not_responding": return "#ff9900" 
            return "#ff0000"                             
            
        self.draw_status_dot(self.canvas_sdr, sdr_color)
        self.lbl_sdr_status.config(
            text="SDRconnect: Active" if sdr_status == "online" and is_sdr_active else ("SDRconnect: Offline" if is_sdr_active else "SDRconnect: Disabled"),
            fg="#ffffff" if sdr_status == "online" and is_sdr_active else "#777777"
        )

        # Rig 1 rendering details
        if config.rig_polling_enabled[1]:
            if config.status_states["rig1_hw"] == "not_responding":
                self.lbl_r1_freq.config(text="NO RESPONSE", fg="#ff9900")
                self.lbl_r1_mode.config(text="STATUS: RigNotReady")
            elif config.status_states["rig1_hw"] == "online":
                f1, f1_b = config.last_freqs[1], config.last_freqs_b[1]
                m1 = config.OMNIRIG_MODES.get(config.last_modes[1], "--") if config.last_modes[1] else "--"
                self.lbl_r1_freq.config(text=f"{f1 / 1_000_000:,.6f} MHz" if f1 > 0 else "0.000.000 MHz", fg="#ffffff")
                self.lbl_r1_mode.config(text=f"MODE: {m1}")
                self.lbl_r1_freq_b.config(text=f"VFO-B: {f1_b / 1_000_000:,.6f} MHz" if f1_b > 0 else "VFO-B: --", fg="#00ffcc" if f1_b > 0 else "#aaaaaa")
            else:
                self.lbl_r1_freq.config(text="OFFLINE", fg="#ff4444")
                self.lbl_r1_mode.config(text="MODE: --")
        else:
            self.lbl_r1_freq.config(text="PAUSED", fg="#777777")
            self.lbl_r1_freq_b.config(text="VFO-B: --", fg="#555555")
            self.lbl_r1_mode.config(text="MODE: --")

        # Rig 2 rendering details
        if config.rig_polling_enabled[2]:
            if config.status_states["rig2_hw"] == "not_responding":
                self.lbl_r2_freq.config(text="NO RESPONSE", fg="#ff9900")
                self.lbl_r2_mode.config(text="STATUS: RigNotReady")
            elif config.status_states["rig2_hw"] == "online":
                f2, f2_b = config.last_freqs[2], config.last_freqs_b[2]
                m2 = config.OMNIRIG_MODES.get(config.last_modes[2], "--") if config.last_modes[2] else "--"
                self.lbl_r2_freq.config(text=f"{f2 / 1_000_000:,.6f} MHz" if f2 > 0 else "0.000.000 MHz", fg="#ffffff")
                self.lbl_r2_mode.config(text=f"MODE: {m2}")
                self.lbl_r2_freq_b.config(text=f"VFO-B: {f2_b / 1_000_000:,.6f} MHz" if f2_b > 0 else "VFO-B: --", fg="#00ffcc" if f2_b > 0 else "#aaaaaa")
            else:
                self.lbl_r2_freq.config(text="OFFLINE", fg="#ff4444")
                self.lbl_r2_mode.config(text="MODE: --")
        else:
            self.lbl_r2_freq.config(text="PAUSED", fg="#777777")
            self.lbl_r2_freq_b.config(text="VFO-B: --", fg="#555555")
            self.lbl_r2_mode.config(text="MODE: --")

        r1_st = config.status_states["rig1_hw"]
        self.draw_status_dot(self.canvas_r1_hw, get_color_for_state(r1_st, config.rig_polling_enabled[1]))
        if not config.rig_polling_enabled[1]:
            self.lbl_r1_hw.config(text="Rig 1: Disabled", fg="#777777")
        else:
            r1_lbl_text = f"Rig 1: Ready" if r1_st == "online" else (f"Rig 1: No Response" if r1_st == "not_responding" else "Rig 1: Offline")
            self.lbl_r1_hw.config(text=r1_lbl_text, fg="#ffffff" if r1_st == "online" else ("#ffaa33" if r1_st == "not_responding" else "#ff8888"))

        r2_st = config.status_states["rig2_hw"]
        self.draw_status_dot(self.canvas_r2_hw, get_color_for_state(r2_st, config.rig_polling_enabled[2]))
        if not config.rig_polling_enabled[2]:
            self.lbl_r2_hw.config(text="Rig 2: Disabled", fg="#777777")
        else:
            r2_lbl_text = f"Rig 2: Ready" if r2_st == "online" else (f"Rig 2: No Response" if r2_st == "not_responding" else "Rig 2: Offline")
            self.lbl_r2_hw.config(text=r2_lbl_text, fg="#ffffff" if r2_st == "online" else ("#ffaa33" if r2_st == "not_responding" else "#ff8888"))

        self.draw_status_dot(self.canvas_fldigi, "#00ff00" if config.status_states["fldigi"] == "online" else "#ff0000")
        self.lbl_fldigi.config(text="Fldigi Link: Active" if config.status_states["fldigi"] == "online" else "Fldigi Link: Offline", fg="#ffffff" if config.status_states["fldigi"] == "online" else "#ff8888")

        self.draw_status_dot(self.canvas_wave, "#00ff00" if config.status_states["wavelog"] == "online" else "#ff0000")
        self.lbl_wave.config(text="Wavelog Cloud: Connected" if config.status_states["wavelog"] == "online" else "Wavelog Cloud: Offline", fg="#ffffff" if config.status_states["wavelog"] == "online" else "#ff8888")

        self.after(200, self.update_gui_indicators)

    def on_close(self): 
        self.destroy()
        import sys
        sys.exit(0)