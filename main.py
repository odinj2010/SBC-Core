# FILE: main.py
import customtkinter as ctk
import configparser
import os
import sys
import logging
import threading
from PIL import Image
from pathlib import Path
import random
from typing import Optional, List, Any, Tuple

# --- Radio-specific Imports ---
VLC_AVAILABLE = False
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    vlc = None
    logging.warning("python-vlc library not found. Radio functionality will be disabled.")

MUTAGEN_AVAILABLE = False
try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    mutagen = None
    logging.warning("mutagen library not found. Music metadata (title, artist) cannot be read.")


try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

# --- Import all page classes ---
from pages.home_page import HomePage
from pages.ai_page import AIPage
from pages.gpio_page import GPIOPage
from pages.status_page import StatusPage
from pages.file_browser_page import FileBrowserPage
from pages.terminal_page import TerminalPage, TerminalLoggingHandler
from pages.settings_page import SettingsPage
from pages.radio_page import RadioPage
from pages.browser_page import BrowserPage
from pages.vehicle_page import VehiclePage
# --- NEW: Import new pages ---
from pages.network_page import NetworkPage
from pages.comms_page import CommsPage


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Radio Configuration ---
MUSIC_ROOT_DIR = Path(__file__).parent / "assets" / "sounds" / ".radio"
SUPPORTED_EXTENSIONS = ('.mp3', '.ogg', '.wav', '.m4a', '.flac')


def load_local_llm(config, app_dir):
    if not LLAMA_CPP_AVAILABLE:
        logging.error("llama-cpp-python not found. Local AI is disabled.")
        return None
        
    relative_path = config.get('PATHS', 'llm_model_path', fallback='').strip()
    if not relative_path:
        logging.error("LLM model path is not set in config.ini under [PATHS].")
        return None
        
    model_path = os.path.normpath(os.path.join(app_dir, relative_path))
    
    if not os.path.exists(model_path):
        logging.error(f"AI model not found at resolved path: {model_path}")
        return None
    try:
        logging.info(f"Loading local AI model from: {model_path}")
        llm_instance = Llama(model_path=model_path, n_ctx=4096, n_gpu_layers=0, verbose=False)
        logging.info("Local AI model loaded successfully!")
        return llm_instance
    except Exception as e:
        logging.error(f"Failed to load the AI model: {e}", exc_info=True)
        return None

