# **OmniRig \- Fldigi \- Wavelog Advanced Bridge**

An advanced, asynchronous multi-rig transceiver integration bridge. This suite synchronizes physical radio transceivers via OmniRig with both **Fldigi** (via XML-RPC) and **Wavelog** logging software (via Web API and inbound local TCP listeners), featuring a modern dark-mode Tkinter GUI for live tracking, routing selection, and dynamic parameter overrides.

## **📡 Features**

* **Asynchronous Dual-Rig Control**: Independently track or command two separate radios (e.g., Rig 1 and Rig 2\) concurrently.  
* **Dynamic Routing Control**: Route Fldigi click captures and waterfall tunings to either Rig on the fly using the GUI drop-down.  
* **Bi-directional Sync Engine**:  
  * Physical radio dial movements sync seamlessly with Fldigi and report directly to Wavelog cloud stations.  
  * Fldigi waterfall clicks command the active target transceiver.  
  * Inbound local TCP commands (e.g., from Wavelog Web UI click-to-tune features) route instantly to the appropriate hardware transceiver.  
* **Hot-Swapping Sockets**: Change TCP ports or timing frequencies in the GUI "Options" dialog, and backend listener sockets will automatically recycle and re-bind without requiring an application restart.  
* **Native Configuration Access**: One-click access to launch OmniRig's native hardware, COM port, and baud rate setup panels right from the bridge utilities interface.  
* **Safety Overrides**: Built-in process termination controls ("Kill OmniRig") to easily clear hung COM engine states.

## **📂 Project Architecture**

The monolith codebase has been split into an clean, extensible multi-file structure:

Plaintext  
├── config.py           \# Shared state maps, configuration parameters, and constants  
├── gui\_app.py          \# Tkinter core frontend, dashboard rendering, and settings modals  
├── omnirig\_engine.py   \# Windows Win32 COM worker loop interacting with OmniRigX  
├── network\_workers.py  \# Inbound TCP server listeners and Fldigi XML-RPC polling clients  
└── main.py             \# Main runtime orchestrator and bootstrapper thread manager

## **🛠️ Installation & Prerequisites**

### **1\. Requirements**

* **Operating System**: Windows (Required for OmniRig COM/OLE interaction via `pywin32`)  
* **Python**: 3.8+  
* Installed instance of **OmniRig** (configured for your specific transceivers)

### **2\. Dependencies**

Install the required packages using pip:
`pip install pywin32 requests`

### **3\. Setup**

Download all 5 files (`config.py`, `gui_app.py`, `omnirig_engine.py`, `network_workers.py`, and `main.py`) and place them together inside the **same directory**.

## **🚀 Usage**

Launch the bridge application: 
`python main.py`

### **Key GUI Actions:**

* **⚙️ Options...**: Opens a modal window to alter configuration values (API keys, target URLs, custom radio labels, frequency tolerances) permanently in memory for that runtime session.  
* **🔧 OmniRig Setup**: Spawns a background window invoking the standard native OmniRig interface where you change hardware-level settings like stop-bits, serial handshakes, or poll intervals.  
* **💥 Kill OmniRig**: Safely force-terminates `OmniRig.exe` processes via a system taskkill sequence to clean up locked serial links.

## **⚙️ Default Configurations**

The bridge spins up using these out-of-the-box defaults (customizable on-the-fly via the options panel):

* **Fldigi Endpoint**: `http://localhost:7362/`  
* **Default Rig Port 1 (Rig 1\)**: `54321` (Local TCP listener)  
* **Default Rig Port 2 (Rig 2\)**: `54322` (Local TCP listener)  
* **Frequency Sync Tolerance**: `10 Hz` *(Prevents recursive tuning loops between the physical VFO dial and digital waterfalls)*

## **🤝 Troubleshooting & Notes**

* **COM Engine Errors**: If the link light shows red for OmniRig, verify that OmniRig is installed on your machine and running as an Administrator if your software layer requires it.  
* **Port Conflicts**: If the activity log states that a TCP listener failed to bind, check that another application isn't already utilizing ports `54321` or `54322`, or map them to new ports via the Options menu.

