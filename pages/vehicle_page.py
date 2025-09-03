# pages/vehicle_page.py
# This is a comprehensive overhaul of the vehicle interface page, integrating features
# like a SQLite database for logging, vehicle profiles, trip management, and a custom alert system.

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass
import sqlite3

# --- Local Imports ---
from .db_manager import VehicleDBManager

# --- Conditional Library Imports ---
OBD_AVAILABLE = False
try:
    import obd
    from obd import Unit
    OBD_AVAILABLE = True
    obd.logger.setLevel(obd.logging.WARNING)
except (ImportError, ModuleNotFoundError):
    class obd:
        class OBD: pass
        class Async:
            def __init__(self, *args, **kwargs): pass
            def start(self): pass
            def stop(self): pass
            def close(self): pass
            def is_connected(self): return False
            def watch(self, *args, **kwargs): pass
            def unwatch(self, *args, **kwargs): pass
            def supports(self, *args, **kwargs): return False
            def query(self, *args, **kwargs): return self.OBDResponse()
        class commands:
            RPM, SPEED, COOLANT_TEMP, THROTTLE_POS, GET_DTC, CLEAR_DTC, VIN = (None,) * 7
        class OBDResponse:
            value = None
            def is_null(self): return True
    logging.getLogger(__name__).warning("python-obd library not found. Vehicle page functionality is disabled.")

SERIAL_AVAILABLE = False
try:
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    logging.getLogger(__name__).warning("pyserial library not found. Port scanning will be disabled.")

logger = logging.getLogger(__name__)

# --- UI Constants ---
PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME = "#2a2d2e"
MAIN_BG_COLOR = "#1a1a1a"
ERROR_COLOR = "#FF5500"
WARNING_COLOR = "#FFB000"
GAUGE_FONT_LARGE = ("Arial", 48, "bold")
GAUGE_FONT_SMALL = ("Arial", 12)

# --- Connection Parameters ---
CONNECTION_TIMEOUT_SECONDS = 20
LOG_UPDATE_INTERVAL_MS = 2000

# --- Data Structures ---
@dataclass
class OBDCommand:
    """A dataclass to hold information about an OBD-II command."""
    cmd: Any  # Using Any because the mock obd.commands are None
    name: str
    label: str
    unit: str

# --- Helper Classes ---
class GaugeWidget(ctk.CTkFrame):
    """A reusable widget to display a single vehicle statistic."""
    def __init__(self, parent: ctk.CTkFrame, label_text: str, unit_text: str):
        super().__init__(parent, fg_color=PIPBOY_FRAME, corner_radius=8)
        self.grid_columnconfigure(0, weight=1)
        self.value_label = ctk.CTkLabel(self, text="--", font=GAUGE_FONT_LARGE, text_color=PIPBOY_GREEN)
        self.value_label.grid(row=0, column=0, sticky="s", padx=10, pady=(10, 0))
        self.description_label = ctk.CTkLabel(self, text=f"{label_text} ({unit_text})", font=GAUGE_FONT_SMALL)
        self.description_label.grid(row=1, column=0, sticky="n", padx=10, pady=(0, 10))

    def update_value(self, value: Optional[Any], color: str = PIPBOY_GREEN) -> None:
        """Updates the displayed value and color of the gauge."""
        display_text = "--"
        if value is not None:
            try:
                val_float = float(value)
                display_text = f"{val_float:.0f}" if val_float == int(val_float) else f"{val_float:.1f}"
            except (ValueError, TypeError):
                display_text = str(value)
        self.value_label.configure(text=display_text, text_color=color)