class MainApplication(ctk.CTk):
    def __init__(self, llm, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = llm

        self.title("Raspberry Pi Kiosk")
        self.geometry("1024x600")

        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.ASSETS_DIR = os.path.join(self.app_dir, "assets")
        self.active_toplevel = None

        self.config = configparser.ConfigParser()
        self.config_path = os.path.join(self.app_dir, 'config.ini')
        self.config.read(self.config_path)
        
        # Variables to hold all current track info
        self.vlc_instance: Optional[vlc.Instance] = None
        self.radio_player: Optional[vlc.MediaPlayer] = None
        self.radio_event_manager: Optional[vlc.EventManager] = None
        self._radio_current_media: Optional[vlc.Media] = None
        self._radio_ui_update_id: Optional[str] = None # To store the after ID for the UI update loop
        
        self.radio_stations: List[str] = []
        self.radio_playlist: List[Path] = []
        self.radio_current_station_idx: int = -1
        self.radio_current_track_idx: int = -1
        
        # State variables for the current track's metadata
        self.radio_current_track_title: str = "..."
        self.radio_current_track_artist: str = "..."
        self.radio_current_track_duration_ms: int = 0
        
        self._initialize_radio_player()
        
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.page_classes = {
            "HomePage": HomePage, "AIPage": AIPage, "GPIOPage": GPIOPage,
            "StatusPage": StatusPage, "FileBrowserPage": FileBrowserPage,
            "TerminalPage": TerminalPage, "SettingsPage": SettingsPage,
            "RadioPage": RadioPage, "BrowserPage": BrowserPage,
            "VehiclePage": VehiclePage,
            # --- NEW: Add new pages to the class dictionary ---
            "NetworkPage": NetworkPage, "CommsPage": CommsPage,
        }
        
        self.create_all_pages(container)
        self.setup_logging_handler()
        self.show_page("HomePage")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_all_pages(self, container):
        for page_name, PageClass in self.page_classes.items():
            logging.info(f"Creating page instance for: {page_name}")
            try:
                init_params = PageClass.__init__.__code__.co_varnames
                kwargs = {'parent': container, 'controller': self}
                if 'llm' in init_params: kwargs['llm'] = self.llm
                page_instance = PageClass(**kwargs)
                self.pages[page_name] = page_instance
                page_instance.grid(row=0, column=0, sticky="nsew")
            except Exception as e:
                logging.error(f"Failed to create page '{page_name}': {e}", exc_info=True)

    # --- NEW: AI Service Hub Methods ---
    def request_gpio_action(self, bcm_pin: int, state: str) -> Tuple[bool, str]:
        """Handles a simple high/low request from the AI."""
        if "GPIOPage" in self.pages:
            return self.pages["GPIOPage"].handle_ai_gpio_request(bcm_pin, state)
        return False, "GPIO Control module is not loaded."
        
    def request_gpio_pulse(self, bcm_pin: int, interval_ms: int) -> Tuple[bool, str]:
        """Handles a pulse request from the AI."""
        if "GPIOPage" in self.pages:
            gpio_page = self.pages["GPIOPage"]
            # We need to get the device object to start the pulse
            if bcm_pin in gpio_page.active_devices:
                device = gpio_page.active_devices[bcm_pin]
                # Ensure it's an output device before pulsing
                if hasattr(device, 'toggle'): # A simple check for output-like devices
                    interval_s = interval_ms / 1000.0
                    gpio_page.start_pulse(bcm_pin, device, interval_s)
                    return True, f"Pulse started on pin {bcm_pin}."
                else:
                    return False, f"Pin {bcm_pin} is not an output device."
            else:
                return False, f"Pin {bcm_pin} is not configured. Set to OUTPUT first."
        return False, "GPIO Control module is not loaded."

    def request_system_status(self, query: str) -> Tuple[bool, str]:
        """Handles a system status query from the AI."""
        if "StatusPage" in self.pages:
            return self.pages["StatusPage"].get_specific_stat(query)
        return False, "Status Page module not loaded."
        
    def request_vehicle_diagnostics(self, action: str) -> Tuple[bool, str]:
        """Handles a vehicle diagnostics request from the AI."""
        if "VehiclePage" in self.pages:
            vehicle_page = self.pages["VehiclePage"]
            if not vehicle_page.is_connected:
                return False, "Not connected to a vehicle."
            
            if action == "read_dtcs":
                vehicle_page.read_dtcs()
                return True, "DTC read command initiated."
            elif action == "clear_dtcs":
                vehicle_page.clear_dtcs()
                return True, "DTC clear command initiated."
            else:
                return False, f"Unknown vehicle action: {action}"
        return False, "Vehicle Interface module not loaded."
    # --- END: AI Service Hub Methods ---

    def setup_logging_handler(self):
        if "TerminalPage" in self.pages:
            handler = TerminalLoggingHandler(self.pages["TerminalPage"])
            handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
            logging.getLogger().addHandler(handler)
            logging.info("Terminal logging handler initialized.")

    def show_page(self, page_name):
        if page_name not in self.pages:
            logging.error(f"Attempted to show non-existent page: '{page_name}'")
            return
        self.close_active_toplevel()
        for page in self.pages.values():
            if page.winfo_ismapped() and hasattr(page, 'on_hide'):
                page.on_hide()
        page_to_show = self.pages[page_name]
        if hasattr(page_to_show, 'on_show'):
            page_to_show.on_show()
        page_to_show.tkraise()

    def save_config(self):
        try:
            with open(self.config_path, 'w') as configfile: self.config.write(configfile)
            logging.info("Configuration saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save configuration: {e}")

    def close_active_toplevel(self):
        if self.active_toplevel and self.active_toplevel.winfo_exists():
            self.active_toplevel.destroy()
        self.active_toplevel = None

    def create_default_config(self, path):
        logging.info("Creating default config.ini file...")
        dc = configparser.ConfigParser()
        dc['AI'] = {'backend': 'local'}
        dc['GEMINI'] = {'api_key': 'YOUR_API_KEY_HERE'}
        dc['PATHS'] = {'llm_model_path': '', 'piper_model_path': ''}
        dc['Browser'] = {'home_page': 'https://www.google.com', 'search_engine_url': 'https://www.google.com/search?q='}
        with open(path, 'w') as f: dc.write(f)

    def on_closing(self):
        logging.info("Closing application...")
        self.radio_cleanup()
        for page in self.pages.values():
            if hasattr(page, 'on_hide'):
                page.on_hide()
        if "TerminalPage" in self.pages: self.pages["TerminalPage"].cleanup()
        if "GPIOPage" in self.pages: self.pages["GPIOPage"].full_cleanup() # NEW: Clean up GPIO resources
        if self.llm:
            logging.info("Releasing AI model from memory...")
            del self.llm
            import gc
            gc.collect()
            logging.info("AI model released.")
        self.destroy()
        sys.exit(0)

    # --- RADIO METHODS SECTION ---

    def _initialize_radio_player(self):
        if not VLC_AVAILABLE:
            logging.warning("VLC library not available, radio player cannot be initialized.")
            return
        try:
            self.vlc_instance = vlc.Instance(['--quiet', '--no-video'])
            self.radio_player = self.vlc_instance.media_player_new()
            self.radio_event_manager = self.radio_player.event_manager()
            self._setup_radio_vlc_events()
            self.radio_player.audio_set_volume(75)
            logging.info("Global VLC Radio Player initialized successfully.")
            
            # Start the continuous UI update loop
            self._radio_ui_update_id = self.after(500, self._radio_ui_update_loop)

        except Exception as e:
            logging.error(f"Error initializing global VLC player: {e}", exc_info=True)
            self.radio_player = None

    def _radio_ui_update_loop(self):
        """
        Periodically calls the UI update callback.
        This is essential for the progress bar and for keeping the play/pause button in sync.
        """
        self.radio_update_ui_callback()
        self.after(250, self._radio_ui_update_loop) # Reschedule to run every 250ms

    def _setup_radio_vlc_events(self):
        if not self.radio_event_manager: return
        self.radio_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_radio_media_end_reached)
        
    def _on_radio_media_end_reached(self, event):
        logging.debug("Global Radio: MediaPlayerEndReached")
        self.after(0, self.radio_next_track)

    def radio_cleanup(self):
        logging.info("Releasing global VLC radio resources.")
        if self._radio_ui_update_id:
            self.after_cancel(self._radio_ui_update_id)
            self._radio_ui_update_id = None
        if self.radio_player:
            self.radio_player.stop()
            self.radio_player.release()
            self.radio_player = None
        if self._radio_current_media:
            self._radio_current_media.release()
            self._radio_current_media = None
        if self.vlc_instance:
            self.vlc_instance.release()
            self.vlc_instance = None

    def radio_play_tts(self, wav_path: str):
        if not self.vlc_instance:
            logging.error("VLC instance not available for TTS playback.")
            return

        def _tts_playback_thread():
            radio_was_playing = self.radio_player and self.radio_player.is_playing()
            if radio_was_playing:
                self.radio_player.pause()

            tts_player = None
            try:
                tts_player = self.vlc_instance.media_player_new()
                media = self.vlc_instance.media_new(wav_path)
                tts_player.set_media(media)
                tts_player.audio_set_volume(100) # Play TTS at full volume
                tts_player.play()
                
                # Poll for completion
                import time
                time.sleep(0.5) # Give it a moment to start
                while tts_player.is_playing():
                    time.sleep(0.1)

            except Exception as e:
                logging.error(f"Error during TTS playback: {e}")
            finally:
                if tts_player:
                    tts_player.stop()
                    tts_player.release()
                
                # Clean up the temporary WAV file
                try:
                    os.remove(wav_path)
                    logging.debug(f"Removed temporary TTS file: {wav_path}")
                except OSError as e:
                    logging.error(f"Failed to remove temporary TTS file {wav_path}: {e}")

                if radio_was_playing:
                    # Use after() to safely interact with the main player from this thread
                    self.after(0, self.radio_player.play)
        
        threading.Thread(target=_tts_playback_thread, daemon=True).start()
    
    def radio_select_station(self, station_idx: int):
        if not self.radio_player or not (0 <= station_idx < len(self.radio_stations)):
            return

        self.radio_player.stop()
        self.radio_current_station_idx = station_idx
        station_name = self.radio_stations[station_idx]
        station_path = MUSIC_ROOT_DIR / station_name
        
        try:
            self.radio_playlist = sorted([f for f in station_path.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS])
            random.shuffle(self.radio_playlist)
            if self.radio_playlist:
                self.radio_current_track_idx = 0
                self.radio_play_track()
            else:
                self.radio_current_track_idx = -1
                self.radio_current_track_title = "Station is empty"
                self.radio_current_track_artist = "..."
                self.radio_current_track_duration_ms = 0
                self.radio_update_ui_callback()
        except Exception as e:
            logging.error(f"Error loading station '{station_name}': {e}")
            self.radio_playlist = []
            self.radio_current_track_idx = -1
            self.radio_update_ui_callback()

    def radio_play_track(self):
        if not self.radio_player or not self.radio_playlist or not (0 <= self.radio_current_track_idx < len(self.radio_playlist)):
            return

        track_path = self.radio_playlist[self.radio_current_track_idx]
        
        # Immediately update UI with filename as a placeholder
        self.radio_current_track_title = track_path.stem
        self.radio_current_track_artist = "Loading..."
        self.radio_current_track_duration_ms = 0
        self.radio_update_ui_callback() # Signal UI to show the placeholder info

        if self._radio_current_media:
            self._radio_current_media.release()
        
        self._radio_current_media = self.vlc_instance.media_new(track_path.as_posix())
        self.radio_player.set_media(self._radio_current_media)
        self.radio_player.play()
        
        # Load the detailed metadata in the background
        threading.Thread(target=self._radio_load_track_metadata_thread, args=(track_path,), daemon=True).start()

    def _radio_load_track_metadata_thread(self, track_path: Path):
        """Loads all track metadata in a background thread to prevent GUI freezes."""
        if not MUTAGEN_AVAILABLE:
            self.radio_current_track_artist = "Unknown Artist"
            self.after(0, self.radio_update_ui_callback)
            return

        try:
            title, artist = track_path.stem, "Unknown Artist"
            duration_ms = 0
            audio = mutagen.File(track_path, easy=True)
            if audio:
                title = audio.get('title', [title])[0]
                artist = audio.get('artist', [artist])[0]
                if hasattr(audio.info, 'length'):
                    duration_ms = int(audio.info.length * 1000)
            
            # Store all fetched info
            self.radio_current_track_title = title
            self.radio_current_track_artist = artist
            self.radio_current_track_duration_ms = duration_ms

        except Exception as e:
            logging.warning(f"Mutagen failed to read metadata for {track_path.name}: {e}")
            # Keep the filename as title if metadata fails
            self.radio_current_track_artist = "Unknown Artist"
            self.radio_current_track_duration_ms = 0
        finally:
            # After loading, signal the UI to update itself
            self.after(0, self.radio_update_ui_callback)

    def radio_update_ui_callback(self):
        """Signals the radio page to update its display if it's visible."""
        if "RadioPage" in self.pages and self.pages["RadioPage"].winfo_ismapped():
            self.pages["RadioPage"].sync_ui_with_controller()

    def radio_toggle_play_pause(self):
        if not self.radio_player:
            return
        
        if not self.radio_player.is_playing() and not self.radio_playlist:
            # If nothing is loaded and we press play, start the first station
            if self.radio_stations: self.radio_select_station(0)
        else:
            self.radio_player.pause()
        
        # Instantly update the UI after a click instead of waiting for the next cycle
        self.after(50, self.radio_update_ui_callback)

    def radio_next_track(self):
        if not self.radio_player or not self.radio_playlist: return
        self.radio_current_track_idx = (self.radio_current_track_idx + 1) % len(self.radio_playlist)
        self.radio_play_track()

    def radio_prev_track(self):
        if not self.radio_player or not self.radio_playlist: return
        self.radio_current_track_idx = (self.radio_current_track_idx - 1 + len(self.radio_playlist)) % len(self.radio_playlist)
        self.radio_play_track()
        
    def radio_set_volume(self, value: float):
        if self.radio_player:
            self.radio_player.audio_set_volume(int(value))

