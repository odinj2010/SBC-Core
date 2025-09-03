# pages/gpio_page.py
import tkinter as tk
from tkinter import messagebox
import logging
import threading
import time
import os
import json
from functools import partial
from enum import Enum
from typing import Dict, Any, Optional, Type, TYPE_CHECKING, Union, Callable, List, Tuple
from dataclasses import dataclass

import customtkinter as ctk

# --- Conditional gpiozero import and Type Hinting Setup ---
if TYPE_CHECKING:
    from gpiozero import Device as GZDevice, LED as GZLED, PWMLED as GZPWMLED, Button as GZButton
    from main import MainApplication
    _Device, _LED, _PWMLED, _Button = GZDevice, GZLED, GZPWMLED, GZButton
else:
    _Device, _LED, _PWMLED, _Button = Any, Any, Any, Any
    MainApplication = ctk.CTk

Device: Optional[Type[_Device]] = None
LED: Optional[Type[_LED]] = None
PWMLED: Optional[Type[_PWMLED]] = None
Button: Optional[Type[_Button]] = None

# --- Configuration Constants ---
@dataclass
class PinInfo:
    physical_pin: int
    name: str
    type: str
    bcm: Optional[int] = None
    supports_pwm: bool = False

PIN_CONFIG: List[PinInfo] = [
    PinInfo(1, "3.3v", "power"), PinInfo(2, "5v", "power"), PinInfo(3, "SDA", "gpio", bcm=2),
    PinInfo(4, "5v", "power"), PinInfo(5, "SCL", "gpio", bcm=3), PinInfo(6, "GND", "ground"),
    PinInfo(7, "GPIO4", "gpio", bcm=4), PinInfo(8, "TXD", "gpio", bcm=14), PinInfo(9, "GND", "ground"),
    PinInfo(10, "RXD", "gpio", bcm=15), PinInfo(11, "GPIO17", "gpio", bcm=17),
    PinInfo(12, "GPIO18", "gpio", bcm=18, supports_pwm=True), PinInfo(13, "GPIO27", "gpio", bcm=27),
    PinInfo(14, "GND", "ground"), PinInfo(15, "GPIO22", "gpio", bcm=22), PinInfo(16, "GPIO23", "gpio", bcm=23),
    PinInfo(17, "3.3v", "power"), PinInfo(18, "GPIO24", "gpio", bcm=24), PinInfo(19, "MOSI", "gpio", bcm=10),
    PinInfo(20, "GND", "ground"), PinInfo(21, "MISO", "gpio", bcm=9), PinInfo(22, "GPIO25", "gpio", bcm=25),
    PinInfo(23, "SCLK", "gpio", bcm=11), PinInfo(24, "CE0", "gpio", bcm=8), PinInfo(25, "GND", "ground"),
    PinInfo(26, "CE1", "gpio", bcm=7), PinInfo(27, "ID_SD", "gpio", bcm=0), PinInfo(28, "ID_SC", "gpio", bcm=1),
    PinInfo(29, "GPIO5", "gpio", bcm=5), PinInfo(30, "GND", "ground"), PinInfo(31, "GPIO6", "gpio", bcm=6),
    PinInfo(32, "GPIO12", "gpio", bcm=12, supports_pwm=True), PinInfo(33, "GPIO13", "gpio", bcm=13, supports_pwm=True),
    PinInfo(34, "GND", "ground"), PinInfo(35, "GPIO19", "gpio", bcm=19, supports_pwm=True),
    PinInfo(36, "GPIO16", "gpio", bcm=16), PinInfo(37, "GPIO26", "gpio", bcm=26),
    PinInfo(38, "GPIO20", "gpio", bcm=20), PinInfo(39, "GND", "ground"), PinInfo(40, "GPIO21", "gpio", bcm=21),
]

BCM_PIN_MAP: Dict[int, PinInfo] = { info.bcm: info for info in PIN_CONFIG if info.bcm is not None }