class AlertManager:
    """Manages the checking and triggering of custom vehicle alerts."""
    def __init__(self, page: 'VehiclePage'):
        self.page = page
        self.rules: List[sqlite3.Row] = []
        self.active_alerts: set[int] = set()

    def load_rules(self) -> None:
        """Loads alert rules from the database for the current vehicle."""
        if self.page.current_vehicle_id:
            self.rules = self.page.db_manager.get_alert_rules(self.page.current_vehicle_id)
            logger.info(f"Loaded {len(self.rules)} alert rules for vehicle ID {self.page.current_vehicle_id}.")
        else:
            self.rules = []

    def check_value(self, command_name: str, response: 'obd.OBDResponse') -> None:
        """Checks a new OBD value against the loaded alert rules."""
        if response.is_null() or not self.page.is_logging_trip:
            return

        value = response.value.magnitude
        for rule in self.rules:
            if rule['command'] == command_name:
                rule_val = float(rule['value'])
                condition = rule['condition']
                is_triggered = False
                
                if condition == '>' and value > rule_val: is_triggered = True
                elif condition == '<' and value < rule_val: is_triggered = True
                elif condition == '=' and value == rule_val: is_triggered = True

                rule_id = rule['id']
                if is_triggered and rule_id not in self.active_alerts:
                    self.active_alerts.add(rule_id)
                    self.trigger_alert(rule, response)
                elif not is_triggered and rule_id in self.active_alerts:
                    self.active_alerts.remove(rule_id)
                    self.clear_alert(rule)

    def trigger_alert(self, rule: sqlite3.Row, response: 'obd.OBDResponse') -> None:
        """Handles a triggered alert: updates UI and logs to DB."""
        logger.warning(f"ALERT TRIGGERED: {rule['command']} {rule['condition']} {rule['value']}. Current value: {response.value}")
        self.page.db_manager.log_alert(self.page.current_trip_id, rule['id'], str(response.value))
        self.page.show_alert_banner(f"ALERT: {rule['command']} is {response.value.magnitude:.1f} {response.value.units}!", rule['severity'])

    def clear_alert(self, rule: sqlite3.Row) -> None:
        """Handles a cleared alert."""
        logger.info(f"Alert Cleared: {rule['command']}")
        self.page.hide_alert_banner()

    def reset(self) -> None:
        """Resets active alerts, typically on disconnect or trip end."""
        self.active_alerts.clear()
        self.page.hide_alert_banner()

