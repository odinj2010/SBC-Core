# pages/sandbox_page.py
# This page provides a "sandbox" environment within the application where the AI (or a user)
# can write, save, and execute Python scripts. It's designed to be a safe, isolated space
# using a Python virtual environment to prevent conflicts with the main application's dependencies.

import tkinter as tk # Standard Python GUI library (used for messagebox, though CustomTkinter is primary)
import customtkinter as ctk # CustomTkinter for modern-looking GUI elements
from tkinter import messagebox # Specific module for GUI pop-up messages
import os # Provides a way of using operating system dependent functionality like file paths
import subprocess # Allows spawning new processes, connecting to their input/output/error pipes, and obtaining their return codes
import logging # For logging events, warnings, and errors throughout the module
import threading # For running time-consuming operations (like virtual environment creation) in the background
import sys # Provides access to system-specific parameters and functions, used for OS detection for venv path
from typing import Optional, Any # For type hinting, improving code readability and maintainability

logger = logging.getLogger(__name__) # Get a logger instance for this module

# --- Configuration ---
# Define the base directory for the sandbox. `os.path.expanduser("~/...")` resolves to the user's home directory.
SANDBOX_DIR = os.path.expanduser("~/pipboy_sandbox")

# Dynamically determine the path to the Python executable within the virtual environment
# based on the operating system. This ensures portability between Windows and Unix-like systems.
if sys.platform.startswith('win'):
    VENV_PATH = os.path.join(SANDBOX_DIR, "sandbox-venv") # Path to the virtual environment directory
    VENV_PYTHON = os.path.join(VENV_PATH, "Scripts", "python.exe") # Path to Python executable on Windows
else: # Linux/macOS
    VENV_PATH = os.path.join(SANDBOX_DIR, "sandbox-venv") # Path to the virtual environment directory
    VENV_PYTHON = os.path.join(VENV_PATH, "bin", "python") # Path to Python executable on Linux/macOS

