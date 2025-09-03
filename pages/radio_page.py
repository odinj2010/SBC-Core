# FILE: pages/radio_page.py
# This file defines the `RadioPage` class, which serves as the graphical user
# interface (GUI) for controlling the application's global radio/music player.
# It allows users to browse and select "stations" (folders of music),
# view current track information, and control playback (play/pause, next/previous track, volume).
# The actual playback logic is handled by the main application controller using the `python-vlc` library.

import customtkinter as ctk # CustomTkinter for modern-looking GUI elements
import logging # For logging events, warnings, and errors throughout this module
from pathlib import Path # Object-oriented filesystem paths, used for navigating music directories
from typing import Optional, List, Any # For type hinting, improving code readability and maintainability

# --- Conditional VLC Import for Type Checking ---
# This block attempts to import the `vlc` library, which is the Python binding for
# the VLC media player. This is crucial for the radio functionality.
# If `vlc` is not found, a mock class structure is not strictly necessary for this
# page's UI elements, but a flag `VLC_AVAILABLE` is set to `False` to disable
# related features and display appropriate messages.
try:
    import vlc # The `python-vlc` library for media playback
    VLC_AVAILABLE = True # Flag indicating VLC is available
except ImportError:
    vlc = None # Set vlc to None to prevent `NameError` in type hints or other uses
    VLC_AVAILABLE = False # Flag indicating VLC is NOT available
    # Log a warning to inform the user that radio functionality will be disabled.
    logging.warning("VLC library not found. Radio player functionality will be disabled.")


logger = logging.getLogger(__name__) # Get a logger instance for this module

# --- Configuration Constants ---
# Define the root directory where radio station folders (each containing music files) are located.
# `Path(__file__).parent.parent` navigates up two levels from `radio_page.py` to the main app directory.
MUSIC_ROOT_DIR = Path(__file__).parent.parent / "assets" / "sounds" / ".radio"

# UI Colors - Consistent with a "Pipboy" (Fallout-style) theme.
PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME_COLOR = "#2a2d2e"
STATION_BUTTON_NORMAL_COLOR = "#1F6AA5" # Default color for station buttons
PRIMARY_BG_COLOR = "#1a1a1a" # Main background color for the page
TEXT_COLOR_GRAY = "gray" # Color for secondary text, like artist names

# UI Fonts - Defined as tuples for reusability across different UI elements.
# Using a custom font "ShareTechMono-Regular" for thematic consistency.
FONT_HEADER = ("Arial", 20, "bold")
FONT_STATION_TITLE = ("Arial", 24, "bold")
FONT_TRACK_TITLE = ("Arial", 16)
FONT_ARTIST_NAME = ("Arial", 12)
FONT_PROGRESS_TIME = ("Arial", 10)
FONT_CONTROL_BUTTONS = ("Arial", 20) # Standard font for media control buttons
FONT_STATION_BUTTON = ("Arial", 12) # Font for individual station selection buttons
FONT_SECTION_HEADER = ("Arial", 14, "bold") # Font for section titles like "STATIONS"


