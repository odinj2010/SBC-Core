# pages/home_page.py
import customtkinter as ctk
from PIL import Image
import os

# --- Constants ---
PIPBOY_GREEN = "#32f178"

# --- NEW: Helper class for creating a clickable icon widget ---
class IconWidget(ctk.CTkFrame):
    """
    A clickable widget that combines an icon and a label.
    This represents a single button on the home page grid.
    """
    def __init__(self, parent, text, icon_path, command):
        super().__init__(parent, fg_color="transparent", corner_radius=10)
        self.command = command

        # --- Style ---
        self.configure(fg_color="#2a2d2e")
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)

        # --- Layout ---
        self.grid_rowconfigure(0, weight=1)    # Icon takes up most space
        self.grid_rowconfigure(1, weight=0)    # Label is at the bottom
        self.grid_columnconfigure(0, weight=1)

        # --- Icon ---
        try:
            icon_image = ctk.CTkImage(Image.open(icon_path), size=(64, 64))
        except (FileNotFoundError, Image.UnidentifiedImageError): # Add Image.UnidentifiedImageError
            # Use a placeholder if the icon is not found or cannot be identified
            print(f"Warning: Icon not found or invalid at '{icon_path}'. Using placeholder.")
            icon_image = ctk.CTkImage(Image.new("RGB", (64, 64), color="grey"), size=(64, 64))

        self.icon_label = ctk.CTkLabel(self, image=icon_image, text="")
        self.icon_label.grid(row=0, column=0, pady=(15, 5))
        self.icon_label.bind("<Button-1>", self.on_click)

        # --- Text Label ---
        self.text_label = ctk.CTkLabel(
            self,
            text=text,
            font=("Arial", 16),
            text_color=PIPBOY_GREEN
        )
        self.text_label.grid(row=1, column=0, pady=(0, 10), padx=5)
        self.text_label.bind("<Button-1>", self.on_click)


    def on_enter(self, event):
        """Callback for mouse entering the widget."""
        self.configure(fg_color="#3a3d3e")

    def on_leave(self, event):
        """Callback for mouse leaving the widget."""
        self.configure(fg_color="#2a2d2e")

    def on_click(self, event):
        """Callback for clicking the widget."""
        if self.command:
            self.command()


class HomePage(ctk.CTkFrame):
    """
    The main menu for the application, providing navigation to all other pages
    using a scrollable grid of icons.
    """
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="#1a1a1a")
        self.controller = controller

        # --- Layout ---
        # Configure the main frame to center its content
        self.grid_rowconfigure(0, weight=0) # Title
        self.grid_rowconfigure(1, weight=1) # Scrollable content
        self.grid_columnconfigure(0, weight=1)

        # --- Widgets ---
        # Main Title Label
        title_label = ctk.CTkLabel(
            self,
            text="Main System Menu",
            font=("Arial", 40, "bold"),
            text_color=PIPBOY_GREEN
        )
        title_label.grid(row=0, column=0, pady=20, padx=50)

        # --- NEW: Scrollable Frame for the Icon Grid ---
        scrollable_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scrollable_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)

        # --- NEW: Configure the grid inside the scrollable frame (4 columns) ---
        for i in range(4):
            scrollable_frame.grid_columnconfigure(i, weight=1)

        # --- Icon Creation ---
        # Define the base path for your icons
        icon_path = os.path.join(controller.app_dir, "assets", "icons")

        pages_to_create = [
            ("Radio", "RadioPage", os.path.join(icon_path, "radio.png")),
            ("Access V.I.N.C.E.", "AIPage", os.path.join(icon_path, "ai.png")),
            ("System Status", "StatusPage", os.path.join(icon_path, "status.png")),
            ("GPIO Control", "GPIOPage", os.path.join(icon_path, "gpio.png")),
            ("Terminal", "TerminalPage", os.path.join(icon_path, "terminal.png")),
            ("File Browser", "FileBrowserPage", os.path.join(icon_path, "files.png")),
            ("Web Browser", "BrowserPage", os.path.join(icon_path, "web.png")),
            ("Vehicle Interface", "VehiclePage", os.path.join(icon_path, "vehicle.png")),
            ("Network Scanner", "NetworkPage", os.path.join(icon_path, "network.png")),
            ("Secure Comms", "CommsPage", os.path.join(icon_path, "comms.png")),
            ("Settings", "SettingsPage", os.path.join(icon_path, "settings.png"))
        ]

        # Sort pages alphabetically by text, except for Settings which should be last
        settings_page = pages_to_create[-1]
        sorted_pages = sorted(pages_to_create[:-1], key=lambda x: x[0])
        sorted_pages.append(settings_page)

        # --- NEW: Loop and place IconWidgets in the grid ---
        for i, (text, page_name, icon_file) in enumerate(sorted_pages):
            row = i // 4  # Calculate the row number
            col = i % 4   # Calculate the column number

            icon_widget = IconWidget(
                parent=scrollable_frame,
                text=text,
                icon_path=icon_file,
                command=lambda p=page_name: controller.show_page(p)
            )
            # Add padding to create space between the icons
            icon_widget.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")