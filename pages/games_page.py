import customtkinter as ctk
import logging
from tkinter import messagebox

logger = logging.getLogger(__name__)

PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME = "#2a2d2e"
DARK_BACKGROUND = "#1a1a1a"

class GamesPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=DARK_BACKGROUND)
        self.controller = controller

        # Layout configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        header_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(header_frame, text="GAMES & EMULATORS", font=("Arial", 20, "bold"), text_color=PIPBOY_GREEN)
        title_label.grid(row=0, column=0, sticky="w")

        back_button = ctk.CTkButton(header_frame, text="Back to Home", command=lambda: self.controller.show_page("HomePage"))
        back_button.grid(row=0, column=1, sticky="e", padx=10)

        # --- Content Area ---
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        # Left panel - Games list
        games_list_frame = ctk.CTkFrame(content_frame, fg_color=PIPBOY_FRAME, corner_radius=10)
        games_list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)
        games_list_frame.grid_columnconfigure(0, weight=1)
        
        list_title = ctk.CTkLabel(games_list_frame, text="Installed Games", font=("Arial", 16, "bold"), text_color=PIPBOY_GREEN)
        list_title.pack(pady=10)

        # RetroArch Launch Button
        self.retroarch_btn = ctk.CTkButton(
            games_list_frame, 
            text="Launch RetroArch", 
            font=("Arial", 14, "bold"),
            text_color="black",
            fg_color=PIPBOY_GREEN,
            hover_color="#27b55a",
            height=50,
            command=self.launch_retroarch
        )
        self.retroarch_btn.pack(fill="x", padx=20, pady=10)

        # Right panel - Description and instruction panel
        info_frame = ctk.CTkFrame(content_frame, fg_color=PIPBOY_FRAME, corner_radius=10)
        info_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=5)
        info_frame.grid_columnconfigure(0, weight=1)

        info_title = ctk.CTkLabel(info_frame, text="Instructions", font=("Arial", 16, "bold"), text_color=PIPBOY_GREEN)
        info_title.pack(pady=10)

        instructions = (
            "1. Connect a USB or Bluetooth Game Controller to the Pi.\n\n"
            "2. Press 'Launch RetroArch' to start emulation.\n\n"
            "3. Exit RetroArch using your controller shortcuts (commonly Start + Select) "
            "to return to the car dashboard."
        )
        info_desc = ctk.CTkLabel(info_frame, text=instructions, font=("Arial", 12), text_color="white", justify="left", wraplength=350)
        info_desc.pack(padx=20, pady=10, fill="both", expand=True)

    def launch_retroarch(self):
        success, message = self.controller.request_game_launch("retroarch")
        if success:
            logger.info("RetroArch launched successfully.")
        else:
            messagebox.showerror("Error launching emulation", message, parent=self)
            
    def on_show(self):
        pass

    def on_hide(self):
        pass