THEME_COLORS: Dict[str, str] = { "background_main": "#1a1a1a", "background_frame": "#2a2d2e", "header_text": "#32f178", "pin_num_text": "#FFB000", "mode_default_text": "gray", "state_default_text": "gray", "output_mode_text": "#32f178", "input_mode_text": "#00AFFF", "pwm_mode_text": "#FFB000", "high_state_text": "#32f178", "low_state_text": "gray", "pulse_state_text": "orange", "button_default_bg": "#4a4d4e", "button_default_hover": "#6a6d6e", "button_output_bg": "green", "button_output_hover": "#006400", "button_pwm_bg": "orange", "button_pwm_hover": "#c88600", "button_pulse_start": "green", "button_pulse_stop": "red", "button_setup_bg": "#34a3eb", "button_setup_hover": "#2a80bb", "button_release_bg": "red", "button_release_hover": "#cc0000", }
FONTS: Dict[str, tuple] = { "header": ("Arial", 20, "bold"), "sub_header": ("Arial", 16, "bold"), "pin_num": ("Arial", 12, "bold"), "pin_name": ("Arial", 11), "pin_mode_state": ("Arial", 10), "button_general": ("Arial", 10), "button_large": ("Arial", 18), "button_medium": ("Arial", 14), "pwm_label": ("Arial", 24, "bold"), "option_menu": ("Arial", 12), }
UPDATE_INTERVAL_MS: int = 250
GPIO_STATE_FILE = "gpio_state.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GPIO_AVAILABLE: bool = False
try:
    from gpiozero import Device as GZDevice, LED as GZLED, PWMLED as GZPWMLED, Button as GZButton
    from gpiozero.pins.lgpio import LGPIOFactory
    GZDevice.pin_factory = LGPIOFactory()
    GPIO_AVAILABLE = True
    logger.info("gpiozero library loaded successfully.")
    Device, LED, PWMLED, Button = GZDevice, GZLED, GZPWMLED, GZButton
except (ImportError, OSError) as e:
    GPIO_AVAILABLE = False
    logger.warning(f"GPIO libraries unavailable: {e}. GPIO functionality will be disabled.")

class PinMode(Enum):
    OUTPUT, INPUT, PWM = "OUTPUT", "INPUT", "PWM"

class CenteredToplevelWindow(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk | ctk.CTkToplevel, width: int = 400, height: int = 300, title: str = "Window", **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self.title(title); self.transient(parent)
        self.update_idletasks()
        self.grab_set()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = int((screen_width / 2) - (width / 2))
        y = int((screen_height / 2) - (height / 2))
        self.geometry(f'{width}x{height}+{x}+{y}')
        self.configure(fg_color=THEME_COLORS["background_main"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self) -> None:
        self.grab_release(); self.destroy()

class PinSetupWindow(CenteredToplevelWindow):
    def __init__(self, root_window: MainApplication, gpio_page: 'GPIOPage', pin_info: PinInfo) -> None:
        if pin_info.bcm is None: raise ValueError("Cannot open PinSetupWindow for a non-GPIO pin.")
        super().__init__(root_window, width=300, height=300, title=f"Setup BCM Pin {pin_info.bcm}")
        self.gpio_page, self.bcm_pin, self.pin_info = gpio_page, pin_info.bcm, pin_info
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1); self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=f"Configure BCM Pin {self.bcm_pin}", font=FONTS["sub_header"], text_color=THEME_COLORS["header_text"]).grid(row=0, column=0, pady=(15, 10))
        
        button_font, button_height = FONTS["button_medium"], 40
        ctk.CTkButton(self, text="Set as OUTPUT", command=lambda: self._set_mode_and_close(PinMode.OUTPUT), font=button_font, height=button_height, fg_color=THEME_COLORS["output_mode_text"], hover_color=THEME_COLORS["button_output_hover"]).grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        ctk.CTkButton(self, text="Set as INPUT", command=lambda: self._set_mode_and_close(PinMode.INPUT), font=button_font, height=button_height, fg_color=THEME_COLORS["input_mode_text"], hover_color=THEME_COLORS["button_setup_hover"]).grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        
        if self.pin_info.supports_pwm:
            ctk.CTkButton(self, text="Set as PWM", command=lambda: self._set_mode_and_close(PinMode.PWM), font=button_font, height=button_height, fg_color=THEME_COLORS["pwm_mode_text"], hover_color=THEME_COLORS["button_pwm_hover"]).grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        else:
            ctk.CTkLabel(self, text="PWM Not Supported", font=FONTS["button_medium"], text_color="gray").grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        persistence_var = ctk.BooleanVar(value=self.gpio_page.is_pin_persistent(self.bcm_pin))
        persistence_check = ctk.CTkCheckBox(self, text="Save Pin State on Exit", variable=persistence_var, command=lambda: self.gpio_page.set_pin_persistence(self.bcm_pin, persistence_var.get()), font=FONTS["option_menu"])
        persistence_check.grid(row=4, column=0, padx=20, pady=5, sticky="w")
        
        if self.bcm_pin in self.gpio_page.active_devices:
            ctk.CTkButton(self, text="Release Pin", command=self._release_pin_and_close, font=button_font, height=button_height, fg_color=THEME_COLORS["button_release_bg"], hover_color=THEME_COLORS["button_release_hover"]).grid(row=5, column=0, padx=20, pady=(10, 15), sticky="ew")

    def _set_mode_and_close(self, mode: PinMode) -> None:
        self.gpio_page.setup_pin(self.bcm_pin, mode); self.on_close()
    def _release_pin_and_close(self) -> None:
        self.gpio_page.cleanup_pin(self.bcm_pin); self.on_close()
    def on_close(self) -> None:
        self.gpio_page.start_updates(); super().on_close()

