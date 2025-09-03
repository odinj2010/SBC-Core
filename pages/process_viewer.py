import customtkinter as ctk
from tkinter import messagebox
import psutil
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def format_bytes(b: Optional[float]) -> str:
    if b is None or b == 0:
        return "0 B"
    power, n = 1024, 0
    units = ("B", "K", "M", "G", "T")
    while b >= power and n < len(units) - 1:
        b /= power
        n += 1
    return f"{b:.1f}{units[n]}"

def _format_io_counters_for_display(io_counters: Optional[psutil._common.pio]) -> str:
    if io_counters:
        read_bytes = getattr(io_counters, 'read_bytes', 0)
        write_bytes = getattr(io_counters, 'write_bytes', 0)
        return f"{format_bytes(read_bytes)} / {format_bytes(write_bytes)}"
    return "N/A"

# --- Configuration Constants ---
APP_FONT = ("Arial", 11)
APP_FONT_BOLD = ("Arial", 11, "bold")
TITLE_FONT = ("Arial", 18, "bold")
PIPBOY_GREEN = "#32f178"
BACKGROUND_COLOR_DARK = "#1a1a1a"
HEADER_BACKGROUND_COLOR = "#2a2d3e"
WIDGET_PADX = 10
WIDGET_PADY = 5
PROCESS_ROW_PADY = 1
# --- MODIFIED --- Performance tuning for Raspberry Pi
REFRESH_INTERVAL_MS = 3000 # Increased from 2000ms to 3000ms

# --- Process List Headers Configuration ---
HEADERS_CONFIG: List[Dict[str, Any]] = [
    {"text": "PID", "psutil_attr": "pid", "formatter": lambda v: str(v) if v is not None else "N/A", "sort_key": "pid", "sort_reverse": False},
    {"text": "Process Name", "psutil_attr": "name", "formatter": lambda v: str(v) if v is not None else "N/A", "sort_key": "name", "sort_reverse": False},
    {"text": "CPU %", "psutil_attr": "cpu_percent", "formatter": lambda v: f"{v:.1f}" if v is not None else "0.0", "sort_key": "cpu_percent", "sort_reverse": True},
    {"text": "Mem %", "psutil_attr": "memory_percent", "formatter": lambda v: f"{v:.1f}" if v is not None else "0.0", "sort_key": "memory_percent", "sort_reverse": True},
    {"text": "User", "psutil_attr": "username", "formatter": lambda v: str(v) if v is not None else "N/A", "sort_key": "username", "sort_reverse": False},
    {"text": "Disk R/W", "psutil_attr": "io_counters", "formatter": _format_io_counters_for_display, "sort_key": None, "sort_reverse": True},
]

