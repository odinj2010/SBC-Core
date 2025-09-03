# pages/comms_page.py
import customtkinter as ctk  # Import the CustomTkinter library for modern GUI elements
from tkinter import messagebox, filedialog  # Import standard Tkinter dialogs for messages and file selection
import logging  # Import logging for debugging and tracking application events
import threading  # Import threading for running long operations in the background to keep the UI responsive
import tempfile  # Import tempfile for creating temporary files securely

# --- Conditional Imports for Crypto and Steganography ---
# These imports are wrapped in try-except blocks to allow the application to run
# even if these external libraries are not installed.
CRYPTO_AVAILABLE = False  # Flag to track if cryptography library is available
try:
    from cryptography.fernet import Fernet, InvalidToken  # For symmetric encryption/decryption
    from cryptography.hazmat.primitives import hashes  # For cryptographic hashing (e.g., SHA256)
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # For Password-Based Key Derivation Function 2
    import base64  # For encoding binary data to text (URL-safe)
    import os  # For interacting with the operating system, like generating random bytes
    CRYPTO_AVAILABLE = True  # Set flag to True if all crypto imports succeed
except ImportError:
    # If any cryptography-related library is missing, this block is executed.
    # The CRYPTO_AVAILABLE flag remains False, and functionality will be disabled.
    pass

STEGANO_AVAILABLE = False  # Flag to track if steganography library is available
try:
    from steganography.steganography import Steganography  # For hiding/revealing files within images
    from PIL import Image  # Pillow library, often a dependency for steganography, for image manipulation
    STEGANO_AVAILABLE = True  # Set flag to True if all steganography imports succeed
except ImportError:
    # If any steganography-related library is missing, this block is executed.
    # The STEGANO_AVAILABLE flag remains False, and functionality will be disabled.
    pass

logger = logging.getLogger(__name__)  # Initialize logger for this module

# --- UI Constants ---
# Define color and font constants for a consistent UI theme, inspired by a "Pip-Boy" style
PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME = "#2a2d2e"
MAIN_BG_COLOR = "#1a1a1a"
TEXT_FONT = ("Arial", 12)  # Custom font for terminal-like appearance