class PwmControlWindow(CenteredToplevelWindow):
    def __init__(self, root_window: MainApplication, gpio_page: 'GPIOPage', bcm_pin: int, pwm_device: _PWMLED, **kwargs: Any) -> None:
        super().__init__(root_window, width=500, height=350, title=f"PWM Control: BCM Pin {bcm_pin}", **kwargs)
        self.pwm_device, self.parent_page, self.bcm_pin = pwm_device, gpio_page, bcm_pin
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(0, weight=1)
        main_frame = ctk.CTkFrame(self, fg_color="transparent"); main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_frame.grid_columnconfigure(0, weight=1); main_frame.grid_rowconfigure(0, weight=1); main_frame.grid_rowconfigure(1, weight=1); main_frame.grid_rowconfigure(2, weight=1)
        self.label = ctk.CTkLabel(main_frame, text="Duty Cycle: --%", font=FONTS["pwm_label"]); self.label.grid(row=0, column=0, sticky="s", pady=10)
        self.slider = ctk.CTkSlider(main_frame, from_=0, to=100, command=self._update_pwm_slider, height=30, button_length=30, button_corner_radius=15); self.slider.grid(row=1, column=0, padx=10, sticky="ew"); self.slider.set(0)
        ctk.CTkButton(main_frame, text="Close", font=FONTS["button_large"], command=self.on_close, height=50).grid(row=2, column=0, sticky="new", pady=10)
        self.after(50, self.load_device_state)

    def load_device_state(self) -> None:
        if not GPIO_AVAILABLE or PWMLED is None or not isinstance(self.pwm_device, PWMLED): self.label.configure(text="PWM Device Not Ready!"); self.slider.configure(state="disabled"); logger.warning(f"PWM device for pin {self.bcm_pin} not properly initialized."); return
        try:
            initial_value = self.pwm_device.value; self.slider.set(int(initial_value * 100)); self.label.configure(text=f"Duty Cycle: {int(initial_value * 100)}%")
        except Exception as e: logger.error(f"Failed to load PWM device state for pin {self.bcm_pin}: {e}"); self.label.configure(text="Error reading device!"); self.slider.configure(state="disabled")

    def _update_pwm_slider(self, value: float) -> None:
        duty_cycle_percent = float(value); self.label.configure(text=f"Duty Cycle: {int(duty_cycle_percent)}%")
        if not GPIO_AVAILABLE or PWMLED is None or not isinstance(self.pwm_device, PWMLED): logger.warning(f"Attempted to set PWM value for pin {self.bcm_pin}, but PWMLED device is not active."); return
        try: self.pwm_device.value = duty_cycle_percent / 100.0
        except Exception as e: logger.error(f"Error setting PWM value for pin {self.bcm_pin}: {e}"); messagebox.showerror("GPIO Error", f"Failed to set PWM value for pin {self.bcm_pin}:\n{e}", parent=self)
    
    def on_close(self) -> None:
        self.parent_page.save_persistent_states() # --- MODIFIED: Save state on close
        self.parent_page.start_updates(); super().on_close()