class VehiclePage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, controller: Any):
        super().__init__(parent, fg_color=MAIN_BG_COLOR)
        self.controller = controller
        self.db_manager = VehicleDBManager(Path(controller.app_dir) / "vehicle_data.db")
        self.alert_manager = AlertManager(self)

        # State variables
        self.connection: Optional[obd.Async] = None
        self.is_connected = self.is_connecting = self.is_logging_trip = False
        self.available_ports: List[str] = []
        self.gauges: Dict[str, GaugeWidget] = {}
        self.vehicles: List[sqlite3.Row] = []
        self.current_vehicle_id: Optional[int] = None
        self.current_trip_id: Optional[int] = None
        self.log_update_job: Optional[str] = None
        
        # Supported Commands Config
        self.SUPPORTED_COMMANDS: List[OBDCommand] = [
            OBDCommand(cmd=obd.commands.RPM, name="RPM", label="Engine", unit="RPM"),
            OBDCommand(cmd=obd.commands.SPEED, name="SPEED", label="Speed", unit="KPH"),
            OBDCommand(cmd=obd.commands.COOLANT_TEMP, name="COOLANT_TEMP", label="Coolant", unit="°C"),
            OBDCommand(cmd=obd.commands.THROTTLE_POS, name="THROTTLE_POS", label="Throttle", unit="%"),
        ]

        # UI Setup
        self._setup_layout()
        self._setup_widgets()
        self.load_vehicle_profiles()
        self._update_ui_state()

    def _setup_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

    def _setup_widgets(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")
        header.columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="VEHICLE INTERFACE", font=("Arial", 24, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Back to Home", command=lambda: self.controller.show_page("HomePage")).grid(row=0, column=1, sticky="e")

        # Alert Banner (initially hidden)
        self.alert_banner = ctk.CTkLabel(self, text="", text_color="black", font=("Arial", 14, "bold"), fg_color=WARNING_COLOR)
        
        # Main Tab View
        self.tab_view = ctk.CTkTabview(self, fg_color=PIPBOY_FRAME)
        self.tab_view.add("Live Data")
        self.tab_view.add("Diagnostics & Alerts")
        self.tab_view.add("Data Logger")
        self.tab_view.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)

        self._setup_live_data_tab()
        self._setup_diagnostics_tab()
        self._setup_logger_tab()

    def _setup_live_data_tab(self):
        tab = self.tab_view.tab("Live Data")
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(2, weight=1)

        # Connection & Trip Controls Frame
        top_frame = ctk.CTkFrame(tab, fg_color="transparent")
        top_frame.grid(row=0, column=0, pady=5, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        self.scan_ports_button = ctk.CTkButton(top_frame, text="Scan Ports", width=100, command=self.scan_for_ports)
        self.scan_ports_button.grid(row=0, column=0, padx=(0, 5))
        self.port_dropdown_var = ctk.StringVar(value="No ports...")
        self.port_dropdown = ctk.CTkOptionMenu(top_frame, variable=self.port_dropdown_var, values=[])
        self.port_dropdown.grid(row=0, column=1, padx=5, sticky="ew")
        self.connect_button = ctk.CTkButton(top_frame, text="Connect", width=100, command=self.connect_to_obd)
        self.connect_button.grid(row=0, column=2, padx=(5, 0))
        self.disconnect_button = ctk.CTkButton(top_frame, text="Disconnect", width=100, fg_color=ERROR_COLOR, hover_color="#b33c00", command=self.disconnect_from_obd)

        # Vehicle Profile & Trip Frame
        trip_frame = ctk.CTkFrame(tab, fg_color="transparent")
        trip_frame.grid(row=1, column=0, pady=5, sticky="ew")
        trip_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(trip_frame, text="Vehicle Profile:").grid(row=0, column=0, padx=(0,5))
        self.vehicle_profile_var = ctk.StringVar(value="Select a vehicle...")
        self.vehicle_profile_dropdown = ctk.CTkOptionMenu(trip_frame, variable=self.vehicle_profile_var, command=self.on_vehicle_select)
        self.vehicle_profile_dropdown.grid(row=0, column=1, sticky="ew")
        self.trip_button = ctk.CTkButton(trip_frame, text="Start Trip", command=self.toggle_trip_logging, width=120)
        self.trip_button.grid(row=0, column=2, padx=10)
        
        # Status Label
        self.status_label = ctk.CTkLabel(tab, text="Status: INITIALIZING", text_color="orange")
        self.status_label.grid(row=2, column=0, pady=5)
        
        # Gauge Container
        self.gauge_container_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.gauge_container_frame.grid(row=3, column=0, sticky="nsew")
        self.gauge_container_frame.grid_columnconfigure((0, 1, 2), weight=1)

    def _setup_diagnostics_tab(self):
        tab = self.tab_view.tab("Diagnostics & Alerts")
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(1, weight=1)
        
        controls_frame = ctk.CTkFrame(tab, fg_color="transparent")
        controls_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        controls_frame.grid_columnconfigure((0, 1), weight=1)
        self.read_dtc_button = ctk.CTkButton(controls_frame, text="Read Trouble Codes (DTCs)", command=self.read_dtcs)
        self.read_dtc_button.grid(row=0, column=0, padx=5, sticky="ew")
        self.clear_dtc_button = ctk.CTkButton(controls_frame, text="Clear Trouble Codes", command=self.clear_dtcs, fg_color=ERROR_COLOR, hover_color="#b33c00")
        self.clear_dtc_button.grid(row=0, column=1, padx=5, sticky="ew")
        
        self.dtc_results_text = ctk.CTkTextbox(tab, font=("Arial", 12), wrap="word", state="disabled")
        self.dtc_results_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _setup_logger_tab(self):
        tab = self.tab_view.tab("Data Logger")
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(1, weight=1)
        
        log_controls_frame = ctk.CTkFrame(tab, fg_color="transparent")
        log_controls_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.export_button = ctk.CTkButton(log_controls_frame, text="Export Current Trip to CSV", command=self.export_trip)
        self.export_button.pack(side="left", padx=5)
        self.prune_button = ctk.CTkButton(log_controls_frame, text="Prune Data Older Than 30 Days", command=self.prune_data)
        self.prune_button.pack(side="left", padx=5)
        
        self.log_textbox = ctk.CTkTextbox(tab, font=("Monaco", 10), wrap="none", state="disabled")
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    # --- UI Update and State Management ---
    def _update_ui_state(self):
        # Master UI state controller based on connection and logging status
        if not OBD_AVAILABLE:
            self.status_label.configure(text="Status: python-obd library MISSING", text_color=ERROR_COLOR)
            # Disable almost everything
            return

        is_busy = self.is_connecting
        # Connection controls
        self.scan_ports_button.configure(state="disabled" if is_busy or self.is_connected else "normal")
        self.port_dropdown.configure(state="disabled" if is_busy or self.is_connected else "normal")
        self.connect_button.configure(state="disabled" if is_busy or self.is_connected or not self.available_ports else "normal")
        if self.is_connected: self.disconnect_button.grid(row=0, column=2, padx=(5,0))
        else: self.disconnect_button.grid_remove()

        # Profile and Trip controls
        self.vehicle_profile_dropdown.configure(state="disabled" if is_busy or self.is_connected else "normal")
        self.trip_button.configure(state="disabled" if not self.is_connected or is_busy else "normal")
        self.trip_button.configure(text="End Trip" if self.is_logging_trip else "Start Trip", 
                                   fg_color=ERROR_COLOR if self.is_logging_trip else ctk.ThemeManager.theme["CTkButton"]["fg_color"])

        # Diagnostics & Logging controls
        self.read_dtc_button.configure(state="disabled" if not self.is_connected or is_busy else "normal")
        self.clear_dtc_button.configure(state="disabled" if not self.is_connected or is_busy else "normal")
        self.export_button.configure(state="disabled" if not self.is_logging_trip else "normal")
        
        # Status Label
        if self.is_connecting: self.status_label.configure(text="Status: CONNECTING...", text_color=WARNING_COLOR)
        elif self.is_connected: self.status_label.configure(text=f"Status: CONNECTED{' | LOGGING ACTIVE' if self.is_logging_trip else ''}", text_color=PIPBOY_GREEN)
        else: self.status_label.configure(text="Status: DISCONNECTED", text_color=ERROR_COLOR)

    def on_show(self):
        if SERIAL_AVAILABLE: self.scan_for_ports()

    def on_hide(self):
        self._stop_log_updater()
        if self.is_logging_trip: self.toggle_trip_logging()
        self.disconnect_from_obd()
        self.db_manager.close()

    # --- Vehicle and Trip Management ---
    def load_vehicle_profiles(self):
        self.vehicles = self.db_manager.get_all_vehicles()
        if self.vehicles:
            names = [v['name'] for v in self.vehicles]
            self.vehicle_profile_dropdown.configure(values=names)
            self.vehicle_profile_var.set(names[0])
            self.on_vehicle_select(names[0])
        else:
            self.vehicle_profile_dropdown.configure(values=["No profiles found"])
            self.vehicle_profile_var.set("Add a profile via VIN")

    def on_vehicle_select(self, selection: str):
        vehicle = next((v for v in self.vehicles if v['name'] == selection), None)
        if vehicle:
            self.current_vehicle_id = vehicle['id']
            self.alert_manager.load_rules()
            logger.info(f"Selected vehicle: {selection} (ID: {self.current_vehicle_id})")

    def toggle_trip_logging(self):
        if not self.current_vehicle_id:
            messagebox.showwarning("No Vehicle", "Please select or create a vehicle profile first.", parent=self)
            return

        self.is_logging_trip = not self.is_logging_trip
        if self.is_logging_trip:
            self.current_trip_id = self.db_manager.start_trip(self.current_vehicle_id)
            self.tab_view.set("Data Logger")
            self.update_log_display()
            self._start_log_updater()
        else:
            self._stop_log_updater()
            if self.current_trip_id:
                self.db_manager.end_trip(self.current_trip_id)
            self.alert_manager.reset()
        self._update_ui_state()

    # --- OBD Connection Logic ---
    def scan_for_ports(self):
        logger.info("Scanning for serial ports...")
        ports = [p.device for p in serial.tools.list_ports.comports() if 'ttyUSB' in p.name or 'ttyACM' in p.name]
        self.available_ports = ports
        if ports:
            self.port_dropdown.configure(values=ports)
            self.port_dropdown_var.set(ports[0])
        else:
            self.port_dropdown.configure(values=["No ports found..."])
            self.port_dropdown_var.set("No ports found...")
        self._update_ui_state()
        
    def connect_to_obd(self):
        if self.is_connecting or self.is_connected: return
        selected_port = self.port_dropdown_var.get()
        if not selected_port or "No ports" in selected_port:
            messagebox.showerror("Error", "No valid port selected.", parent=self)
            return
        
        self.is_connecting = True
        self._update_ui_state()
        threading.Thread(target=self._obd_connection_thread, args=(selected_port,), daemon=True).start()

    def disconnect_from_obd(self):
        self._stop_log_updater()
        if self.is_logging_trip:
            self.toggle_trip_logging()
        if self.connection:
            if self.connection.is_connected():
                self.connection.stop()
            self.connection.close()
        self.connection = None
        self.is_connected = self.is_connecting = False
        self._clear_all_gauges()
        self.alert_manager.reset()
        self._update_ui_state()

    def _obd_connection_thread(self, port: str):
        try:
            self.connection = obd.Async(portstr=port, fast=False, timeout=CONNECTION_TIMEOUT_SECONDS)
            self.connection.start()
            if not self.connection.is_connected():
                raise ConnectionError("Failed to connect after start().")
            
            self.is_connected = True
            self.after(0, self.on_successful_connection)
        except Exception as e:
            logger.error(f"OBD connection failed: {e}", exc_info=True)
            self.after(0, lambda: messagebox.showerror("Connection Error", f"Failed: {e}", parent=self))
        finally:
            self.is_connecting = False
            self.after(0, self._update_ui_state)

    def on_successful_connection(self):
        """Called on the main thread after a connection is established."""
        # Attempt to get VIN to identify vehicle
        vin_resp = self.connection.query(obd.commands.VIN)
        if not vin_resp.is_null() and vin_resp.value:
            vin = vin_resp.value
            vehicle_id = self.db_manager.add_or_get_vehicle(vin, f"Vehicle-{vin[-4:]}")
            self.load_vehicle_profiles()
            vehicle = next((v for v in self.vehicles if v['id'] == vehicle_id), None)
            if vehicle:
                self.vehicle_profile_var.set(vehicle['name'])
                self.on_vehicle_select(vehicle['name'])
        
        self._create_dynamic_gauges()
        if self.current_vehicle_id:
            self.toggle_trip_logging()

    # --- Real-time Data Handling ---
    def _create_dynamic_gauges(self):
        max_cols, row, col = 3, 0, 0
        for cmd_info in self.SUPPORTED_COMMANDS:
            cmd_obj = cmd_info.cmd
            if self.connection.supports(cmd_obj):
                gauge = GaugeWidget(self.gauge_container_frame, cmd_info.label, cmd_info.unit)
                gauge.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                self.gauges[cmd_info.name] = gauge
                self.connection.watch(cmd_obj, callback=self.gauge_callback_factory(cmd_info))
                col += 1
                if col >= max_cols: col, row = 0, row + 1

    def gauge_callback_factory(self, cmd_info: OBDCommand) -> Callable:
        """Creates a callback that updates gauges, logs data, and checks alerts."""
        cmd_name, unit = cmd_info.name, cmd_info.unit
        def callback(response: obd.OBDResponse):
            if not response.is_null():
                self.after(0, self.gauges[cmd_name].update_value, response.value.magnitude)
                if self.is_logging_trip and self.current_trip_id:
                    self.db_manager.log_reading(self.current_trip_id, cmd_name, response.value.magnitude, unit)
                self.alert_manager.check_value(cmd_name, response)
        return callback

    def _clear_all_gauges(self):
        for cmd_info in self.SUPPORTED_COMMANDS:
            if self.connection and self.connection.is_connected():
                self.connection.unwatch(cmd_info.cmd)
        for widget in self.gauge_container_frame.winfo_children():
            widget.destroy()
        self.gauges.clear()

    # --- Diagnostics ---
    def read_dtcs(self):
        threading.Thread(target=self._diag_thread, args=(obd.commands.GET_DTC,), daemon=True).start()

    def clear_dtcs(self):
        if not messagebox.askyesno("Confirm", "Clear all DTCs and Check Engine Light?", parent=self): return
        threading.Thread(target=self._diag_thread, args=(obd.commands.CLEAR_DTC,), daemon=True).start()
    
    def _diag_thread(self, command):
        """Generic thread for DTC read/clear operations."""
        self.after(0, self._update_dtc_textbox, f"Querying ECU with {command.name}...\n")
        response = self.connection.query(command, force=True)
        if response.is_null():
            result_text = f"{command.name}: No data or command not supported.\n"
        elif command.name == "GET_DTC":
            result_text = "--- Found Trouble Codes ---\n" + "".join([f"- {c}: {d}\n" for c, d in response.value]) if response.value else "No trouble codes found.\n"
        else: # CLEAR_DTC
            result_text = f"{command.name}: Command sent. Response value: {response.value}\n"
        self.after(0, self._update_dtc_textbox, result_text, append=True)

    def _update_dtc_textbox(self, text: str, append: bool = False):
        self.dtc_results_text.configure(state="normal")
        if not append: self.dtc_results_text.delete("1.0", "end")
        self.dtc_results_text.insert("end", text)
        self.dtc_results_text.configure(state="disabled")

    # --- Data Logger Tab Functions ---
    def _start_log_updater(self):
        """Starts the periodic job to update the log display."""
        if self.log_update_job is not None:
            self.after_cancel(self.log_update_job)
        self.log_update_job = self.after(LOG_UPDATE_INTERVAL_MS, self._live_log_update)

    def _stop_log_updater(self):
        """Stops the periodic log update job."""
        if self.log_update_job is not None:
            self.after_cancel(self.log_update_job)
            self.log_update_job = None

    def _live_log_update(self):
        """The recurring method that calls the log display update and reschedules itself."""
        if self.is_logging_trip:
            self.update_log_display()
            self.log_update_job = self.after(LOG_UPDATE_INTERVAL_MS, self._live_log_update)
        else:
            self._stop_log_updater()

    def update_log_display(self):
        if not self.is_logging_trip or not self.current_trip_id: return
        readings = self.db_manager.get_trip_readings(self.current_trip_id)
        
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        header = f"{'Timestamp':<22}{'Command':<15}{'Value':<15}{'Unit':<10}\n"
        self.log_textbox.insert("1.0", header, ("header",))
        self.log_textbox.tag_config("header", font=("Monaco", 10, "bold"))

        for r in readings:
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['timestamp']))
            line = f"{ts:<22}{r['command']:<15}{r['value']:<15}{r.get('unit', ''):<10}\n"
            self.log_textbox.insert("end", line)
        self.log_textbox.configure(state="disabled")

    def export_trip(self):
        if not self.current_trip_id: return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save Trip Log As",
            initialfile=f"trip_{self.current_trip_id}.csv"
        )
        if not save_path: return
        
        success = self.db_manager.export_trip_to_csv(self.current_trip_id, Path(save_path))
        if success: messagebox.showinfo("Success", "Trip data exported successfully.", parent=self)
        else: messagebox.showerror("Error", "Failed to export trip data.", parent=self)

    def prune_data(self):
        if messagebox.askyesno("Confirm", "Delete all trip data older than 30 days? This cannot be undone.", parent=self):
            trips, readings = self.db_manager.prune_old_data(30)
            messagebox.showinfo("Pruning Complete", f"Removed {trips} old trips and {readings} readings.", parent=self)

    # --- Alert Banner ---
    def show_alert_banner(self, message: str, severity: str):
        color = ERROR_COLOR if severity == 'CRITICAL' else WARNING_COLOR
        self.alert_banner.configure(text=message, fg_color=color)
        self.alert_banner.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.alert_banner.tkraise()

    def hide_alert_banner(self):
        if not self.alert_manager.active_alerts:
            self.alert_banner.grid_remove()