class SandboxPage(ctk.CTkFrame):
    """
    A CustomTkinter page that provides a code editor, save functionality,
    and script execution within an isolated virtual environment (sandbox).
    This allows the AI to generate and test Python code safely.
    """
    def __init__(self, parent: ctk.CTkFrame, controller: Any = None, llm: Any = None) -> None:
        """
        Initializes the SandboxPage.

        Args:
            parent: The CTkFrame widget that contains this page.
            controller: A reference to the main application controller.
            llm: An instance of the Large Language Model (LLM), which might interact
                 with this sandbox (e.g., to write code).
        """
        super().__init__(parent, fg_color="#1a1a1a") # Initialize CTkFrame with a dark background
        
        self.controller = controller # Store the controller reference
        self.llm = llm # Store the LLM instance

        self.columnconfigure(0, weight=1) # Make the single column expandable
        self.rowconfigure(2, weight=1) # Configure row 2 (the code editor) to expand and fill available space

        # --- Controls Frame (Filename, Save, Run Buttons) ---
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(0,5)) # Position at the top
        
        ctk.CTkLabel(control_frame, text="Filename:", font=("Arial", 12)).pack(side="left")
        self.filename_entry = ctk.CTkEntry(control_frame, width=200, font=("Arial", 12))
        self.filename_entry.pack(side="left", padx=5)
        self.filename_entry.insert(0, "myscript.py") # Default filename for the script

        self.save_button = ctk.CTkButton(control_frame, text="Save", command=self.save_script, width=60)
        self.save_button.pack(side="left", padx=5)
        
        self.run_button = ctk.CTkButton(control_frame, text="Run", command=self.run_script, width=60, fg_color="green", hover_color="#006400")
        self.run_button.pack(side="left", padx=5)

        # --- Status and Warning Frame ---
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        # Label to display the status of the virtual environment.
        self.venv_status_label = ctk.CTkLabel(status_frame, text="Checking venv...", font=("Arial", 10, "italic"), text_color="gray")
        self.venv_status_label.pack(side="left")
        
        # Warning label about the nature of script execution.
        warning_label = ctk.CTkLabel(status_frame, text="WARNING: Scripts run here can affect your system.", font=("Arial", 10, "italic"), text_color="orange")
        warning_label.pack(side="right")
        
        # --- Code Editor ---
        # CTkTextbox for writing and displaying Python code.
        self.code_text = ctk.CTkTextbox(self, font=("Consolas", 11), wrap="word", # Monospace font for code
                                        border_color="#32f178", border_width=1, # Pipboy green border
                                        fg_color="#2a2d2e", text_color="#32f178") # Dark background, green text
        self.code_text.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.code_text.insert("1.0", "# V.I.N.C.E. can write Python code here!\n\nprint('Hello from the sandbox!')") # Default code
        
        self.setup_sandbox_environment() # Call method to prepare the sandbox environment

    def setup_sandbox_environment(self) -> None:
        """
        Ensures the sandbox directory exists and checks if the virtual environment
        is ready. If the virtual environment is not found, it triggers its creation
        in a background thread.
        """
        if not os.path.exists(SANDBOX_DIR):
            logger.info(f"Creating sandbox directory at: {SANDBOX_DIR}")
            os.makedirs(SANDBOX_DIR) # Create the sandbox directory if it doesn't exist
        
        # Check if the virtual environment's Python executable exists.
        if not os.path.exists(VENV_PYTHON):
            self.venv_status_label.configure(text="Virtual environment not found. Creating it now...")
            self.run_button.configure(state="disabled") # Disable run button while venv is being created
            # Start venv creation in a separate daemon thread to keep the UI responsive.
            threading.Thread(target=self._create_venv, daemon=True).start()
        else:
            self.venv_status_label.configure(text="Virtual environment is ready.", text_color="lightgreen")

    def _create_venv(self) -> None:
        """
        Contains the actual logic for creating the Python virtual environment.
        This method is designed to be run in a background thread.
        It uses `subprocess.run` to execute the `python -m venv` command.
        """
        try:
            logger.info(f"Running venv creation in {VENV_PATH}")
            # Determine the appropriate Python command based on OS.
            python_cmd = "python3" if not sys.platform.startswith('win') else "python"
            # Execute the venv creation command. `check=True` raises an error on non-zero exit code.
            # `capture_output=True` captures stdout/stderr, `text=True` decodes output as text.
            subprocess.run([python_cmd, "-m", "venv", VENV_PATH], check=True, capture_output=True, text=True)
            logger.info("Successfully created sandbox virtual environment.")
            self.after(0, self.on_venv_created, True) # Call UI update callback on the main thread
        except subprocess.CalledProcessError as e:
            # Handle errors specifically from the subprocess command.
            logger.error(f"Error creating virtual environment: {e.stderr}")
            self.after(0, self.on_venv_created, False, e.stderr) # Pass error message to UI callback
        except Exception as e:
            # Handle any other unexpected errors during venv creation.
            logger.error(f"An unexpected error occurred during venv creation: {e}", exc_info=True)
            self.after(0, self.on_venv_created, False, str(e))

    def on_venv_created(self, success: bool, error_msg: str = "") -> None:
        """
        Callback method executed on the main Tkinter thread after the virtual environment
        creation attempt has finished (either successfully or with an error).
        Updates the UI to reflect the venv status.

        Args:
            success: Boolean indicating if the venv creation was successful.
            error_msg: Any error message encountered during creation.
        """
        if success:
            self.venv_status_label.configure(text="Virtual environment is ready.", text_color="lightgreen")
            self.run_button.configure(state="normal") # Enable run button now that venv is ready
        else:
            self.venv_status_label.configure(text=f"Venv creation failed. See terminal log.", text_color="red")
            # Print the detailed error to the system terminal/log if venv creation failed.
            logger.error(f"--- VENV CREATION FAILED ---\n{error_msg}")

    def save_script(self) -> None:
        """
        Saves the current content of the code editor (CTkTextbox) to a file
        within the sandbox directory. Performs basic filename validation.
        """
        filename = self.filename_entry.get().strip() # Get filename from entry and strip whitespace
        # Basic validation to prevent path traversal or empty filenames.
        if not filename or "/" in filename or "\\" in filename:
            messagebox.showerror("Invalid Filename", "Please enter a valid, simple filename (e.g., 'myscript.py').", parent=self)
            return
        
        filepath = os.path.join(SANDBOX_DIR, filename) # Construct the full path to save the script
        content = self.code_text.get("1.0", "end-1c") # Get all text from the editor, excluding the final newline
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content) # Write the content to the file
            logger.info(f"Script saved successfully to {filepath}")
            messagebox.showinfo("Success", f"Script '{filename}' saved successfully!", parent=self)
        except Exception as e:
            logger.error(f"Failed to save script {filename}: {e}", exc_info=True)
            messagebox.showerror("Save Error", f"Could not save script:\n{e}", parent=self)

    def run_script(self) -> None:
        """
        Executes the currently saved script using the Python interpreter from the
        sandbox's virtual environment. The script runs as a separate subprocess
        and its output will typically appear in the system terminal where the main
        application was launched.
        """
        filename = self.filename_entry.get().strip()
        filepath = os.path.join(SANDBOX_DIR, filename)

        # Check if the script file exists.
        if not os.path.exists(filepath):
            messagebox.showerror("File Not Found", f"The file '{filename}' does not exist. Please save it first.", parent=self)
            return

        # Check if the virtual environment's Python interpreter is available.
        if not os.path.exists(VENV_PYTHON):
            messagebox.showerror("Environment Error", "The sandbox virtual environment is not yet ready. Please wait.", parent=self)
            return
            
        logger.info(f"Executing script via Popen: {VENV_PYTHON} {filepath}")
        # Use `subprocess.Popen` to run the script.
        # `[VENV_PYTHON, filepath]` specifies the interpreter and the script as arguments.
        # `cwd=SANDBOX_DIR` sets the current working directory for the subprocess,
        # which is useful if the script needs to access other files in the sandbox.
        # This runs asynchronously, so the GUI remains responsive.
        subprocess.Popen([VENV_PYTHON, filepath], cwd=SANDBOX_DIR)