class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.geometry("400x200")
        self.overrideredirect(True)
        app_dir = os.path.dirname(os.path.abspath(__file__))
        splash_path = os.path.join(app_dir, "assets", "pics", "splash.png")
        try:
            self.splash_image = ctk.CTkImage(Image.open(splash_path), size=(400, 200))
            label = ctk.CTkLabel(self, image=self.splash_image, text="")
            label.pack(fill="both", expand=True)
        except Exception as e:
            logging.error(f"Could not load splash screen image: {e}")
            label = ctk.CTkLabel(self, text="Loading...", font=("Arial", 24))
            label.pack(fill="both", expand=True)
        
        parent.update_idletasks()
        x = (parent.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (parent.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

def main():
    root = ctk.CTk()
    root.withdraw()
    splash = SplashScreen(root)
    llm_container = [None] 
    app_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(app_dir, 'config.ini')
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        MainApplication(None).create_default_config(config_path)
    config.read(config_path)
    
    loading_thread = threading.Thread(target=lambda: llm_container.__setitem__(0, load_local_llm(config, app_dir)), daemon=True)
    loading_thread.start()
    
    def check_loading_status():
        if loading_thread.is_alive():
            root.after(100, check_loading_status)
        else:
            splash.destroy()
            root.destroy()
            app = MainApplication(llm=llm_container[0])
            app.mainloop()
            
    check_loading_status()
    root.mainloop()

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    main()