class RadioPage(ctk.CTkFrame):
    """
    A CustomTkinter page that acts as a UI remote control for the main application's
    global radio/music player. It displays available stations, current track info,
    and provides playback controls.
    """

    def __init__(self, parent: ctk.CTkFrame, controller: Any) -> None:
        """
        Initializes the RadioPage.

        Args:
            parent: The CTkFrame widget that contains this page.
            controller: A reference to the main application controller, which
                        manages the actual VLC media player instance and global radio state.
        """
        super().__init__(parent, fg_color=PRIMARY_BG_COLOR) # Initialize CTkFrame with the primary background color
        self.controller = controller # Store the controller reference
        self.station_buttons: List[ctk.CTkButton] = [] # List to hold CTkButton widgets for each station
        # Stores the index of the previously selected station. Used for optimizing button highlighting.
        self._previous_selected_station_idx: Optional[int] = None 

        self._setup_ui() # Call method to build the user interface
        
    def _setup_ui(self) -> None:
        """
        Initializes the layout and widgets for the radio page.
        It's divided into a header, a station list pane, and a media player pane.
        """
        self.grid_columnconfigure(0, weight=1) # Make the main column expandable
        self.grid_rowconfigure(1, weight=1)   # Make the main content row expandable
        
        # --- Header Frame ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10,5)) # Position at the top
        header.columnconfigure(0, weight=1) # Make the title label column expandable
        
        # Page title label
        ctk.CTkLabel(header, text="RADIO", font=FONT_HEADER, text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        # Button to navigate back to the Home page, using the controller for page switching.
        ctk.CTkButton(header, text="Back to Home", command=lambda: self.controller.show_page("HomePage")).grid(row=0, column=1, sticky="e", padx=10)
        
        # --- Main Content Pane ---
        # This frame holds both the station list and the media player sections.
        main_pane = ctk.CTkFrame(self, fg_color="transparent")
        main_pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        main_pane.grid_columnconfigure(0, weight=3) # Station list takes ~30% width
        main_pane.grid_columnconfigure(1, weight=7) # Player takes ~70% width
        main_pane.grid_rowconfigure(0, weight=1) # The single row is expandable
        
        # --- Station List Frame ---
        station_frame = ctk.CTkFrame(main_pane, fg_color=PIPBOY_FRAME_COLOR)
        station_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5)) # Position on the left within main_pane
        station_frame.grid_rowconfigure(1, weight=1) # Make the scrollable frame row expandable
        station_frame.grid_columnconfigure(0, weight=1) # Make the column for station buttons expandable
        
        # Label for the "STATIONS" section
        ctk.CTkLabel(station_frame, text="STATIONS", font=FONT_SECTION_HEADER).grid(row=0, column=0, pady=5)
        # A scrollable frame to contain the list of station buttons.
        self.station_scroll_frame = ctk.CTkScrollableFrame(station_frame, fg_color="transparent")
        self.station_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.station_scroll_frame.columnconfigure(0, weight=1) # Ensure buttons within the scrollable frame fill its width
        
        # --- Player Frame ---
        # This frame displays current track info and playback controls.
        self.player_frame = ctk.CTkFrame(main_pane, fg_color=PIPBOY_FRAME_COLOR)
        self.player_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0)) # Position on the right within main_pane
        self.player_frame.grid_columnconfigure(0, weight=1) # Make its single column expandable
        
        # Label for the current station's title (or "NO SIGNAL").
        self.station_label = ctk.CTkLabel(self.player_frame, text="NO SIGNAL", font=FONT_STATION_TITLE, text_color=PIPBOY_GREEN)
        self.station_label.pack(pady=(20, 5))
        
        # Label for the current track's title.
        self.track_label = ctk.CTkLabel(self.player_frame, text="...", font=FONT_TRACK_TITLE, wraplength=500)
        self.track_label.pack(pady=5)
        
        # Label for the current track's artist.
        self.artist_label = ctk.CTkLabel(self.player_frame, text="...", font=FONT_ARTIST_NAME, text_color=TEXT_COLOR_GRAY, wraplength=500)
        self.artist_label.pack(pady=(0, 20))
        
        # Label for current playback time / total duration.
        self.progress_label = ctk.CTkLabel(self.player_frame, text="0:00 / 0:00", font=FONT_PROGRESS_TIME)
        self.progress_label.pack()
        
        # Progress bar for visual representation of track progress.
        self.progress_bar = ctk.CTkProgressBar(self.player_frame)
        self.progress_bar.pack(fill="x", padx=20, pady=5)
        self.progress_bar.set(0) # Initialize to 0
        
        # --- Playback Controls Frame ---
        controls_frame = ctk.CTkFrame(self.player_frame, fg_color="transparent")
        controls_frame.pack(pady=20)
        
        # Previous track button, calls controller's method.
        self.prev_btn = ctk.CTkButton(controls_frame, text="⏪", font=FONT_CONTROL_BUTTONS, width=50, command=self.controller.radio_prev_track)
        self.prev_btn.pack(side="left", padx=10)
        
        # Play/Pause button, calls controller's method. Text changes between play and pause symbols.
        self.play_pause_btn = ctk.CTkButton(controls_frame, text="▶", font=FONT_CONTROL_BUTTONS, width=80, command=self.controller.radio_toggle_play_pause)
        self.play_pause_btn.pack(side="left", padx=10)
        
        # Next track button, calls controller's method.
        self.next_btn = ctk.CTkButton(controls_frame, text="⏩", font=FONT_CONTROL_BUTTONS, width=50, command=self.controller.radio_next_track)
        self.next_btn.pack(side="left", padx=10)
        
        # Volume slider, calls controller's method on value change.
        self.volume_scale = ctk.CTkSlider(self.player_frame, from_=0, to=100, command=self.controller.radio_set_volume)
        self.volume_scale.pack(fill="x", padx=50, pady=20)

    def on_show(self) -> None:
        """
        Lifecycle method called when the RadioPage becomes visible.
        It triggers a scan for available music stations and then updates
        all UI elements to reflect the current state of the radio player.
        """
        logger.debug("RadioPage on_show called.")
        self.scan_and_load_stations() # Discover and display available stations
        self.sync_ui_with_controller() # Perform an initial UI synchronization

    def on_hide(self) -> None:
        """
        Lifecycle method called when the RadioPage is hidden.
        Resets internal state variables that manage UI highlighting to ensure
        a fresh state when the page is shown again.
        """
        logger.debug("RadioPage on_hide called.")
        # Reset previous station index when hiding to ensure a full refresh
        # of button highlights on the next `on_show`.
        self._previous_selected_station_idx = None

    def sync_ui_with_controller(self) -> None:
        """
        This is the central update function for the RadioPage's UI.
        It fetches the latest state from the main application's `controller`
        (which holds the VLC player instance and radio state variables)
        and updates all relevant UI elements accordingly.
        This function is designed to be called repeatedly by the controller's
        main UI update loop (e.g., via `self.after`).
        """
        player = self.controller.radio_player # Get the current VLC player instance from the controller
        
        # First, check if VLC itself is available and if the player was initialized successfully.
        if not VLC_AVAILABLE:
            self._handle_vlc_offline_state("VLC library not found or failed to load.")
            return
        
        if not player:
            self._handle_vlc_offline_state("Radio player is not initialized.")
            return

        # If VLC and player are ready, proceed to update specific UI sections.
        self._update_player_controls(player)
        self._update_station_selection_ui()
        self._update_track_metadata()
        self._update_playback_progress(player)

    def _handle_vlc_offline_state(self, message: str) -> None:
        """
        Updates the UI to clearly indicate that VLC or the radio player
        is not available or failed to initialize. Disables controls.

        Args:
            message: A descriptive message to display to the user.
        """
        self.station_label.configure(text="RADIO OFFLINE")
        self.track_label.configure(text=message)
        self.artist_label.configure(text="") # Clear artist info
        # Disable all playback control buttons and the volume slider.
        self.play_pause_btn.configure(state="disabled")
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        self.volume_scale.configure(state="disabled")
        self.progress_bar.set(0) # Reset progress bar
        self.progress_label.configure(text="0:00 / 0:00") # Reset time labels
        # Ensure all station buttons are unhighlighted and reset to their normal color.
        for btn in self.station_buttons:
            btn.configure(fg_color=STATION_BUTTON_NORMAL_COLOR)
        # Reset previous selected station index to prevent phantom highlights.
        self._previous_selected_station_idx = None

    def _update_player_controls(self, player: Any) -> None:
        """
        Updates the state and appearance of playback controls (play/pause button)
        and the volume slider based on the current VLC player state.

        Args:
            player: The `vlc.MediaPlayer` instance.
        """
        # Update volume slider only if the actual player volume has changed,
        # to avoid unnecessary widget updates.
        current_volume = player.audio_get_volume() # VLC volume is an integer from 0-100
        if self.volume_scale.get() != current_volume:
            self.volume_scale.set(current_volume)
        
        # Re-enable controls if they were previously disabled due to an offline state.
        if self.play_pause_btn.cget("state") == "disabled":
            self.play_pause_btn.configure(state="normal")
            self.prev_btn.configure(state="normal")
            self.next_btn.configure(state="normal")
            self.volume_scale.configure(state="normal")

        # Change play/pause button text based on player state.
        play_pause_text = "❚❚" if player.is_playing() else "▶"
        if self.play_pause_btn.cget("text") != play_pause_text:
            self.play_pause_btn.configure(text=play_pause_text)

    def _update_station_selection_ui(self) -> None:
        """
        Updates the station title label and highlights the button corresponding
        to the currently selected radio station. Optimizes updates to only change
        UI elements if their value has actually changed.
        """
        station_idx = self.controller.radio_current_station_idx # Get current station index from controller
        stations = self.controller.radio_stations # Get list of station names
        
        if station_idx != -1 and 0 <= station_idx < len(stations):
            station_name = stations[station_idx]
            # Update station label only if text is different.
            if self.station_label.cget("text") != station_name.upper():
                self.station_label.configure(text=station_name.upper())

            # Optimize button highlight updates: only change if selected station index actually changed.
            if self._previous_selected_station_idx != station_idx:
                # If there was a previous selected station, unhighlight its button.
                if self._previous_selected_station_idx is not None and \
                   0 <= self._previous_selected_station_idx < len(self.station_buttons):
                    self.station_buttons[self._previous_selected_station_idx].configure(fg_color=STATION_BUTTON_NORMAL_COLOR)
                
                # Highlight the current station's button.
                if 0 <= station_idx < len(self.station_buttons):
                    self.station_buttons[station_idx].configure(fg_color=PIPBOY_GREEN)
                
                # Store the new selected index for the next update cycle.
                self._previous_selected_station_idx = station_idx
        else:
            # If no station is selected (index is -1 or invalid).
            if self.station_label.cget("text") != "NO SIGNAL":
                self.station_label.configure(text="NO SIGNAL")
            
            # If no station is selected, ensure all buttons are unhighlighted.
            if self._previous_selected_station_idx is not None:
                if 0 <= self._previous_selected_station_idx < len(self.station_buttons):
                    self.station_buttons[self._previous_selected_station_idx].configure(fg_color=STATION_BUTTON_NORMAL_COLOR)
                self._previous_selected_station_idx = None # Clear the previous selection

    def _update_track_metadata(self) -> None:
        """
        Updates the track title and artist labels based on the current track's metadata
        stored in the controller.
        """
        current_title = self.controller.radio_current_track_title
        current_artist = self.controller.radio_current_track_artist

        # Update track title label only if text is different.
        if self.track_label.cget("text") != current_title:
            self.track_label.configure(text=current_title)
        
        # Update artist label only if text is different.
        if self.artist_label.cget("text") != current_artist:
            self.artist_label.configure(text=current_artist)

    def _update_playback_progress(self, player: Any) -> None:
        """
        Updates the progress bar and time labels to reflect the current playback position.

        Args:
            player: The `vlc.MediaPlayer` instance.
        """
        duration_ms = self.controller.radio_current_track_duration_ms # Total duration from controller (ms)
        current_time_ms = player.get_time() # Current playback time from VLC player (ms)
        
        current_time_str = self._format_time(current_time_ms // 1000) # Format current time to MM:SS
        duration_str = self._format_time(duration_ms // 1000)       # Format total duration to MM:SS
        
        new_progress_text = f"{current_time_str} / {duration_str}"
        # Update progress label only if text is different.
        if self.progress_label.cget("text") != new_progress_text:
            self.progress_label.configure(text=new_progress_text)
        
        if duration_ms > 0:
            progress = min(current_time_ms / duration_ms, 1.0) # Calculate progress, cap at 1.0
            # Update progress bar only if value changed.
            if self.progress_bar.get() != progress:
                self.progress_bar.set(progress)
        else:
            # If duration is 0 (e.g., streaming or error), reset progress bar.
            if self.progress_bar.get() != 0:
                self.progress_bar.set(0)

    def scan_and_load_stations(self) -> None:
        """
        Scans the predefined `MUSIC_ROOT_DIR` for subdirectories, treating each
        subdirectory as a "radio station". It dynamically creates CTkButtons
        for each station and adds them to the scrollable frame.
        Also handles directory creation if it doesn't exist and displays error messages.
        """
        if not MUSIC_ROOT_DIR.is_dir():
            try: 
                MUSIC_ROOT_DIR.mkdir(parents=True, exist_ok=True) # Attempt to create the directory
                logger.info(f"Created music directory: {MUSIC_ROOT_DIR}")
            except OSError as e: 
                logger.error(f"Could not create music directory {MUSIC_ROOT_DIR}: {e}")
                # Update UI to reflect the error if directory creation fails.
                self.station_label.configure(text="ERROR")
                self.track_label.configure(text=f"Failed to create music directory:\n{MUSIC_ROOT_DIR.as_posix()}\nError: {e}")
                self.artist_label.configure(text="")
                return # Exit early if directory cannot be managed
        
        # Clear any existing station buttons from the UI before rescanning.
        for btn in self.station_buttons:
            btn.destroy()
        self.station_buttons.clear() # Empty the list of button references
        
        # Reset previous selected station index because buttons are being rebuilt,
        # ensuring correct highlighting after recreation.
        self._previous_selected_station_idx = None
        
        # Get the new list of station names (subdirectories) and store it in the controller.
        all_subdirs = [d for d in MUSIC_ROOT_DIR.iterdir() if d.is_dir()]
        self.controller.radio_stations = sorted([d.name for d in all_subdirs]) # Store sorted names

        if not self.controller.radio_stations:
            # If no station folders are found, update the UI to inform the user.
            self.station_label.configure(text="NO STATIONS FOUND")
            self.track_label.configure(text=f"Add music folders to\n{MUSIC_ROOT_DIR.as_posix()}")
            self.artist_label.configure(text="")
            return # Exit early if no stations
            
        # Create a button for each discovered station.
        for i, station_name in enumerate(self.controller.radio_stations):
            # Each button's command calls `radio_select_station` in the controller,
            # passing its index. `lambda idx=i:` captures the current value of `i`.
            btn = ctk.CTkButton(self.station_scroll_frame, text=station_name, 
                                command=lambda idx=i: self.controller.radio_select_station(idx),
                                fg_color=STATION_BUTTON_NORMAL_COLOR,
                                font=FONT_STATION_BUTTON)
            # Use grid for buttons inside the scrollable frame for better control over expansion.
            btn.grid(row=i, column=0, sticky="ew", pady=2, padx=5)
            self.station_buttons.append(btn)
            
        # After loading stations, if a station is already selected in the controller
        # (e.g., if the page was hidden and shown again while music was playing),
        # ensure its button is highlighted immediately.
        self._update_station_selection_ui()

    def _format_time(self, seconds: int) -> str:
        """
        Helper method to format a given number of seconds into a "MM:SS" string.

        Args:
            seconds: The time in seconds.

        Returns:
            A formatted string (e.g., "3:45").
        """
        if seconds < 0: return "0:00" # Handle negative time
        minutes, remaining_seconds = divmod(seconds, 60) # Divide seconds into minutes and remaining seconds
        return f"{minutes}:{remaining_seconds:02d}" # Format with leading zero for seconds if needed