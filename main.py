import threading
import config
import network_workers
import omnirig_engine
import gui_app
import sdrconnect_worker  # Ensure this is imported at the top

def start_background_subsystems():
    """Spins off processing thread workers once initialization ticks complete."""
    threading.Thread(target=omnirig_engine.omnirig_worker_thread, daemon=True).start()
    threading.Thread(target=network_workers.fldigi_polling_listener, daemon=True).start()
    threading.Thread(target=network_workers.parameterized_tcp_listener, args=(1,), daemon=True).start()
    threading.Thread(target=network_workers.parameterized_tcp_listener, args=(2,), daemon=True).start()
    
    # Run the new live monitoring connection monitor
    threading.Thread(target=sdrconnect_worker.sdrconnect_heartbeat_loop, daemon=True).start()
    
if __name__ == '__main__':
    # Initialize UI Window instance
    app = gui_app.BridgeGUIApp()
    
    # Store explicit connection hook for text viewport operations
    config._app_instance = app
    
    # Schedule workers to initiate asynchronously after first frame paint finishes
    app.after(1000, start_background_subsystems)
    
    # Execute primary UI run thread loop
    app.mainloop()

