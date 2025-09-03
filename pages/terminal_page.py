# pages/terminal_page.py
import tkinter as tk
import customtkinter as ctk
import threading
import logging
from PIL import Image
import os
import sys

# Conditional import for pexpect based on OS
if sys.platform.startswith('win'):
    pexpect_lib = None # pexpect is not supported on Windows
else:
    try:
        import pexpect as pexpect_lib
    except ImportError:
        pexpect_lib = None

logger = logging.getLogger(__name__)

class TerminalPage(ctk.CTkFrame):
    def __init__(self, parent, controller=None):
        super().__init__(parent, fg_color="#1a1a1a")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.proc = None
        self.controller = controller
        self.buffer = "" # Buffer for incomplete lines

        # --- Header ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, pady=(10,5), sticky="ew")
        header_frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(header_frame, text="SYSTEM LOG & TERMINAL", font=("Arial", 20, "bold"), text_color="#32f178").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header_frame, text="Back to Home", command=lambda: controller.show_page("HomePage")).grid(row=0, column=1, sticky="e", padx=10)

        # --- Text Container ---
        text_container = ctk.CTkFrame(self, fg_color="black", corner_radius=6)
        text_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        text_container.grid_rowconfigure(0, weight=1)
        text_container.grid_columnconfigure(0, weight=1)

        self.output = ctk.CTkTextbox(text_container, font=("Arial", 10), text_color="#32f178", fg_color="transparent", activate_scrollbars=True)
        self.output.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.output.configure(state="disabled")

        # --- CRT OVERLAY ---
        try:
            crt_path = os.path.join(self.controller.ASSETS_DIR, "crt_overlay.png")
            self.crt_image = ctk.CTkImage(Image.open(crt_path), size=(1024, 768))
            crt_label = ctk.CTkLabel(text_container, image=self.crt_image, text="", fg_color="transparent")
            crt_label.place(relwidth=1, relheight=1)
            crt_label.lower(self.output)
        except (FileNotFoundError, Image.UnidentifiedImageError) as e:
            logger.warning(f"Could not load CRT overlay image: {e}")
        
        # --- Entry Box ---
        self.entry = ctk.CTkEntry(self, placeholder_text="Enter command...", font=("Arial", 12), border_color="#2a2d2e", fg_color="#2a2d2e")
        self.entry.grid(row=2, column=0, sticky="ew", padx=10, pady=10, ipady=5)
        self.entry.bind("<Return>", self.send_command)

        # --- Configure Text Tags ---
        self.output.tag_config("COMMAND", foreground="#FFFFFF")
        self.output.tag_config("STDOUT", foreground="#32f178")
        self.output.tag_config("STDERR", foreground="#FF5500")
        self.output.tag_config("DEBUG", foreground="#9D9D9D")
        self.output.tag_config("INFO", foreground="#32f178")
        self.output.tag_config("WARNING", foreground="#FFD700")
        self.output.tag_config("ERROR", foreground="#FF5500")
        self.output.tag_config("CRITICAL", foreground="#000000", background="#FFD700")

        self.start_shell_process()

    def start_shell_process(self):
        if pexpect_lib is None:
            self.write("\n--- FATAL: pexpect library not available. Terminal disabled. ---\n", "CRITICAL")
            return
        try:
            self.proc = pexpect_lib.spawn("/bin/bash", encoding="utf-8", echo=False)
            self.proc.setecho(False)
            threading.Thread(target=self.read_output, daemon=True).start()
        except Exception as e:
            self.write(f"\n--- FATAL: Could not start shell process: {e} ---\n", "CRITICAL")

    def get_history(self, lines=50):
        try:
            if self.output.winfo_exists():
                return '\n'.join(self.output.get("1.0", tk.END).strip().split('\n')[-lines:])
            return "Terminal widget no longer exists."
        except Exception:
            return "Error retrieving terminal history."

    def send_command(self, event=None):
        cmd = self.entry.get().strip()
        if not cmd or not self.proc or not self.proc.isalive(): return
        self.write(f"$ {cmd}\n", "COMMAND")
        self.proc.sendline(cmd)
        self.entry.delete(0, "end")

    def read_output(self):
        if not self.proc: return
        while self.proc.isalive():
            try:
                # Read available data
                data = self.proc.read_nonblocking(size=1024, timeout=0.1)
                if data:
                    # Add new data to the buffer
                    self.buffer += data
                    # Process complete lines from the buffer
                    while '\n' in self.buffer:
                        line, self.buffer = self.buffer.split('\n', 1)
                        self.write(line + '\n', "STDOUT")
            except pexpect_lib.TIMEOUT:
                continue
            except pexpect_lib.EOF:
                # If there's anything left in the buffer, print it
                if self.buffer:
                    self.write(self.buffer + '\n', "STDOUT")
                self.write("\n--- TERMINAL PROCESS TERMINATED ---\n", "ERROR"); break
            except Exception as e:
                self.write(f"\n--- TERMINAL ERROR: {e} ---\n", "ERROR"); break

    def write(self, message, tags=None):
        def _write():
            if not self.output.winfo_exists(): return
            self.output.configure(state="normal")
            self.output.insert(tk.END, message, tags)
            self.output.see(tk.END)
            self.output.configure(state="disabled")
        self.after(0, _write)
    
    def cleanup(self):
        if self.proc and self.proc.isalive():
            logger.info("Closing terminal shell process...")
            self.proc.close(force=True)

class TerminalLoggingHandler(logging.Handler):
    """Redirects the logging module to the terminal widget."""
    def __init__(self, terminal_page):
        super().__init__()
        self.terminal = terminal_page
        self.level_map = {
            logging.DEBUG: "DEBUG", logging.INFO: "INFO",
            logging.WARNING: "WARNING", logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL"
        }
    def emit(self, record):
        tag = self.level_map.get(record.levelno, "INFO")
        try:
            self.terminal.write(self.format(record) + '\n', tag)
        except Exception:
            self.handleError(record)
