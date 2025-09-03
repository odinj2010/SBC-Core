# pages/browser_page.py
import customtkinter as ctk # Import the CustomTkinter library for modern-looking GUI widgets.
import tkinter as tk # Import the standard Tkinter library, though CustomTkinter is primary, some underlying Tkinter functionality might be used.
import logging # Import the logging module for recording events, debugging, and status messages.
from tkinterweb import HtmlFrame # Import HtmlFrame from tkinterweb, which provides an embedded web browser widget.
import configparser # Import configparser for reading .ini files.

# Get a logger instance for this module. This allows for structured logging messages specific to the BrowserPage.
logger = logging.getLogger(__name__)

# --- Constants ---
# Define color constants to ensure consistent theming across the application, mimicking a "Pip-Boy" style.
PIPBOY_GREEN = "#32f178" # A distinct green color often associated with retro-futuristic interfaces like the Pip-Boy.
PIPBOY_FRAME = "#2a2d2e" # A dark grey color for background elements, providing contrast.

    

class BrowserPage(ctk.CTkFrame):
    """
    A page within a CustomTkinter application that embeds a simple web browser widget.
    This page allows users to input a URL and browse web content directly within the application.
    """
    def __init__(self, parent, controller):
        """
        Initializes the BrowserPage.

        Args:
            parent: The parent widget (e.g., the main application window or another frame)
                    to which this BrowserPage will be attached.
            controller: An instance of the main application controller, used to switch between pages.
        """
        # Call the constructor of the parent class (ctk.CTkFrame) to set up the frame itself.
        # Set a dark background color for the frame.
        super().__init__(parent, fg_color="#1a1a1a")
        self.controller = controller # Store a reference to the controller for navigation purposes.

        self.home_page, self.search_engine_url = self._read_config()

        # --- Layout Configuration ---
        # Configure the grid layout for this frame.
        self.grid_columnconfigure(0, weight=1) # Make the first (and only) column expandable, so widgets stretch horizontally.
        self.grid_rowconfigure(3, weight=1) # Allow the third row (where the browser frame is placed) to expand vertically,
                                            # ensuring the browser takes up available space.

        # --- Header Section ---
        # Create a header frame to hold the page title and a back button.
        header = ctk.CTkFrame(self, fg_color="transparent") # Use a transparent background for the header frame.
        header.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew") # Place header at the top, spanning horizontally.
        header.columnconfigure(0, weight=1) # Make the first column in the header expandable for the title.

        # Add a label for the page title, styled with a specific font and color.
        ctk.CTkLabel(header, text="WEB BROWSER", font=("Arial", 20, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        # Add a button to navigate back to the home page.
        ctk.CTkButton(header, text="Back to Home", command=lambda: controller.show_page("HomePage")).grid(row=0, column=1, sticky="e", padx=10)

        # --- Navigation Bar Section ---
        nav_frame = ctk.CTkFrame(self, fg_color=PIPBOY_FRAME)
        nav_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        nav_frame.grid_columnconfigure(4, weight=1) # Adjusted column configure for URL entry

        # Navigation Buttons
        self.back_button = ctk.CTkButton(nav_frame, text="<", width=30, command=self.go_back)
        self.back_button.grid(row=0, column=0, padx=(10, 2), pady=5)

        self.forward_button = ctk.CTkButton(nav_frame, text=">", width=30, command=self.go_forward)
        self.forward_button.grid(row=0, column=1, padx=(2, 2), pady=5)

        self.reload_button = ctk.CTkButton(nav_frame, text="↻", width=30, command=self.reload_page)
        self.reload_button.grid(row=0, column=2, padx=(2, 2), pady=5)

        self.home_button = ctk.CTkButton(nav_frame, text="🏠", width=30, command=self.go_home)
        self.home_button.grid(row=0, column=3, padx=(2, 10), pady=5)

        self.url_entry = ctk.CTkEntry(nav_frame, placeholder_text="https://...", font=("Arial", 12))
        self.url_entry.grid(row=0, column=4, padx=(0, 10), pady=5, sticky="ew")
        self.url_entry.bind("<Return>", self.load_url_event)

        self.go_button = ctk.CTkButton(nav_frame, text="Go", width=50, command=self.load_url)
        self.go_button.grid(row=0, column=5, padx=(0, 10), pady=5)

        self.bookmark_button = ctk.CTkButton(nav_frame, text="⭐", width=30, command=self.add_bookmark)
        self.bookmark_button.grid(row=0, column=6, padx=(0, 2), pady=5)

        self.show_bookmarks_button = ctk.CTkButton(nav_frame, text="Bookmarks", width=80, command=self.show_bookmarks)
        self.show_bookmarks_button.grid(row=0, column=7, padx=(2, 10), pady=5)

        # --- Status Bar ---
        self.status_label = ctk.CTkLabel(self, text="Ready", font=("Arial", 10), text_color=PIPBOY_GREEN)
        self.status_label.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")

        # --- Browser Frame ---
        self.browser_frame = HtmlFrame(self, messages_enabled=False)
        self.browser_frame.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="nsew")

        # Initialize a flag to ensure the default URL is loaded only once when the page is first shown.
        self.has_loaded_once = False
        self.history = []
        self.history_index = -1
        self.browser_frame.open_link = self._on_link_click

    def _read_config(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        home_page = "https://www.google.com" # Default
        search_engine_url = "https://www.google.com/search?q=" # Default

        if 'Browser' in config:
            if 'home_page' in config['Browser']:
                home_page = config['Browser']['home_page']
            if 'search_engine_url' in config['Browser']:
                search_engine_url = config['Browser']['search_engine_url']
        return home_page, search_engine_url

    def on_show(self):
        """
        This method is called by the application controller whenever this page is displayed.
        It's used to perform actions that should happen each time the page becomes visible,
        such as loading a default URL on the very first display.
        """
        # Check if the default URL has already been loaded.
        if not self.has_loaded_once:
            self.url_entry.insert(0, self.home_page) # Insert the default URL into the entry box.
            self.load_url(self.home_page, add_to_history=True) # Call load_url to navigate to the default URL.
            self.has_loaded_once = True # Set the flag to true to prevent reloading on subsequent shows.
            logger.info("BrowserPage shown for the first time, loading default URL.") # Log the action.

    def load_url(self, url=None, add_to_history=True):
        """
        Retrieves the URL from the entry box (if not provided), performs basic validation/sanitization,
        and then instructs the embedded browser to navigate to that URL.
        If the input is not a valid URL, it performs a Google search.
        Manages history and updates status.
        """
        if url is None:
            input_text = self.url_entry.get().strip()
        else:
            input_text = url.strip()

        if not input_text: # Don't try to load empty input
            self.status_label.configure(text="Please enter a URL or search query.")
            return

        # Determine if it's a URL or a search query
        # Simple check: if it contains a space or doesn't look like a URL
        if " " in input_text or not ("." in input_text and (input_text.startswith("http://") or input_text.startswith("https://") or input_text.startswith("www."))):
            # Treat as search query
            search_query = input_text
            url_to_load = f"{self.search_engine_url}{search_query}"
        else:
            # Treat as URL
            url_to_load = input_text
            # Basic URL sanitization: prepend http:// if no protocol is specified
            if not url_to_load.startswith(('http://', 'https://')):
                url_to_load = 'http://' + url_to_load
        
        # Update URL entry with the URL we are attempting to load
        self.url_entry.delete(0, 'end')
        self.url_entry.insert(0, url_to_load)

        logger.info(f"Attempting to load URL: {url_to_load}")
        self.status_label.configure(text=f"Loading: {url_to_load}")
        
        try:
            self.browser_frame.load_url(url_to_load)
            self.status_label.configure(text=f"Loaded: {url_to_load}")

            if add_to_history:
                # If navigating to a new URL, clear forward history
                if self.history_index < len(self.history) - 1:
                    self.history = self.history[:self.history_index + 1]
                self.history.append(url_to_load)
                self.history_index = len(self.history) - 1
            
        except Exception as e:
            logger.error(f"Failed to load URL {url_to_load}: {e}")
            self.status_label.configure(text=f"Error loading: {url_to_load} - {e}")
        
        self.update_navigation_buttons_state()

    def load_url_event(self, event=None):
        """
        An event handler method specifically designed to be triggered when the <Return> (Enter)
        key is pressed in the URL entry field.
        """
        self.load_url()

    def _on_link_click(self, url):
        """
        Callback for HtmlFrame when a link is clicked.
        Loads the clicked URL in the browser.
        """
        logger.info(f"Link clicked: {url}")
        self.load_url(url, add_to_history=True)

    def go_back(self):
        """
        Navigates back in history.
        """
        if self.history_index > 0:
            self.history_index -= 1
            self.load_url(self.history[self.history_index], add_to_history=False)
        self.update_navigation_buttons_state()

    def go_forward(self):
        """
        Navigates forward in history.
        """
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.load_url(self.history[self.history_index], add_to_history=False)
        self.update_navigation_buttons_state()

    def reload_page(self):
        """
        Reloads the current page.
        """
        if self.history:
            self.load_url(self.history[self.history_index], add_to_history=False)
        else:
            self.status_label.configure(text="No page to reload.")
        self.update_navigation_buttons_state()

    def go_home(self):
        """
        Navigates to the predefined home page.
        """
        self.load_url(self.home_page, add_to_history=True)
        self.update_navigation_buttons_state()

    def update_navigation_buttons_state(self):
        """
        Updates the enabled/disabled state of navigation buttons based on history.
        """
        self.back_button.configure(state=ctk.NORMAL if self.history_index > 0 else ctk.DISABLED)
        self.forward_button.configure(state=ctk.NORMAL if self.history_index < len(self.history) - 1 else ctk.DISABLED)
        self.reload_button.configure(state=ctk.NORMAL if self.history else ctk.DISABLED)

    def add_bookmark(self):
        current_url = self.url_entry.get()
        if not current_url:
            self.status_label.configure(text="No URL to bookmark.")
            return

        title = tk.simpledialog.askstring("Bookmark Title", "Enter title for this bookmark:", initialvalue=current_url)
        if title is None: # User cancelled
            return

        bookmarks_file = "bookmarks.json"
        bookmarks = []
        try:
            with open(bookmarks_file, 'r') as f:
                bookmarks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            bookmarks = [] # Start with empty list if file not found or corrupted

        new_bookmark = {"title": title, "url": current_url}
        # Avoid duplicate URLs
        if not any(b['url'] == new_bookmark['url'] for b in bookmarks):
            bookmarks.append(new_bookmark)
            try:
                with open(bookmarks_file, 'w') as f:
                    json.dump(bookmarks, f, indent=4)
                self.status_label.configure(text=f"Bookmark '{title}' added.")
                logger.info(f"Bookmark added: {new_bookmark}")
            except IOError as e:
                self.status_label.configure(text=f"Error saving bookmark: {e}")
                logger.error(f"Error saving bookmark: {e}")
        else:
            self.status_label.configure(text="Bookmark already exists.")

    def show_bookmarks(self):
        bookmarks_file = "bookmarks.json"
        bookmarks = []
        try:
            with open(bookmarks_file, 'r') as f:
                bookmarks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.status_label.configure(text="No bookmarks found.")
            return

        if not bookmarks:
            self.status_label.configure(text="No bookmarks found.")
            return

        # Create a new top-level window for bookmarks
        bookmark_window = ctk.CTkToplevel(self)
        bookmark_window.title("Bookmarks")
        bookmark_window.geometry("400x500")
        bookmark_window.transient(self.master) # Make it appear on top of the main window
        bookmark_window.grab_set() # Make it modal

        bookmark_window.grid_columnconfigure(0, weight=1)
        bookmark_window.grid_rowconfigure(0, weight=1)

        scrollable_frame = ctk.CTkScrollableFrame(bookmark_window)
        scrollable_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        scrollable_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(scrollable_frame, text="Your Bookmarks", font=("Arial", 16, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, pady=(0, 10), sticky="ew")

        for i, bookmark in enumerate(bookmarks):
            bookmark_frame = ctk.CTkFrame(scrollable_frame, fg_color=PIPBOY_FRAME)
            bookmark_frame.grid(row=i+1, column=0, pady=5, padx=5, sticky="ew")
            bookmark_frame.grid_columnconfigure(0, weight=1)

            title_label = ctk.CTkLabel(bookmark_frame, text=bookmark['title'], font=("Arial", 12, "bold"), text_color=PIPBOY_GREEN, wraplength=300, justify=tk.LEFT)
            title_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

            url_label = ctk.CTkLabel(bookmark_frame, text=bookmark['url'], font=("Arial", 10), text_color="gray", wraplength=300, justify=tk.LEFT)
            url_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)

            open_button = ctk.CTkButton(bookmark_frame, text="Open", width=60,
                                        command=lambda url=bookmark['url']: [self.load_url(url, add_to_history=True), bookmark_window.destroy()])
            open_button.grid(row=0, column=1, rowspan=2, padx=5, pady=5, sticky="e")