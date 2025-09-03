# pages/settings_page.py
import tkinter as tk
import customtkinter as ctk
import os
import sys
import subprocess
import logging
import threading
import time
from tkinter import messagebox
from .sandbox_page import SandboxPage

# --- GPIO Library Handling for Morse Code ---
try:
    from gpiozero import LED, GPIOZeroError
    GPIO_AVAILABLE = True
except (ImportError, OSError):
    GPIO_AVAILABLE = False
    # Create dummy classes if gpiozero is not available
    class LED:
        def __init__(self, *args, **kwargs): pass
        def on(self): pass
        def off(self): pass
        def close(self): pass
    class GPIOZeroError(Exception):
        pass

logger = logging.getLogger(__name__)

# --- Constants ---
PIPBOY_GREEN = "#32f178"

# Morse Code Dictionary
MORSE_CODE_DICT = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '1': '.----', '2': '..---', '3': '...--', '4': '....-', '5': '.....',
    '6': '-....', '7': '--...', '8': '---..', '9': '----.', '0': '-----',
    ', ': '--..--', '.': '.-.-.-', '?': '..--..', '/': '-..-.', '-': '-....-',
    '(': '-.--.', ')': '-.--.-', ' ': '/'
}

class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="#1a1a1a")
        self.controller = controller

        # Morse code state
        self.morse_thread = None
        self.stop_morse_event = threading.Event()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")
        ctk.CTkLabel(header, text="SETTINGS", font=("Arial", 24, "bold"), text_color=PIPBOY_GREEN).pack(side="left")
        ctk.CTkButton(header, text="Back to Home", command=lambda: controller.show_page("HomePage")).pack(side="right")

        # --- Tab View for Organization ---
        self.tab_view = ctk.CTkTabview(self, fg_color="#2a2d2e")
        self.tab_view.add("General")
        self.tab_view.add("AI")
        self.tab_view.add("Tools")
        self.tab_view.add("Emergency") # New Tab
        self.tab_view.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.setup_general_tab()
        self.setup_ai_tab()
        self.setup_tools_tab()
        self.setup_emergency_tab() # Setup the new tab
        
    def on_show(self):
        """Called when page is shown. Ensures settings UI reflects current config."""
        self.update_ai_settings_display()

    def on_hide(self):
        """Called when page is hidden. Ensures background threads are stopped."""
        self.stop_broadcast()

    def setup_general_tab(self):
        tab = self.tab_view.tab("General")
        tab.grid_columnconfigure(0, weight=1)
        
        sys_frame = ctk.CTkFrame(tab, fg_color="#3a3d3e")
        sys_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(sys_frame, text="System Power", font=("Arial", 14, "bold")).pack(pady=(5,10))
        
        ctk.CTkButton(sys_frame, text="Restart Pip-Boy Software", command=self.restart_app).pack(pady=5, fill="x", padx=10)
        ctk.CTkButton(sys_frame, text="Reboot System", fg_color="#b28900", hover_color="#c29500", command=lambda: self._run_command("sudo reboot")).pack(pady=5, fill="x", padx=10)
        ctk.CTkButton(sys_frame, text="Shutdown System", fg_color="#8B0000", hover_color="#AE0000", command=lambda: self._run_command("sudo poweroff")).pack(pady=(5,10), fill="x", padx=10)

    def setup_ai_tab(self):
        tab = self.tab_view.tab("AI")
        tab.grid_columnconfigure(0, weight=1)

        backend_frame = ctk.CTkFrame(tab, fg_color="#3a3d3e")
        backend_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(backend_frame, text="V.I.N.C.E. Cognitive Backend", font=("Arial", 14, "bold")).pack(pady=(5,10))
        
        self.backend_selector = ctk.CTkSegmentedButton(backend_frame, values=["Local", "Gemini"], command=self.on_backend_change)
        self.backend_selector.pack(pady=10, padx=20, fill="x")

        gemini_frame = ctk.CTkFrame(tab, fg_color="#3a3d3e")
        gemini_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(gemini_frame, text="Gemini Configuration", font=("Arial", 14, "bold")).pack(pady=(5,10))
        
        ctk.CTkLabel(gemini_frame, text="Enter your Google AI Studio API Key:", font=("Arial", 12)).pack()
        self.api_key_entry = ctk.CTkEntry(gemini_frame, placeholder_text="Paste API Key here...", show="*", width=400)
        self.api_key_entry.pack(pady=5)
        
        self.api_key_status_label = ctk.CTkLabel(gemini_frame, text="", font=("Arial", 10))
        self.api_key_status_label.pack()
        
        ctk.CTkButton(gemini_frame, text="Save Key", command=self.save_api_key).pack(pady=10)
        
        self.update_ai_settings_display()
        
    def setup_tools_tab(self):
        tab = self.tab_view.tab("Tools")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        
        sandbox_frame = SandboxPage(tab, controller=self.controller, llm=self.controller.llm)
        sandbox_frame.grid(row=0, column=0, sticky="nsew")

    def setup_emergency_tab(self):
        tab = self.tab_view.tab("Emergency")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1) # Allow textbox to expand

        # --- Morse Code Frame ---
        morse_frame = ctk.CTkFrame(tab, fg_color="#3a3d3e")
        morse_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        morse_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(morse_frame, text="Morse Code Broadcaster", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=(5,10))
        
        # --- Config Controls ---
        config_frame = ctk.CTkFrame(morse_frame, fg_color="transparent")
        config_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(config_frame, text="BCM Pin:", font=("Arial", 12)).pack(side="left", padx=(0,5))
        self.morse_pin_entry = ctk.CTkEntry(config_frame, width=60)
        self.morse_pin_entry.insert(0, "23")
        self.morse_pin_entry.pack(side="left", padx=5)

        ctk.CTkLabel(config_frame, text="Dot Duration (ms):", font=("Arial", 12)).pack(side="left", padx=(20,5))
        self.morse_speed_entry = ctk.CTkEntry(config_frame, width=80)
        self.morse_speed_entry.insert(0, "100")
        self.morse_speed_entry.pack(side="left", padx=5)

        # --- Message Entry ---
        ctk.CTkLabel(morse_frame, text="Message to Broadcast:", font=("Arial", 12)).grid(row=2, column=0, columnspan=2, padx=10, pady=(10,0), sticky="w")
        self.morse_message_box = ctk.CTkTextbox(morse_frame, height=150, font=("Arial", 11), wrap="word")
        self.morse_message_box.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.morse_message_box.insert("1.0", "SOS Sunday is going to be hot.")

        # --- Action Buttons ---
        self.broadcast_button = ctk.CTkButton(morse_frame, text="Broadcast Message", fg_color="green", hover_color="#006400", command=self.start_broadcast)
        self.broadcast_button.grid(row=4, column=0, padx=10, pady=10, sticky="ew")

        self.stop_button = ctk.CTkButton(morse_frame, text="Stop Broadcast", fg_color="red", hover_color="#AE0000", command=self.stop_broadcast, state="disabled")
        self.stop_button.grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        if not GPIO_AVAILABLE:
            ctk.CTkLabel(morse_frame, text="gpiozero library not found. Morse code feature disabled.", text_color="orange").grid(row=5, column=0, columnspan=2, pady=5)
            self.broadcast_button.configure(state="disabled")

    def start_broadcast(self):
        if not GPIO_AVAILABLE:
            messagebox.showerror("GPIO Error", "GPIO libraries are not available on this system.", parent=self)
            return

        if self.morse_thread is not None and self.morse_thread.is_alive():
            messagebox.showwarning("In Progress", "A broadcast is already in progress.", parent=self)
            return

        try:
            pin = int(self.morse_pin_entry.get())
            dot_duration_ms = int(self.morse_speed_entry.get())
            if dot_duration_ms <= 0: raise ValueError("Duration must be positive.")
            dot_sec = dot_duration_ms / 1000.0
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for BCM Pin and Dot Duration.", parent=self)
            return

        message = self.morse_message_box.get("1.0", "end-1c").strip().upper()
        if not message:
            messagebox.showwarning("Empty Message", "Cannot broadcast an empty message.", parent=self)
            return

        self.stop_morse_event.clear()
        self.morse_thread = threading.Thread(target=self._morse_code_thread, args=(message, pin, dot_sec), daemon=True)
        self.morse_thread.start()

        self.broadcast_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

    def stop_broadcast(self):
        if self.morse_thread and self.morse_thread.is_alive():
            self.stop_morse_event.set()
            logger.info("Stop event set for Morse code thread.")
        # UI state is updated in the thread's finally block to ensure it happens after the thread finishes.

    def _morse_code_thread(self, message, pin_num, dot_len):
        led = None
        try:
            led = LED(pin_num)
            dash_len = dot_len * 3
            inter_element_gap = dot_len
            inter_letter_gap = dot_len * 3
            word_gap = dot_len * 7

            for char in message:
                if self.stop_morse_event.is_set(): break
                
                code = MORSE_CODE_DICT.get(char)
                if code is None:
                    time.sleep(inter_letter_gap) # Treat unknown chars as a gap
                    continue
                
                if code == '/': # Word space
                    time.sleep(word_gap - inter_letter_gap) # Subtract the upcoming letter gap
                    continue

                for symbol in code:
                    if self.stop_morse_event.is_set(): break
                    led.on()
                    if symbol == '.': time.sleep(dot_len)
                    elif symbol == '-': time.sleep(dash_len)
                    led.off()
                    time.sleep(inter_element_gap)
                
                if not self.stop_morse_event.is_set():
                    time.sleep(inter_letter_gap - inter_element_gap)

        except GPIOZeroError as e:
            logger.error(f"GPIO Error for Morse code: {e}")
            self.after(0, lambda: messagebox.showerror("GPIO Error", f"Failed to control pin {pin_num}.\nIs it valid or already in use?\n\nError: {e}", parent=self))
        except Exception as e:
            logger.error(f"An unexpected error occurred in Morse thread: {e}", exc_info=True)
        finally:
            if led:
                led.off()
                led.close()
            logger.info("Morse code thread finished.")
            # Schedule UI updates to run on the main thread
            self.after(0, self._reset_morse_ui)

    def _reset_morse_ui(self):
        self.broadcast_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    # --- Other Methods (unchanged) ---

    def update_ai_settings_display(self):
        current_backend = self.controller.config.get('AI', 'backend', fallback='local')
        self.backend_selector.set(current_backend.capitalize())
        
        if self.controller.config.get('GEMINI', 'api_key', fallback=''):
            self.api_key_status_label.configure(text="API Key is currently set.", text_color="lightgreen")
        else:
            self.api_key_status_label.configure(text="API Key is not set.", text_color="orange")

    def on_backend_change(self, selection):
        backend = selection.lower()
        
        if backend == 'gemini' and not self.controller.config.get('GEMINI', 'api_key', fallback=''):
            messagebox.showinfo("API Key Required", "To use the Gemini backend, you must first save a Google AI Studio API key.", parent=self)
            self.backend_selector.set("Local")
            return
            
        self.controller.config.set('AI', 'backend', backend)
        self.controller.save_config()
        logger.info(f"AI backend switched to: {backend}")
        
        if "AIPage" in self.controller.pages:
            self.controller.pages["AIPage"]._show_welcome_message()

    def save_api_key(self):
        key = self.api_key_entry.get().strip()
        if not key:
            messagebox.showwarning("Empty Key", "API Key field is empty.", parent=self)
            return
            
        self.controller.config.set('GEMINI', 'api_key', key)
        self.controller.save_config()
        self.api_key_entry.delete(0, 'end')
        self.update_ai_settings_display()
        messagebox.showinfo("Success", "Gemini API Key has been saved successfully.", parent=self)

    def restart_app(self):
        self.stop_broadcast() # Ensure thread is stopped before restarting
        logger.info("Restarting application via settings...")
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception as e:
            messagebox.showerror("Restart Failed", f"Could not restart the application:\n{e}", parent=self)

    def _run_command(self, command):
        if not messagebox.askyesno("Confirm", f"Are you sure you want to {command.split()[-1]} the system?", parent=self):
            return
        try:
            subprocess.Popen(command, shell=True)
        except Exception as e:
            logger.error(f"Failed to run command '{command}': {e}")