class CommsPage(ctk.CTkFrame):
    """
    A CustomTkinter frame representing the Secure Communications page of the application.
    This page includes functionalities for encrypted text communication and digital dead drops
    (steganography with encryption).
    """
    def __init__(self, parent, controller):
        """
        Initializes the CommsPage.

        Args:
            parent (ctk.CTkFrame): The parent widget this page belongs to.
            controller (AppController): The main application controller for navigation.
        """
        super().__init__(parent, fg_color=MAIN_BG_COLOR)  # Call the CTkFrame constructor
        self.controller = controller  # Store the controller for page navigation
        self.is_processing = False  # Flag to prevent multiple simultaneous hide/reveal operations

        # Configure the grid layout for the page
        self.grid_columnconfigure(0, weight=1)  # Allow the central column to expand horizontally
        self.grid_rowconfigure(1, weight=1)     # Allow the content area (tab view) to expand vertically

        # --- Header Section ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=10, pady=10, sticky="ew") # Place header at the top
        header.columnconfigure(0, weight=1) # Allow the header label to expand

        # Title label for the page
        ctk.CTkLabel(header, text="SECURE COMMS", font=("Arial", 20, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        # Button to navigate back to the home page
        ctk.CTkButton(header, text="Back to Home", command=lambda: self.controller.show_page("HomePage")).grid(row=0, column=1, sticky="e")

        # --- Tab View for Different Communication Modes ---
        self.tab_view = ctk.CTkTabview(self, fg_color=PIPBOY_FRAME)
        self.tab_view.add("Encrypted Terminal")  # First tab for text encryption/decryption
        self.tab_view.add("Digital Dead Drop")   # Second tab for steganography
        self.tab_view.grid(row=1, column=0, sticky="nsew", padx=10, pady=10) # Place tab view below header, expanding

        # Call setup methods for each tab's content
        self._setup_crypto_tab()
        self._setup_stegano_tab()

    def _setup_crypto_tab(self):
        """
        Sets up the 'Encrypted Terminal' tab with widgets for text encryption and decryption.
        """
        tab = self.tab_view.tab("Encrypted Terminal") # Get reference to the tab frame
        tab.grid_columnconfigure(0, weight=1) # Allow the main column to expand
        tab.grid_rowconfigure(1, weight=1)    # Allow input textbox to expand
        tab.grid_rowconfigure(3, weight=1)    # Allow output textbox to expand

        # --- Input Frame ---
        # Frame for the plaintext/ciphertext input textbox
        input_frame = ctk.CTkFrame(tab, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(0, weight=1)
        # Label for the input area
        ctk.CTkLabel(tab, text="Plaintext / Ciphertext Input", font=TEXT_FONT).grid(row=0, column=0, sticky="w", padx=10, pady=(10,0))
        # Textbox for user input (plaintext to encrypt or ciphertext to decrypt)
        self.crypto_input_text = ctk.CTkTextbox(input_frame, wrap="word", font=TEXT_FONT)
        self.crypto_input_text.pack(fill="both", expand=True)

        # --- Controls Frame ---
        # Frame containing password entry and action buttons
        controls_frame = ctk.CTkFrame(tab, fg_color="transparent")
        controls_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        controls_frame.grid_columnconfigure(1, weight=1) # Allow password entry to expand
        # Label for the password field
        ctk.CTkLabel(controls_frame, text="Password:", font=TEXT_FONT).grid(row=0, column=0, padx=5)
        # Entry widget for the encryption/decryption password, characters are hidden with '*'
        self.password_entry = ctk.CTkEntry(controls_frame, show="*")
        self.password_entry.grid(row=0, column=1, sticky="ew")
        # Button to initiate encryption
        ctk.CTkButton(controls_frame, text="Encrypt", command=self.encrypt_text).grid(row=0, column=2, padx=5)
        # Button to initiate decryption
        ctk.CTkButton(controls_frame, text="Decrypt", command=self.decrypt_text).grid(row=0, column=3, padx=5)

        # --- Output Frame ---
        # Frame for the encryption/decryption output textbox
        output_frame = ctk.CTkFrame(tab, fg_color="transparent")
        output_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        output_frame.grid_columnconfigure(0, weight=1)
        output_frame.grid_rowconfigure(0, weight=1)
        # Textbox to display the output (ciphertext or decrypted plaintext), initially disabled for read-only
        self.crypto_output_text = ctk.CTkTextbox(output_frame, wrap="word", font=TEXT_FONT, state="disabled")
        self.crypto_output_text.pack(fill="both", expand=True)

        # Display a warning if the cryptography library is not available
        if not CRYPTO_AVAILABLE:
            self.crypto_input_text.insert("1.0", "Cryptography library not found.\nPlease run: pip install cryptography")
            self.crypto_input_text.configure(state="disabled") # Disable input if crypto is missing

    def _setup_stegano_tab(self):
        """
        Sets up the 'Digital Dead Drop' tab with widgets for steganography operations.
        """
        tab = self.tab_view.tab("Digital Dead Drop") # Get reference to the tab frame
        tab.grid_columnconfigure(0, weight=1) # Allow the main column to expand
        tab.grid_rowconfigure(1, weight=1)    # Allow content to expand

        # Frame for the Hide/Reveal buttons
        controls_frame = ctk.CTkFrame(tab, fg_color="transparent")
        controls_frame.pack(pady=10, fill="x", padx=10)
        # Button to hide data in an image
        self.hide_button = ctk.CTkButton(controls_frame, text="Hide Data in Image", command=self.hide_data)
        self.hide_button.pack(side="left", expand=True, padx=5)
        # Button to reveal data from an image
        self.reveal_button = ctk.CTkButton(controls_frame, text="Reveal Data from Image", command=self.reveal_data)
        self.reveal_button.pack(side="left", expand=True, padx=5)
        
        # Label to display the status of steganography operations
        self.stegano_status_label = ctk.CTkLabel(tab, text="Status: Ready", font=TEXT_FONT, wraplength=400)
        self.stegano_status_label.pack(pady=10)

        # Display a warning if steganography or Pillow libraries are not available
        if not STEGANO_AVAILABLE:
             self.stegano_status_label.configure(text="Steganography or Pillow library not found.\nPlease run: pip install steganography Pillow")

    def _get_key_from_password(self, password: str, salt: bytes) -> bytes:
        """
        Derives a cryptographic key from a user-provided password and a salt using PBKDF2HMAC.
        This makes the encryption more secure by converting a human-memorable password into a
        strong, fixed-length key, and using a unique salt to prevent rainbow table attacks.

        Args:
            password (str): The user's password.
            salt (bytes): A random, unique salt bytes.

        Returns:
            bytes: The URL-safe base64 encoded derived key (32 bytes).
        """
        # PBKDF2HMAC is a key derivation function that stretches a password using a salt
        # and a high iteration count to make brute-force attacks computationally expensive.
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),  # Use SHA256 as the hashing algorithm
            length=32,                  # Derive a 32-byte key (suitable for Fernet)
            salt=salt,                  # Unique salt for each key derivation
            iterations=100000           # High iteration count for security
        )
        # Derive the key from the password and encode it to a URL-safe base64 format,
        # which is required by Fernet.
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def encrypt_text(self):
        """
        Encrypts the text from the input textbox using a password and displays the ciphertext
        in the output textbox.
        """
        if not CRYPTO_AVAILABLE: # If crypto library is not loaded, exit
            messagebox.showerror("Error", "Cryptography library not available.", parent=self)
            return

        password = self.password_entry.get()
        plaintext = self.crypto_input_text.get("1.0", "end-1c") # Get all text from input textbox, excluding the final newline

        # Validate that both password and plaintext are provided
        if not password or not plaintext:
            messagebox.showwarning("Input Required", "Password and input text are required.", parent=self)
            return
        
        salt = os.urandom(16) # Generate a 16-byte random salt for key derivation
        key = self._get_key_from_password(password, salt) # Derive a secure key from the password and salt
        f = Fernet(key) # Initialize Fernet cipher with the derived key
        encrypted_data = f.encrypt(plaintext.encode()) # Encrypt the plaintext (must be bytes)
        
        # Combine the salt and the encrypted data. The salt is prepended so it can be extracted
        # during decryption. The combined data is then URL-safe base64 encoded for easy storage/transport.
        output = base64.urlsafe_b64encode(salt + encrypted_data).decode()
        
        # Update the output textbox with the encrypted data
        self.crypto_output_text.configure(state="normal") # Enable textbox to insert text
        self.crypto_output_text.delete("1.0", "end")      # Clear previous content
        self.crypto_output_text.insert("1.0", output)     # Insert the new ciphertext
        self.crypto_output_text.configure(state="disabled") # Disable textbox again (read-only)

    def decrypt_text(self):
        """
        Decrypts the ciphertext from the input textbox using a password and displays the plaintext
        in the output textbox.
        """
        if not CRYPTO_AVAILABLE: # If crypto library is not loaded, exit
            messagebox.showerror("Error", "Cryptography library not available.", parent=self)
            return

        password = self.password_entry.get()
        ciphertext = self.crypto_input_text.get("1.0", "end-1c") # Get all text from input textbox

        # Validate that both password and ciphertext are provided
        if not password or not ciphertext:
            messagebox.showwarning("Input Required", "Password and input text are required.", parent=self)
            return

        try:
            # Decode the base64-encoded ciphertext to get the raw bytes
            data = base64.urlsafe_b64decode(ciphertext)
            # Extract the salt (first 16 bytes) and the actual encrypted data
            salt, encrypted_data = data[:16], data[16:]
            key = self._get_key_from_password(password, salt) # Derive the key using the password and the extracted salt
            f = Fernet(key) # Initialize Fernet cipher with the derived key
            decrypted_data = f.decrypt(encrypted_data).decode() # Decrypt the data and decode it back to a string
            
            # Update the output textbox with the decrypted data
            self.crypto_output_text.configure(state="normal")
            self.crypto_output_text.delete("1.0", "end")
            self.crypto_output_text.insert("1.0", decrypted_data)
            self.crypto_output_text.configure(state="disabled")
        except (InvalidToken, TypeError, ValueError):
            # Catch specific errors related to decryption failure (e.g., wrong password, corrupted data)
            messagebox.showerror("Decryption Failed", "Invalid password or corrupted data.", parent=self)
        except Exception as e:
            # Catch any other unexpected errors during decryption
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self)

    def _toggle_buttons(self, enabled: bool):
        """
        Enables or disables the main action buttons in the Digital Dead Drop tab
        to prevent users from initiating multiple operations simultaneously.

        Args:
            enabled (bool): True to enable buttons, False to disable them.
        """
        state = "normal" if enabled else "disabled"
        self.hide_button.configure(state=state)
        self.reveal_button.configure(state=state)

    def hide_data(self):
        """
        Initiates the process of hiding a selected file within an image.
        It prompts the user for paths, an encryption password, and then starts
        a background thread for the intensive operation to keep the UI responsive.
        """
        # Check if necessary libraries are available and if another process is already running
        if not STEGANO_AVAILABLE:
            messagebox.showerror("Error", "Steganography library not available.", parent=self)
            return
        if not CRYPTO_AVAILABLE:
            messagebox.showerror("Error", "Cryptography library not available.", parent=self)
            return
        if self.is_processing:
            messagebox.showwarning("In Progress", "Another operation is already running. Please wait.", parent=self)
            return
        
        # --- File Selection Dialogs ---
        carrier_path = filedialog.askopenfilename(title="Select Carrier Image", filetypes=[("Image Files", "*.png *.bmp")])
        if not carrier_path: return # User cancelled

        secret_path = filedialog.askopenfilename(title="Select File to Hide")
        if not secret_path: return # User cancelled

        output_path = filedialog.asksaveasfilename(title="Save New Image As", defaultextension=".png", filetypes=[("PNG Image", "*.png")])
        if not output_path: return # User cancelled
        
        # --- Password Input ---
        password_dialog = ctk.CTkInputDialog(text="Enter a password to encrypt the secret file:", title="Encryption")
        password = password_dialog.get_input()
        if not password: return # User cancelled or entered empty password

        self.is_processing = True       # Set flag to indicate an operation is in progress
        self._toggle_buttons(False)     # Disable buttons to prevent re-triggering
        # Start a new thread for the long-running operation to avoid freezing the GUI
        threading.Thread(target=self._hide_data_thread, args=(carrier_path, secret_path, output_path, password), daemon=True).start()

    def _hide_data_thread(self, carrier_path, secret_path, output_path, password):
        """
        Performs the actual hiding of encrypted data within an image in a separate thread.
        This includes reading the secret file, encrypting it, writing to a temporary file,
        and then embedding the temporary file into the carrier image using steganography.
        Updates the UI status and handles errors.
        """
        temp_secret_path = None # Variable to store the path of the temporary encrypted file
        try:
            # Update UI status (using self.after to ensure thread-safe UI updates)
            self.after(0, self.stegano_status_label.configure, {"text": "Status: Reading secret file..."})
            with open(secret_path, 'rb') as f: # Read the secret file in binary mode
                plaintext = f.read()

            self.after(0, self.stegano_status_label.configure, {"text": "Status: Encrypting data..."})
            salt = os.urandom(16) # Generate a fresh salt for this encryption
            key = self._get_key_from_password(password, salt) # Derive key from password and salt
            f = Fernet(key) # Initialize Fernet cipher
            encrypted_data = f.encrypt(plaintext) # Encrypt the secret file's content
            data_to_hide = salt + encrypted_data # Prepend salt to encrypted data

            # Write the combined (salt + encrypted) data to a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(data_to_hide)
                temp_secret_path = temp_file.name # Store temp file path for steganography

            self.after(0, self.stegano_status_label.configure, {"text": "Status: Hiding encrypted data in image..."})
            # Use the steganography library to encode the temporary file into the carrier image
            Steganography.encode(carrier_path, temp_secret_path, output_path)
            
            # Update UI with success message
            success_msg = f"Success! Data from {os.path.basename(secret_path)} encrypted and hidden in {os.path.basename(output_path)}"
            self.after(0, self.stegano_status_label.configure, {"text": success_msg})
            self.after(0, messagebox.showinfo, "Success", "Data hidden successfully!", {"parent": self})
        except Exception as e:
            # Handle any errors during the process and display an error message
            error_msg = f"Error: {e}"
            self.after(0, self.stegano_status_label.configure, {"text": error_msg})
            self.after(0, messagebox.showerror, "Error", f"Failed to hide data: {e}", {"parent": self})
        finally:
            # This block always executes, ensuring cleanup and UI state reset
            if temp_secret_path and os.path.exists(temp_secret_path):
                os.remove(temp_secret_path) # Delete the temporary file
            self.is_processing = False # Reset processing flag
            self.after(0, self._toggle_buttons, True) # Re-enable buttons

    def reveal_data(self):
        """
        Initiates the process of revealing hidden data from a selected image.
        It prompts the user for paths, a decryption password, and then starts
        a background thread for the intensive operation to keep the UI responsive.
        """
        # Check if necessary libraries are available and if another process is already running
        if not STEGANO_AVAILABLE:
            messagebox.showerror("Error", "Steganography library not available.", parent=self)
            return
        if not CRYPTO_AVAILABLE:
            messagebox.showerror("Error", "Cryptography library not available.", parent=self)
            return
        if self.is_processing:
            messagebox.showwarning("In Progress", "Another operation is already running. Please wait.", parent=self)
            return

        # --- File Selection Dialogs ---
        carrier_path = filedialog.askopenfilename(title="Select Image with Hidden Data", filetypes=[("Image Files", "*.png *.bmp")])
        if not carrier_path: return # User cancelled

        output_path = filedialog.asksaveasfilename(title="Save Revealed File As", defaultextension=".txt")
        if not output_path: return # User cancelled

        # --- Password Input ---
        password_dialog = ctk.CTkInputDialog(text="Enter password to decrypt the hidden file:", title="Decryption")
        password = password_dialog.get_input()
        if not password: return # User cancelled or entered empty password

        self.is_processing = True       # Set flag to indicate an operation is in progress
        self._toggle_buttons(False)     # Disable buttons to prevent re-triggering
        # Start a new thread for the long-running operation to avoid freezing the GUI
        threading.Thread(target=self._reveal_data_thread, args=(carrier_path, output_path, password), daemon=True).start()

    def _reveal_data_thread(self, carrier_path, output_path, password):
        """
        Performs the actual revealing of data from an image and decryption in a separate thread.
        This includes extracting the hidden data to a temporary file, reading the encrypted payload,
        decrypting it, and writing the final decrypted data to the output file.
        Updates the UI status and handles errors.
        """
        temp_revealed_path = None # Variable to store the path of the temporary extracted file
        try:
            self.after(0, self.stegano_status_label.configure, {"text": "Status: Revealing data from image..."})
            # Create a temporary file to store the extracted data from the image
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_revealed_path = temp_file.name
            
            # Use the steganography library to decode (extract) the hidden data
            # from the carrier image into the temporary file.
            Steganography.decode(carrier_path, temp_revealed_path)

            self.after(0, self.stegano_status_label.configure, {"text": "Status: Reading encrypted data..."})
            with open(temp_revealed_path, 'rb') as f: # Read the extracted (encrypted) data from the temp file
                encrypted_payload = f.read()

            self.after(0, self.stegano_status_label.configure, {"text": "Status: Decrypting data..."})
            # Separate the salt (first 16 bytes) from the actual encrypted data
            salt, encrypted_data = encrypted_payload[:16], encrypted_payload[16:]
            key = self._get_key_from_password(password, salt) # Derive key using the password and the extracted salt
            f = Fernet(key) # Initialize Fernet cipher
            decrypted_data = f.decrypt(encrypted_data) # Decrypt the data

            with open(output_path, 'wb') as f: # Write the final decrypted data to the user-specified output file
                f.write(decrypted_data)

            # Update UI with success message
            success_msg = f"Success! Revealed data saved to {os.path.basename(output_path)}"
            self.after(0, self.stegano_status_label.configure, {"text": success_msg})
            self.after(0, messagebox.showinfo, "Success", "Data revealed successfully!", {"parent": self})
        except (InvalidToken, TypeError, ValueError):
            # Handle decryption specific errors (wrong password, corrupted data)
            error_msg = "Error: Decryption failed. Invalid password or corrupted data."
            self.after(0, self.stegano_status_label.configure, {"text": error_msg})
            self.after(0, messagebox.showerror, "Decryption Failed", "Invalid password or corrupted data.", {"parent": self})
        except Exception as e:
            # Handle any other unexpected errors
            error_msg = f"Error: {e}"
            self.after(0, self.stegano_status_label.configure, {"text": error_msg})
            self.after(0, messagebox.showerror, "Error", f"Failed to reveal data: {e}", {"parent": self})
        finally:
            # This block always executes, ensuring cleanup and UI state reset
            if temp_revealed_path and os.path.exists(temp_revealed_path):
                os.remove(temp_revealed_path) # Delete the temporary file
            self.is_processing = False # Reset processing flag
            self.after(0, self._toggle_buttons, True) # Re-enable buttons