class ProcessViewerWindow(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, sort_by: str = "cpu_percent", title: str = "Process Viewer"):
        super().__init__(parent)
        self.title(title)
        #self.attributes("-fullscreen", True)
        self.configure(fg_color=BACKGROUND_COLOR_DARK)
        self.grab_set() # Make the window modal

        logger.info(f"Process Viewer initialized: title='{title}', sorting by='{sort_by}'")

        self.sort_by = sort_by
        self.sort_reverse = True
        self.selected_pid: Optional[int] = None
        self.process_row_widgets: Dict[int, Dict[str, Any]] = {}
        self.header_buttons: Dict[str, ctk.CTkButton] = {}
        self.after_id: Optional[str] = None

        self._header_config_map: Dict[str, Dict[str, Any]] = {
            config["psutil_attr"]: config for config in HEADERS_CONFIG if config.get("psutil_attr")
        }

        initial_config = self._header_config_map.get(self.sort_by, {})
        self.sort_reverse = initial_config.get("sort_reverse", False)

        self.setup_layout()
        self.create_widgets(title)
        self.after(100, self.populate_processes) # Schedule initial population
        
    def setup_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

    def create_widgets(self, title: str) -> None:
        # --- Row 0: Title and Close Button ---
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", padx=WIDGET_PADX, pady=(WIDGET_PADY * 2, WIDGET_PADY))
        title_frame.columnconfigure(0, weight=1)
        
        ctk.CTkLabel(title_frame, text=title, font=TITLE_FONT, text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(title_frame, text="Close Window", font=APP_FONT, width=120, command=self.destroy).grid(row=0, column=1, sticky="e", padx=WIDGET_PADX/2)

        # --- Row 1: Headers for the process list ---
        header_frame = ctk.CTkFrame(self, fg_color=HEADER_BACKGROUND_COLOR, height=30)
        header_frame.grid(row=1, column=0, sticky="ew", padx=WIDGET_PADX, pady=WIDGET_PADY)
        
        for i in range(len(HEADERS_CONFIG)): 
            header_frame.grid_columnconfigure(i, weight=1)
        
        for i, config in enumerate(HEADERS_CONFIG):
            attr = config.get("psutil_attr")
            if attr and config.get("sort_key"):
                header_button = ctk.CTkButton(
                    header_frame, text=config["text"], font=APP_FONT_BOLD, text_color=PIPBOY_GREEN,
                    fg_color="transparent", hover_color="#3a3d3e", anchor="w",
                    command=lambda a=attr: self.change_sort_order(a)
                )
                self.header_buttons[attr] = header_button
            else:
                header_button = ctk.CTkLabel(header_frame, text=config["text"], font=APP_FONT_BOLD, text_color=PIPBOY_GREEN, anchor="w")

            header_button.grid(row=0, column=i, sticky="nsew", padx=WIDGET_PADX/2)
        
        self._update_header_visuals()

        # --- Row 2: Scrollable Process List ---
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=WIDGET_PADX, pady=(0, WIDGET_PADY))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # --- Row 3: Action Buttons ---
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=3, column=0, sticky="ew", padx=WIDGET_PADX, pady=WIDGET_PADY)
        
        self.refresh_button = ctk.CTkButton(action_frame, text="Refresh", font=APP_FONT, command=self.populate_processes)
        self.refresh_button.pack(side="left")
        
        self.kill_button = ctk.CTkButton(action_frame, text="Kill Process", font=APP_FONT, 
                                        state="disabled", fg_color="#8B0000", hover_color="#AE0000", 
                                        command=self.kill_selected_process)
        self.kill_button.pack(side="right")
        
    def select_process(self, pid: int, frame: ctk.CTkFrame) -> None:
        if self.selected_pid == pid:
            frame.configure(fg_color="transparent")
            self.selected_pid = None
            self.kill_button.configure(state="disabled")
            logger.debug(f"Process deselected: PID={pid}")
            return

        logger.debug(f"Process selected: PID={pid}")
        if self.selected_pid is not None and self.selected_pid in self.process_row_widgets:
            prev_frame = self.process_row_widgets[self.selected_pid]['frame']
            prev_frame.configure(fg_color="transparent")
        
        self.selected_pid = pid
        frame.configure(fg_color=PIPBOY_GREEN)
        self.kill_button.configure(state="normal")
        
    def change_sort_order(self, new_sort_by: str) -> None:
        logger.info(f"Changing sort order to '{new_sort_by}'")
        if self.sort_by == new_sort_by:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_by = new_sort_by
            sort_config = self._header_config_map.get(self.sort_by, {})
            self.sort_reverse = sort_config.get("sort_reverse", False)
        
        self._update_header_visuals()
        self.populate_processes()

    def _update_header_visuals(self) -> None:
        for attr, button in self.header_buttons.items():
            base_text = self._header_config_map[attr]['text']
            if attr == self.sort_by:
                arrow = '▼' if self.sort_reverse else '▲'
                button.configure(text=f"{base_text} {arrow}")
            else:
                button.configure(text=base_text)

    def _get_formatted_process_data(self, p_info: Dict[str, Any]) -> List[str]:
        formatted_data: List[str] = []
        for config in HEADERS_CONFIG:
            attr = config["psutil_attr"]
            value = p_info.get(attr)
            formatter = config.get("formatter")
            # Ensure formatter is callable before calling it
            formatted_data.append(formatter(value) if callable(formatter) else str(value) if value is not None else 'N/A')
        return formatted_data

    def _create_process_row_widgets(self, p_info: Dict[str, Any], parent_frame: ctk.CTkFrame, row_idx: int) -> Tuple[ctk.CTkFrame, List[ctk.CTkLabel]]:
        pid = p_info['pid']
        p_frame = ctk.CTkFrame(parent_frame, fg_color="transparent", cursor="hand2")
        p_frame.grid(row=row_idx, column=0, sticky="ew", pady=PROCESS_ROW_PADY)
        
        for i in range(len(HEADERS_CONFIG)): 
            p_frame.grid_columnconfigure(i, weight=1)
        
        labels: List[ctk.CTkLabel] = []
        for i in range(len(HEADERS_CONFIG)):
            label = ctk.CTkLabel(p_frame, text="", font=APP_FONT, anchor="w")
            label.grid(row=0, column=i, sticky="w", padx=WIDGET_PADX/2)
            label.bind("<Button-1>", lambda e, p=pid, f=p_frame: self.select_process(p, f))
            labels.append(label)
            
        p_frame.bind("<Button-1>", lambda e, p=pid, f=p_frame: self.select_process(p, f))
        return p_frame, labels

    def _update_process_row_widgets(self, widgets: Dict[str, Any], p_info: Dict[str, Any]) -> None:
        p_frame = widgets['frame']
        labels = widgets['labels']
        pid = p_info['pid']

        if self.selected_pid == pid:
            p_frame.configure(fg_color=PIPBOY_GREEN)
        else:
            p_frame.configure(fg_color="transparent")

        data_points = self._get_formatted_process_data(p_info)
        for i, text in enumerate(data_points):
            if i < len(labels):
                labels[i].configure(text=text)

    def _get_process_sort_key(self, p_info: Dict[str, Any]) -> Any:
        sort_attr_config = self._header_config_map.get(self.sort_by)
        if not sort_attr_config or sort_attr_config.get("sort_key") is None:
            # Fallback to pid if sort_by or sort_key is not configured
            return p_info.get("pid", 0) 
            
        attr_to_sort_by = sort_attr_config["sort_key"]
        value = p_info.get(attr_to_sort_by)

        if attr_to_sort_by in ["cpu_percent", "memory_percent", "pid"]:
            return value if value is not None else 0.0
        elif attr_to_sort_by in ["name", "username"]:
            return str(value).lower() if value is not None else ""
        
        # Default fallback for other types
        return value if value is not None else 0

    def populate_processes(self) -> None:
        logger.debug("Refreshing process list...")
        if self.after_id is not None:
            self.after_cancel(self.after_id)

        try:
            new_processes_data: List[Dict[str, Any]] = []
            
            # Collect all psutil attributes needed for display AND sorting
            attrs_to_fetch_set = set()
            for config in HEADERS_CONFIG:
                if "psutil_attr" in config and config["psutil_attr"] is not None:
                    attrs_to_fetch_set.add(config["psutil_attr"])
                if config.get("sort_key") and config["sort_key"] is not None:
                    attrs_to_fetch_set.add(config["sort_key"])
            
            # Ensure the current sort_by attribute is also fetched
            current_sort_config = self._header_config_map.get(self.sort_by)
            if current_sort_config and current_sort_config.get("psutil_attr") is not None:
                attrs_to_fetch_set.add(current_sort_config["psutil_attr"])
            elif self.sort_by and self.sort_by not in attrs_to_fetch_set: # Fallback if sort_by is a psutil_attr not in headers
                attrs_to_fetch_set.add(self.sort_by)

            attrs_to_fetch = list(attrs_to_fetch_set)
            logger.debug(f"Fetching psutil attributes: {attrs_to_fetch}")

            for p in psutil.process_iter(attrs=attrs_to_fetch):
                try:
                    # Fetching as dict to avoid issues with missing attributes for some processes
                    process_info = p.as_dict(attrs=attrs_to_fetch, ad_value=None) 
                    new_processes_data.append(process_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.debug(f"Could not access process info for PID {p.pid}: {e}")
                except Exception as e:
                    logger.warning(f"An unexpected error occurred while fetching info for PID {p.pid}: {e}", exc_info=True)
            
            new_processes_data.sort(key=self._get_process_sort_key, reverse=self.sort_reverse)
            logger.debug(f"Successfully retrieved and sorted info for {len(new_processes_data)} processes.")

            new_pids = {p['pid'] for p in new_processes_data}
            current_pids = set(self.process_row_widgets.keys())

            vanished_pids = current_pids - new_pids
            for pid in vanished_pids:
                logger.debug(f"Removing vanished process PID: {pid}")
                self.process_row_widgets[pid]['frame'].destroy()
                del self.process_row_widgets[pid]
                if self.selected_pid == pid:
                    self.selected_pid = None
                    self.kill_button.configure(state="disabled")

            updated_process_row_widgets: Dict[int, Dict[str, Any]] = {}
            row_idx = 0
            for p_info in new_processes_data:
                pid = p_info['pid']
                if pid in self.process_row_widgets:
                    widgets = self.process_row_widgets[pid]
                    # Make sure the frame is at the correct grid position in case of re-sort
                    widgets['frame'].grid(row=row_idx, column=0, sticky="ew", pady=PROCESS_ROW_PADY)
                    self._update_process_row_widgets(widgets, p_info)
                    updated_process_row_widgets[pid] = widgets
                else:
                    logger.debug(f"Adding new process PID: {pid}")
                    p_frame, labels = self._create_process_row_widgets(p_info, self.scroll_frame, row_idx)
                    self._update_process_row_widgets({'frame': p_frame, 'labels': labels}, p_info)
                    updated_process_row_widgets[pid] = {'frame': p_frame, 'labels': labels}
                row_idx += 1

            # Destroy any remaining old widgets if the count decreased (should be handled by vanished_pids, but as a safeguard)
            for pid in list(self.process_row_widgets.keys()):
                if pid not in updated_process_row_widgets:
                    try:
                        self.process_row_widgets[pid]['frame'].destroy()
                    except Exception as e:
                        logger.warning(f"Error destroying leftover widget for PID {pid}: {e}")
                    del self.process_row_widgets[pid]


            self.process_row_widgets = updated_process_row_widgets

            if self.selected_pid is None or self.selected_pid not in self.process_row_widgets:
                 self.kill_button.configure(state="disabled")

        except Exception as e:
            logger.error(f"Critical error during process population: {e}", exc_info=True)
            # Display an error message to the user if a critical error occurs
            # This helps to diagnose if the window is responsive enough to show messages
            messagebox.showerror("Process Viewer Error", f"Failed to load processes: {e}\nCheck logs for details.", parent=self)
            
        finally:
            # Always reschedule the next refresh, even if an error occurred, to try and recover
            self.after_id = self.after(REFRESH_INTERVAL_MS, self.populate_processes)

    def kill_selected_process(self) -> None:
        if self.selected_pid is None:
            return

        try:
            p = psutil.Process(self.selected_pid)
            p_name = p.name()
            confirmed = messagebox.askyesno(
                "Confirm Kill", 
                f"Are you sure you want to terminate '{p_name}' (PID: {self.selected_pid})?", 
                parent=self
            )
            if confirmed:
                p.kill()
                logger.info(f"Process '{p_name}' (PID: {self.selected_pid}) terminated.")
                messagebox.showinfo("Success", f"Process '{p_name}' has been terminated.", parent=self)
            else:
                logger.info(f"Process kill for PID {self.selected_pid} cancelled by user.")
        except psutil.NoSuchProcess:
            logger.warning(f"Attempted to kill non-existent process PID {self.selected_pid}.")
            messagebox.showerror("Error", "Process no longer exists.", parent=self)
        except psutil.AccessDenied:
            logger.error(f"Access denied when attempting to kill process PID {self.selected_pid}.")
            messagebox.showerror("Access Denied", "You do not have permission to terminate this process.", parent=self)
        except Exception as e:
            logger.error(f"An unexpected error occurred while killing PID {self.selected_pid}: {e}", exc_info=True)
            messagebox.showerror("Error", f"An unexpected error occurred:\n{e}", parent=self)
        finally:
            self.populate_processes()

    def destroy(self) -> None:
        logger.info("Process Viewer closed.")
        if self.after_id is not None:
            self.after_cancel(self.after_id)
        try:
            # Explicitly release the grab before destroying the window
            self.grab_release() 
        except Exception as e:
            logger.warning(f"Error releasing grab: {e}") # Log if there's an issue releasing
        super().destroy()

if __name__ == "__main__":
    # Set logging level to DEBUG to see all detailed messages
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    class MainApplication(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("Main Application")
            self.geometry("300x100")
            self.protocol("WM_DELETE_WINDOW", self.on_closing)

            self.open_button = ctk.CTkButton(self, text="Open Process Viewer", command=self.open_viewer)
            self.open_button.pack(pady=20)
            
            self.viewer_window: Optional[ProcessViewerWindow] = None

        def open_viewer(self):
            if self.viewer_window is None or not self.viewer_window.winfo_exists():
                self.viewer_window = ProcessViewerWindow(self)
                # It's good practice to set protocol after the window is fully initialized
                self.viewer_window.protocol("WM_DELETE_WINDOW", self.on_viewer_close)
            else:
                self.viewer_window.focus()

        def on_viewer_close(self):
            logger.info("Process viewer window closed by user.")
            if self.viewer_window is not None:
                # Call destroy on the window to ensure clean up, which includes grab_release()
                self.viewer_window.destroy()
                self.viewer_window = None

        def on_closing(self):
            logger.info("Main application window closing.")
            if self.viewer_window is not None and self.viewer_window.winfo_exists():
                # Ensure viewer window is destroyed before main app
                self.viewer_window.destroy() 
            self.destroy()

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = MainApplication()
    app.mainloop()