class OutputControlWindow(CenteredToplevelWindow):
    UNIT_CONVERSIONS: Dict[str, Callable[[float], float]] = {"Milliseconds": lambda x: x / 1000.0, "Seconds": lambda x: x, "Minutes": lambda x: x * 60.0}
    def __init__(self, root_window: MainApplication, gpio_page: 'GPIOPage', bcm_pin: int, output_device: _LED, **kwargs: Any) -> None:
        super().__init__(root_window, width=500, height=450, title=f"Output Control: BCM Pin {bcm_pin}", **kwargs)
        self.parent_page, self.bcm_pin, self.output_device = gpio_page, bcm_pin, output_device
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(0, weight=1)
        main_frame = ctk.CTkFrame(self, fg_color="transparent"); main_frame.grid(row=0, column=0, sticky="nsew"); main_frame.grid_columnconfigure(0, weight=1)
        manual_frame = ctk.CTkFrame(main_frame, fg_color=THEME_COLORS["background_frame"]); manual_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew"); manual_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(manual_frame, text="Manual Control", font=FONTS["sub_header"]).grid(row=0, column=0, pady=(10,5))
        self.toggle_button = ctk.CTkButton(manual_frame, text="Toggle High/Low", height=40, font=FONTS["button_medium"], state="disabled"); self.toggle_button.grid(row=1, column=0, padx=20, pady=(5, 15), sticky="ew")
        pulse_frame = ctk.CTkFrame(main_frame, fg_color=THEME_COLORS["background_frame"]); pulse_frame.grid(row=1, column=0, padx=20, pady=0, sticky="ew"); pulse_frame.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(pulse_frame, text="Programmed Pulse", font=FONTS["sub_header"]).grid(row=0, column=0, columnspan=2, pady=(10, 5)); ctk.CTkLabel(pulse_frame, text="Interval:", font=FONTS["option_menu"]).grid(row=1, column=0, columnspan=2)
        self.interval_entry = ctk.CTkEntry(pulse_frame, justify="center"); self.interval_entry.grid(row=2, column=0, padx=10, pady=5, sticky="e"); self.interval_entry.insert(0, "500")
        self.units_var = ctk.StringVar(value="Milliseconds"); self.units_menu = ctk.CTkOptionMenu(pulse_frame, variable=self.units_var, values=list(self.UNIT_CONVERSIONS.keys()), font=FONTS["option_menu"]); self.units_menu.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        self.pulse_button = ctk.CTkButton(pulse_frame, text="Start Pulse", command=self._toggle_pulse, height=40, font=FONTS["button_medium"], fg_color=THEME_COLORS["button_pulse_start"]); self.pulse_button.grid(row=3, column=0, columnspan=2, padx=20, pady=(10, 15), sticky="ew")
        self._update_pulse_button_state()
        ctk.CTkButton(main_frame, text="Close", font=FONTS["button_large"], command=self.on_close, height=50).grid(row=2, column=0, padx=20, pady=20, sticky="ew")
        self.after(50, self.load_device_state)

    def load_device_state(self) -> None:
        if not GPIO_AVAILABLE or LED is None or not isinstance(self.output_device, LED): self.toggle_button.configure(text="Output Device Not Ready!", state="disabled"); logger.warning(f"Output device for pin {self.bcm_pin} not properly initialized."); return
        try: 
            self.toggle_button.configure(command=self._toggle_and_save, state="normal")
            self._update_pulse_button_state()
        except Exception as e: logger.error(f"Failed to link output device for pin {self.bcm_pin}: {e}"); self.toggle_button.configure(text="Error!", state="disabled")

    # --- NEW: Wrapper for toggle to save state after toggling ---
    def _toggle_and_save(self) -> None:
        self.output_device.toggle()
        self.parent_page.save_persistent_states()

    def _get_interval_in_seconds(self) -> float:
        try:
            interval_val = float(self.interval_entry.get())
            if interval_val <= 0: raise ValueError("Interval must be positive.")
            return self.UNIT_CONVERSIONS[self.units_var.get()](interval_val)
        except ValueError as e: messagebox.showerror("Invalid Input", f"Please enter a valid positive number. Error: {e}", parent=self); raise

    def _toggle_pulse(self) -> None:
        if self.parent_page.is_pin_pulsing(self.bcm_pin): self.parent_page.stop_pulse(self.bcm_pin)
        else:
            try:
                if not GPIO_AVAILABLE or LED is None or not isinstance(self.output_device, LED): messagebox.showerror("GPIO Error", "Output device not properly initialized.", parent=self)
                else: self.parent_page.start_pulse(self.bcm_pin, self.output_device, self._get_interval_in_seconds())
            except ValueError: return
            except Exception as e: messagebox.showerror("GPIO Error", f"Failed to start pulse: {e}", parent=self)
        self._update_pulse_button_state()

    def _update_pulse_button_state(self) -> None:
        if self.parent_page.is_pin_pulsing(self.bcm_pin): self.pulse_button.configure(text="Stop Pulse", fg_color=THEME_COLORS["button_pulse_stop"], hover_color=THEME_COLORS["button_release_hover"])
        else: self.pulse_button.configure(text="Start Pulse", fg_color=THEME_COLORS["button_pulse_start"], hover_color=THEME_COLORS["button_output_hover"])
    
    def on_close(self) -> None:
        if self.parent_page.is_pin_pulsing(self.bcm_pin): self.parent_page.stop_pulse(self.bcm_pin)
        self.parent_page.save_persistent_states() # --- MODIFIED: Save state on close
        self.parent_page.start_updates(); super().on_close()

