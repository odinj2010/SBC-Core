import customtkinter as ctk
import psutil
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque
import numpy as np
import datetime
import logging
import platform
import subprocess
import os
from functools import lru_cache
from typing import Tuple
from .process_viewer import ProcessViewerWindow

logger = logging.getLogger(__name__)

# --- Configuration --
PIPBOY_GREEN = "#32f178"
PIPBOY_AMBER = "#FFB000"
PIPBOY_FRAME = "#2a2d2e"
MAX_GRAPH_POINTS = 50
UPDATE_INTERVAL_MS = 1000

DEFAULT_FONT = ("Arial", 11)
HEADER_FONT = ("Arial", 20, "bold")
SECTION_TITLE_FONT = ("Arial", 14, "bold")
MAIN_TITLE_FONT = ("Arial", 16, "bold")

# --- Helper Functions ---
@lru_cache(maxsize=1)
def get_static_system_info():
    os_version = f"{platform.system()} {platform.release()}"
    # lsb_release is a Linux-specific command
    if platform.system() == "Linux":
        try:
            lsb_info = subprocess.check_output(['lsb_release', '-ds'], stderr=subprocess.DEVNULL).decode().strip()
            os_version = lsb_info.replace('"', '')
        except (FileNotFoundError, subprocess.CalledProcessError):
            # If lsb_release fails, the generic version is still used
            pass
    return {
        "os": os_version,
        "arch": platform.machine(),
        "hostname": platform.node(),
        "boot_time": datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    }

def format_bytes(b):
    if b is None or b == 0: return "0 B"
    power, n = 1024, 0
    units = ("B", "K", "M", "G", "T")
    while b >= power and n < len(units) - 1:
        b /= power
        n += 1
    return f"{b:.1f}{units[n]}"

def get_cpu_temperature_psutil():
    if hasattr(psutil, "sensors_temperatures"):
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps:
            # On some systems, coretemp might have multiple entries
            return temps['coretemp'][0].current
        if 'cpu_thermal' in temps:
            # Common on Raspberry Pi
            return temps['cpu_thermal'][0].current
    return float('nan')

class StatusPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="#1a1a1a")
        self.controller = controller
        self.after_id = None
        self.cpu_data = deque([0] * MAX_GRAPH_POINTS, maxlen=MAX_GRAPH_POINTS)
        self.ram_data = deque([0] * MAX_GRAPH_POINTS, maxlen=MAX_GRAPH_POINTS)
        self.setup_ui()
        self.update_all_info()

    def on_show(self):
        self.update_all_info()

    def on_hide(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        right_frame = ctk.CTkFrame(self, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left_frame, text="SYSTEM STATUS", font=HEADER_FONT, text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.setup_graphs(left_frame)
        ctk.CTkLabel(right_frame, text="DETAILS", font=HEADER_FONT, text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.setup_details(right_frame)

    def setup_graphs(self, parent):
        graph_frame = ctk.CTkFrame(parent, fg_color=PIPBOY_FRAME)
        graph_frame.grid(row=1, column=0, sticky="nsew")
        graph_frame.grid_rowconfigure((0, 1), weight=1)
        graph_frame.grid_columnconfigure(0, weight=1)

        plt.style.use('dark_background')
        fig_cpu, self.ax_cpu = plt.subplots()
        fig_ram, self.ax_ram = plt.subplots()
        self.setup_ax(self.ax_cpu, "CPU Usage (%)")
        self.setup_ax(self.ax_ram, "RAM Usage (%)")
        
        self.line_cpu, = self.ax_cpu.plot(self.cpu_data, color=PIPBOY_GREEN)
        self.line_ram, = self.ax_ram.plot(self.ram_data, color=PIPBOY_AMBER)

        canvas_cpu = FigureCanvasTkAgg(fig_cpu, master=graph_frame)
        canvas_cpu.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        canvas_ram = FigureCanvasTkAgg(fig_ram, master=graph_frame)
        canvas_ram.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        canvas_cpu.draw()
        canvas_ram.draw()

    def setup_ax(self, ax, title):
        ax.set_title(title, color=PIPBOY_GREEN, fontdict={'family': 'Arial', 'size': 12})
        ax.set_ylim(0, 100)
        ax.set_xlim(0, MAX_GRAPH_POINTS)
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.grid(True, color=PIPBOY_GREEN, linestyle='--', linewidth=0.5, alpha=0.3)
        for spine in ax.spines.values():
            spine.set_edgecolor(PIPBOY_GREEN)

    def setup_details(self, parent):
        details_frame = ctk.CTkFrame(parent, fg_color=PIPBOY_FRAME)
        details_frame.grid(row=1, column=0, sticky="nsew")
        details_frame.grid_columnconfigure(0, weight=1)
        
        static_info = get_static_system_info()
        info_map = {
            "OS": static_info["os"], "Arch": static_info["arch"],
            "Hostname": static_info["hostname"], "Boot Time": static_info["boot_time"]
        }
        for i, (key, val) in enumerate(info_map.items()):
            ctk.CTkLabel(details_frame, text=f"{key}: {val}", font=DEFAULT_FONT, anchor="w").grid(row=i, column=0, sticky="ew", padx=10, pady=2)

        self.cpu_load = ctk.CTkLabel(details_frame, text="Load: -", font=DEFAULT_FONT, anchor="w")
        self.cpu_load.grid(row=len(info_map), column=0, sticky="ew", padx=10, pady=2)
        self.cpu_temp = ctk.CTkLabel(details_frame, text="Temp: -", font=DEFAULT_FONT, anchor="w")
        self.cpu_temp.grid(row=len(info_map)+1, column=0, sticky="ew", padx=10, pady=2)
        self.mem_ram = ctk.CTkLabel(details_frame, text="RAM: -", font=DEFAULT_FONT, anchor="w")
        self.mem_ram.grid(row=len(info_map)+2, column=0, sticky="ew", padx=10, pady=2)
        self.disk_usage = ctk.CTkLabel(details_frame, text="Disk: -", font=DEFAULT_FONT, anchor="w")
        self.disk_usage.grid(row=len(info_map)+3, column=0, sticky="ew", padx=10, pady=2)
        self.disk_io = ctk.CTkLabel(details_frame, text="I/O: -", font=DEFAULT_FONT, anchor="w")
        self.disk_io.grid(row=len(info_map)+4, column=0, sticky="ew", padx=10, pady=2)

        # Buttons
        button_row_start = len(info_map) + 5
        ctk.CTkButton(details_frame, text="View Running Processes", command=self.show_process_viewer).grid(row=button_row_start, column=0, pady=(20, 5), padx=10)
        
        ctk.CTkButton(details_frame, text="Back to Main Menu", command=lambda: self.controller.show_page("HomePage")).grid(row=button_row_start + 1, column=0, pady=(5, 10), padx=10)

    def show_process_viewer(self):
        if self.controller.active_toplevel is None or not self.controller.active_toplevel.winfo_exists():
            self.controller.active_toplevel = ProcessViewerWindow(self)
        else:
            self.controller.active_toplevel.focus()

    def update_all_info(self):
        self.update_dynamic_info()
        self.update_graphs()
        self.after_id = self.after(UPDATE_INTERVAL_MS, self.update_all_info)

    def update_dynamic_info(self):
        cpu = psutil.cpu_percent(interval=None)
        self.cpu_data.append(cpu)
        self.cpu_load.configure(text=f"Load: {cpu:.1f}%")
        self.cpu_temp.configure(text=f"Temp: {get_cpu_temperature_psutil():.1f} °C")
        mem = psutil.virtual_memory()
        self.ram_data.append(mem.percent)
        self.mem_ram.configure(text=f"RAM: {format_bytes(mem.used)} / {format_bytes(mem.total)} ({mem.percent:.1f}%)")
        disk = psutil.disk_usage('/')
        self.disk_usage.configure(text=f"Disk (/): {format_bytes(disk.used)} / {format_bytes(disk.total)} ({disk.percent:.1f}%)")
        disk_io = psutil.disk_io_counters()
        if disk_io:
            self.disk_io.configure(text=f"I/O R/W: {format_bytes(disk_io.read_bytes)} / {format_bytes(disk_io.write_bytes)}")

    def update_graphs(self):
        self.line_cpu.set_ydata(np.array(self.cpu_data))
        self.line_ram.set_ydata(np.array(self.ram_data))
        self.ax_cpu.figure.canvas.draw()
        self.ax_ram.figure.canvas.draw()

    def get_specific_stat(self, query: str) -> Tuple[bool, str]:
        """Returns a specific piece of system information based on a query string."""
        try:
            if query == "cpu_load":
                val = psutil.cpu_percent(interval=None)
                return True, f"Current CPU load is {val:.1f}%."
            elif query == "cpu_temp":
                val = get_cpu_temperature_psutil()
                return True, f"Current CPU temperature is {val:.1f}°C."
            elif query == "mem_used":
                mem = psutil.virtual_memory()
                return True, f"Currently using {format_bytes(mem.used)} of RAM."
            elif query == "mem_percent":
                mem = psutil.virtual_memory()
                return True, f"Current RAM usage is at {mem.percent:.1f}%."
            else:
                return False, f"Unknown status query: '{query}'"
        except Exception as e:
            logger.error(f"Error getting stat for query '{query}': {e}")
            return False, f"Could not retrieve stat: {e}"