class PinDisplayWidget(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkScrollableFrame, pin_info: PinInfo, gpio_page: 'GPIOPage', open_setup_window_command: Callable[[PinInfo], None], **kwargs: Any) -> None:
        super().__init__(master, fg_color=THEME_COLORS["background_frame"], corner_radius=6, **kwargs)
        self.pin_info, self.physical_pin, self.bcm_pin, self.pin_name = pin_info, pin_info.physical_pin, pin_info.bcm, pin_info.name
        self._open_setup_window_command = open_setup_window_command
        self.gpio_page = gpio_page
        
        self.grid_columnconfigure(0, weight=0); self.grid_columnconfigure(1, weight=1); self.grid_columnconfigure(2, weight=0); self.grid_columnconfigure(3, weight=0); self.grid_columnconfigure(4, weight=0); self.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(self, text=f"{self.physical_pin:02d}", font=FONTS["pin_num"], text_color=THEME_COLORS["pin_num_text"]).grid(row=0, column=0, padx=8, pady=3, sticky="ns")
        
        self.pin_name_label = ctk.CTkLabel(self, text=f"{self.pin_name:<7}", font=FONTS["pin_name"], anchor="w")
        self.pin_name_label.grid(row=0, column=1, sticky="nsew", padx=5)
        
        if self.bcm_pin is not None:
            self.mode_lbl = ctk.CTkLabel(self, text="?", font=FONTS["pin_mode_state"], width=35, text_color=THEME_COLORS["mode_default_text"]); self.mode_lbl.grid(row=0, column=2, padx=4)
            self.state_lbl = ctk.CTkLabel(self, text="?", font=FONTS["pin_mode_state"], width=45, text_color=THEME_COLORS["state_default_text"]); self.state_lbl.grid(row=0, column=3, padx=4)
            self.control_btn = ctk.CTkButton(self, text="Setup", font=FONTS["button_general"], width=50, fg_color=THEME_COLORS["button_setup_bg"], hover_color=THEME_COLORS["button_setup_hover"], command=self._open_setup_window); self.control_btn.grid(row=0, column=4, padx=8, pady=4)
        else:
            bg_color = THEME_COLORS["background_frame"]
            ctk.CTkLabel(self, text="", width=35, fg_color=bg_color).grid(row=0, column=2, padx=4)
            ctk.CTkLabel(self, text="", width=45, fg_color=bg_color).grid(row=0, column=3, padx=4)
            ctk.CTkButton(self, text="", width=50, state="disabled", fg_color=bg_color, hover=False).grid(row=0, column=4, padx=8, pady=4)

    def _open_setup_window(self) -> None:
        if self.bcm_pin is not None: self._open_setup_window_command(self.pin_info)

    def update_status(self, device: Optional[_Device] = None, is_pulsing: bool = False) -> None:
        if self.bcm_pin is None: return
        
        is_persistent = self.gpio_page.is_pin_persistent(self.bcm_pin)
        indicator = " 💾" if is_persistent else "" # Using a save icon
        self.pin_name_label.configure(text=f"{self.pin_name:<7}{indicator}")

        if device is None or not GPIO_AVAILABLE:
            self.mode_lbl.configure(text="?", text_color=THEME_COLORS["mode_default_text"]); self.state_lbl.configure(text="?", text_color=THEME_COLORS["state_default_text"])
            self.control_btn.configure(text="Setup", state="normal", fg_color=THEME_COLORS["button_setup_bg"], hover_color=THEME_COLORS["button_setup_hover"], command=self._open_setup_window); self.configure(border_width=0)
            return
        
        if PWMLED is not None and isinstance(device, PWMLED):
            self.mode_lbl.configure(text="PWM", text_color=THEME_COLORS["pwm_mode_text"]); self.state_lbl.configure(text=f"{int(device.value*100)}%", text_color=THEME_COLORS["pwm_mode_text"])
            self.control_btn.configure(text="Control", state="normal", fg_color=THEME_COLORS["button_pwm_bg"], hover_color=THEME_COLORS["button_pwm_hover"]); self.configure(border_width=2, border_color=THEME_COLORS["pwm_mode_text"])
        elif LED is not None and isinstance(device, LED):
            self.mode_lbl.configure(text="OUT", text_color=THEME_COLORS["output_mode_text"]); state_text, state_color = ("PULSE", THEME_COLORS["pulse_state_text"]) if is_pulsing else (("HIGH", THEME_COLORS["high_state_text"]) if device.is_lit else ("LOW", THEME_COLORS["low_state_text"]))
            self.state_lbl.configure(text=state_text, text_color=state_color); self.control_btn.configure(text="Control", state="normal", fg_color=THEME_COLORS["button_output_bg"], hover_color=THEME_COLORS["button_output_hover"]); self.configure(border_width=2, border_color=THEME_COLORS["output_mode_text"])
        elif Button is not None and isinstance(device, Button):
            self.mode_lbl.configure(text="IN", text_color=THEME_COLORS["input_mode_text"]); state = device.is_pressed; self.state_lbl.configure(text="HIGH" if state else "LOW", text_color=THEME_COLORS["high_state_text"] if state else THEME_COLORS["low_state_text"])
            self.control_btn.configure(text="View", state="disabled", fg_color=THEME_COLORS["button_default_bg"], hover_color=THEME_COLORS["button_default_hover"]); self.configure(border_width=2, border_color=THEME_COLORS["input_mode_text"])
        else:
            self.mode_lbl.configure(text="ERR", text_color="red"); self.state_lbl.configure(text="UNK", text_color="red"); self.control_btn.configure(text="Error", state="disabled", fg_color="gray", hover_color="gray"); self.configure(border_width=0)

class GPIOPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTk, controller: MainApplication, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=THEME_COLORS["background_main"], **kwargs)
        self.controller = controller
        self.pin_display_widgets: Dict[int, PinDisplayWidget] = {}
        self.active_devices: Dict[int, _Device] = {}
        self.pulse_threads: Dict[int, Dict[str, Any]] = {}
        self.is_updating: bool = False
        
        # --- MODIFIED: Use a dictionary for state persistence ---
        self.persistent_pins: Dict[int, Dict[str, Any]] = {}
        self.state_file_path = os.path.join(controller.app_dir, GPIO_STATE_FILE)

        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        header_frame = ctk.CTkFrame(self, fg_color="transparent"); header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5)); header_frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(header_frame, text="GPIO Control Panel", font=FONTS["header"], text_color=THEME_COLORS["header_text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header_frame, text="Back to Home", command=lambda: self.controller.show_page("HomePage")).grid(row=0, column=1, sticky="e", padx=10)
        grid_container = ctk.CTkScrollableFrame(self, fg_color="transparent"); grid_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=10); grid_container.grid_columnconfigure((0, 1), weight=1)
        
        if not GPIO_AVAILABLE: ctk.CTkLabel(grid_container, text="GPIO LIBRARIES UNAVAILABLE...", font=FONTS["sub_header"], text_color="orange").grid(row=0, column=0, columnspan=2, pady=50, sticky="nsew")
        
        for pin_info in PIN_CONFIG:
            row, col = (pin_info.physical_pin - 1) // 2, (pin_info.physical_pin - 1) % 2
            pin_widget = PinDisplayWidget(grid_container, pin_info, gpio_page=self, open_setup_window_command=self.open_pin_setup_window); pin_widget.grid(row=row, column=col, padx=10, pady=4, sticky="ew")
            if pin_info.bcm is not None: self.pin_display_widgets[pin_info.bcm] = pin_widget
        
        for pin_widget in self.pin_display_widgets.values(): pin_widget.update_status(device=None)

        self._load_pin_states() # --- NEW: Load states on startup

    # --- NEW: Method to handle validated requests from the controller ---
    def handle_ai_gpio_request(self, bcm_pin: int, state: str) -> Tuple[bool, str]:
        """Handles a validated request to set a GPIO pin's state."""
        if not GPIO_AVAILABLE:
            return False, "GPIO libraries are not available."
            
        if bcm_pin not in self.active_devices:
            return False, f"Pin {bcm_pin} is not currently configured. Please set it to OUTPUT mode first."

        device = self.active_devices[bcm_pin]
        if not isinstance(device, LED):
            return False, f"Pin {bcm_pin} is not configured as an OUTPUT. Current mode is {type(device).__name__}."
        
        try:
            if state.lower() == 'high':
                device.on()
                msg = f"Successfully set BCM Pin {bcm_pin} to HIGH."
            elif state.lower() == 'low':
                device.off()
                msg = f"Successfully set BCM Pin {bcm_pin} to LOW."
            else:
                return False, f"Invalid state '{state}'. Use 'high' or 'low'."
            
            self.save_persistent_states() # Save state if it's a persistent pin
            logger.info(msg)
            return True, msg
        except Exception as e:
            error_msg = f"Failed to set state for BCM Pin {bcm_pin}: {e}"
            logger.error(error_msg)
            return False, error_msg

    # --- NEW: Methods to manage loading and saving pin states to a file ---
    def _load_pin_states(self):
        if not GPIO_AVAILABLE:
            return
        try:
            if os.path.exists(self.state_file_path):
                with open(self.state_file_path, 'r') as f:
                    self.persistent_pins = {int(k): v for k, v in json.load(f).items()}
                
                logger.info(f"Loaded {len(self.persistent_pins)} persistent pin states.")
                
                for bcm_pin, state_info in self.persistent_pins.items():
                    mode_str = state_info.get("mode")
                    if mode_str:
                        try:
                            mode = PinMode[mode_str]
                            self.setup_pin(bcm_pin, mode, from_load=True) # Prevent re-saving during load
                            
                            # Apply the saved state after setup
                            device = self.active_devices.get(bcm_pin)
                            if device:
                                saved_state = state_info.get("state")
                                if mode == PinMode.OUTPUT and isinstance(device, LED):
                                    if saved_state == "HIGH": device.on()
                                    else: device.off()
                                elif mode == PinMode.PWM and isinstance(device, PWMLED):
                                    device.value = float(saved_state)
                        except Exception as e:
                            logger.error(f"Failed to restore state for pin {bcm_pin}: {e}")
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Could not load GPIO state file: {e}")

    def save_persistent_states(self):
        """Saves the current state of all pins marked as persistent."""
        if not GPIO_AVAILABLE: return
        
        pins_to_save = {}
        for bcm_pin in self.persistent_pins.keys():
            if bcm_pin in self.active_devices:
                device = self.active_devices[bcm_pin]
                state_info = self.persistent_pins[bcm_pin].copy() # Start with existing info
                
                if isinstance(device, PWMLED):
                    state_info["state"] = round(device.value, 4)
                elif isinstance(device, LED):
                    state_info["state"] = "HIGH" if device.is_lit else "LOW"
                # Input pins have no savable state
                
                pins_to_save[bcm_pin] = state_info

        try:
            with open(self.state_file_path, 'w') as f:
                json.dump(pins_to_save, f, indent=4)
            logger.info(f"Saved {len(pins_to_save)} persistent pin states.")
        except IOError as e:
            logger.error(f"Could not save GPIO state file: {e}")

    def start_updates(self):
        if self.is_updating: return
        self.is_updating = True; logger.info("Starting GPIO status updates."); self._update_pin_statuses_loop()

    def stop_updates(self):
        if self.is_updating: logger.info("Stopping GPIO status updates."); self.is_updating = False

    def _update_pin_statuses_loop(self):
        if not self.is_updating: return
        for bcm_pin, pin_widget in self.pin_display_widgets.items():
            pin_widget.update_status(device=self.active_devices.get(bcm_pin), is_pulsing=self.is_pin_pulsing(bcm_pin))
        self.after(UPDATE_INTERVAL_MS, self._update_pin_statuses_loop)

    def on_hide(self):
        logger.info("GPIO page hidden. Stopping updates and saving persistent states.")
        self.stop_updates()
        self.save_persistent_states() # Save final states before hiding
        # Pins are no longer cleaned up on hide. They remain active until app exit or explicit release.
        self.controller.close_active_toplevel()

    def on_show(self):
        logger.info("GPIO page shown. Restarting UI updates."); self.start_updates()
    
    def cleanup_pin(self, bcm_pin: int):
        self.stop_pulse(bcm_pin)
        if bcm_pin in self.active_devices:
            try:
                if Device is not None and isinstance(self.active_devices[bcm_pin], Device): self.active_devices[bcm_pin].close()
                del self.active_devices[bcm_pin]; logger.info(f"Released BCM pin {bcm_pin}.")
            except Exception as e: logger.error(f"Error releasing BCM pin {bcm_pin}: {e}")
        
        self.persistent_pins.pop(bcm_pin, None)
        self.save_persistent_states() # Save after removing persistence
        
        if bcm_pin in self.pin_display_widgets: self.pin_display_widgets[bcm_pin].update_status(device=None)
    
    def set_pin_persistence(self, bcm_pin: int, is_persistent: bool) -> None:
        if is_persistent:
            self.persistent_pins[bcm_pin] = {"is_persistent": True}
            logger.info(f"BCM pin {bcm_pin} set to be persistent.")
        else:
            self.persistent_pins.pop(bcm_pin, None)
            logger.info(f"BCM pin {bcm_pin} persistence disabled.")
        self.save_persistent_states()

    def is_pin_persistent(self, bcm_pin: int) -> bool:
        return bcm_pin in self.persistent_pins

    def open_pin_setup_window(self, pin_info: PinInfo) -> None:
        self.stop_updates(); self.controller.close_active_toplevel()
        popup = PinSetupWindow(self.controller, self, pin_info); self.controller.active_toplevel = popup
    
    def setup_pin(self, bcm_pin: int, mode: PinMode, from_load: bool = False) -> None:
        if bcm_pin in self.active_devices and isinstance(self.active_devices[bcm_pin], (LED, PWMLED, Button)):
            logger.info(f"Pin {bcm_pin} already configured. Skipping setup.")
        else:
            self.cleanup_pin(bcm_pin)

        if not GPIO_AVAILABLE:
            if not from_load: messagebox.showerror("GPIO Error", "GPIO libraries are not available.", parent=self)
            return

        try:
            device: Optional[_Device] = None
            if mode == PinMode.OUTPUT: device = LED(bcm_pin); self.pin_display_widgets[bcm_pin].control_btn.configure(command=partial(self.open_output_control, bcm_pin, device))
            elif mode == PinMode.INPUT: device = Button(bcm_pin)
            elif mode == PinMode.PWM: device = PWMLED(bcm_pin); self.pin_display_widgets[bcm_pin].control_btn.configure(command=partial(self.open_pwm_control, bcm_pin, device))
            
            if device: 
                self.active_devices[bcm_pin] = device
                logger.info(f"Set BCM pin {bcm_pin} as {mode.value}.")
                if self.is_pin_persistent(bcm_pin):
                    self.persistent_pins[bcm_pin]['mode'] = mode.name
                    if not from_load: self.save_persistent_states()
                self.pin_display_widgets[bcm_pin].update_status(device=device)
            else: 
                raise RuntimeError(f"Failed to create device for BCM pin {bcm_pin} with mode {mode.value}.")
        except Exception as e:
            if not from_load: messagebox.showerror("GPIO Error", f"Failed to set up pin {bcm_pin} as {mode.value}:\n{e}", parent=self)
            logger.error(f"Error setting up BCM pin {bcm_pin} as {mode.value}: {e}")
            self.cleanup_pin(bcm_pin)
            if bcm_pin in self.pin_display_widgets: self.pin_display_widgets[bcm_pin].update_status(device=None)

    def open_output_control(self, bcm_pin: int, device: _LED) -> None:
        self.stop_updates(); self.controller.close_active_toplevel()
        popup = OutputControlWindow(self.controller, self, bcm_pin, device); self.controller.active_toplevel = popup
    def open_pwm_control(self, bcm_pin: int, device: _PWMLED) -> None:
        self.stop_updates(); self.controller.close_active_toplevel()
        popup = PwmControlWindow(self.controller, self, bcm_pin, device); self.controller.active_toplevel = popup

    def _pulse_loop(self, device: _LED, interval: float, stop_event: threading.Event) -> None:
        if not GPIO_AVAILABLE or LED is None or not isinstance(device, LED): logger.error(f"Pulse loop started with non-LED device. Terminating."); return
        try:
            while not stop_event.is_set(): device.toggle(); stop_event.wait(interval)
            device.off()
        except Exception as e: logger.error(f"Error in pulse loop: {e}"); device.off()
    
    def start_pulse(self, bcm_pin: int, device: _LED, interval: float) -> None:
        self.stop_pulse(bcm_pin); logger.info(f"Starting pulse on BCM pin {bcm_pin} with interval {interval:.3f}s.")
        stop_event = threading.Event(); thread = threading.Thread(target=self._pulse_loop, args=(device, interval, stop_event), daemon=True)
        self.pulse_threads[bcm_pin] = {'thread': thread, 'stop_event': stop_event}; thread.start()
        if isinstance(self.controller.active_toplevel, OutputControlWindow) and self.controller.active_toplevel.bcm_pin == bcm_pin: self.controller.active_toplevel._update_pulse_button_state()
    
    def stop_pulse(self, bcm_pin: int) -> None:
        if bcm_pin in self.pulse_threads:
            logger.info(f"Stopping pulse on BCM pin {bcm_pin}."); self.pulse_threads[bcm_pin]['stop_event'].set()
            thread_to_join = self.pulse_threads[bcm_pin]['thread']; thread_to_join.join(timeout=1.0)
            if thread_to_join.is_alive(): logger.warning(f"Pulse thread for BCM pin {bcm_pin} did not terminate in time.")
            del self.pulse_threads[bcm_pin]
            if isinstance(self.controller.active_toplevel, OutputControlWindow) and self.controller.active_toplevel.bcm_pin == bcm_pin: self.controller.active_toplevel._update_pulse_button_state()
            if bcm_pin in self.active_devices and LED is not None and isinstance(self.active_devices[bcm_pin], LED):
                try: self.active_devices[bcm_pin].off()
                except Exception as e: logger.error(f"Error turning off LED for BCM pin {bcm_pin} after stopping pulse: {e}")
    
    def is_pin_pulsing(self, bcm_pin: int) -> bool:
        return bcm_pin in self.pulse_threads

    def full_cleanup(self) -> None:
        logger.info("Performing full GPIO cleanup.")
        self.stop_updates()
        for pin in list(self.pulse_threads.keys()):
            self.stop_pulse(pin)
        for pin in list(self.active_devices.keys()):
            self.cleanup_pin(pin)
        self.persistent_pins.clear() # Clear all persistence
        self.save_persistent_states() # Save empty state
        if GPIO_AVAILABLE and Device is not None:
            try:
                # This is a more aggressive cleanup for gpiozero
                # It closes all devices opened by the current pin factory
                Device.close_all()
                logger.info("gpiozero.Device.close_all() called.")
            except Exception as e:
                logger.error(f"Error during gpiozero.Device.close_all(): {e}")