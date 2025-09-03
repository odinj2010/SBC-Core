import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
import shutil
import logging
from PIL import Image
from pathlib import Path
import concurrent.futures
import sys
import os
import subprocess
import time
import queue

# --- Configuration (Centralized Logging) ---
def setup_logging():
    """Sets up centralized logging for the application."""
    log_level = logging.INFO
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handlers = [logging.StreamHandler(sys.stdout)]
    log_file_path = Path(__file__).parent / "app_log.log"
    try:
        handlers.append(logging.FileHandler(log_file_path))
    except Exception as e:
        logging.warning(f"Could not set up file logging: {e}. Logging to console only.")
    logging.basicConfig(level=log_level, format=log_format, handlers=handlers)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("customtkinter").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- UI Constants ---
APP_FONT = ("Arial", 12)
HEADER_FONT = ("Arial", 20, "bold")
PIPBOY_FRAME = "#2a2d2e"
PIPBOY_GREEN = "#32f178"
MAIN_BG_COLOR = "#1a1a1a"
ITEM_NORMAL_BG_COLOR = "#1f1f1f"
LONG_PRESS_DURATION_MS = 500

# --- Clipboard Constants ---
CLIPBOARD_PATH_KEY = "path"
CLIPBOARD_OPERATION_KEY = "operation"
CLIPBOARD_OPERATION_COPY = "copy"
CLIPBOARD_OPERATION_CUT = "cut"

# --- Mock Controller for Standalone Testing ---
class MockController:
    """A mock controller for simulating application navigation and providing asset paths."""
    ASSETS_DIR = Path(__file__).parent / "assets"

    def show_page(self, page_name: str):
        logger.info(f"Navigating to {page_name} (Mock Controller)")

    def get_asset_path(self, filename: str) -> Path:
        return self.ASSETS_DIR / filename

    @staticmethod
    def _create_dummy_assets():
        if not MockController.ASSETS_DIR.exists():
            MockController.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
            try:
                Image.new('RGB', (20, 20), color='red').save(MockController.ASSETS_DIR / "folder_icon.png")
                Image.new('RGB', (20, 20), color='blue').save(MockController.ASSETS_DIR / "file_icon.png")
                Image.new('RGB', (20, 20), color='purple').save(MockController.ASSETS_DIR / "script_icon.png")
                logger.info("Created dummy icon files in assets directory.")
            except Exception as e:
                logging.warning(f"Could not create dummy icon files: {e}.")

# --- Progress Dialog for File Operations ---
class ProgressDialog(ctk.CTkToplevel):
    """A Toplevel window to show file operation progress."""
    def __init__(self, parent, title="Processing..."):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x120")
        self.transient(parent)
        self.grab_set()

        self.progress_queue = queue.Queue()
        self.total_size = 0
        self.copied_size = 0
        self._after_id = None # To store the after ID for the recurring check_queue call

        self.grid_columnconfigure(0, weight=1)
        self.label = ctk.CTkLabel(self, text="Preparing...", font=APP_FONT)
        self.label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.progress_bar = ctk.CTkProgressBar(self, mode='determinate')
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.details_label = ctk.CTkLabel(self, text="", font=APP_FONT)
        self.details_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        self.after(100, self.check_queue)

    def check_queue(self):
        """Checks the queue for progress updates from the worker thread."""
        try:
            while True:
                progress_update = self.progress_queue.get_nowait()
                if isinstance(progress_update, tuple):
                    current, total = progress_update
                    progress_val = current / total if total > 0 else 0
                    self.progress_bar.set(progress_val)
                    self.details_label.configure(text=f"{current/1024**2:.2f} MB / {total/1024**2:.2f} MB")
                elif isinstance(progress_update, str):
                    if progress_update == "done":
                        self.grab_release()
                        # Cancel the recurring after call before destroying
                        if hasattr(self, '_after_id'): # Check if the ID exists
                            self.after_cancel(self._after_id)
                        self.destroy()
                        return
                    else:
                        self.label.configure(text=progress_update)
        except queue.Empty:
            pass
        # Store the after ID so it can be cancelled later
        self._after_id = self.after(100, self.check_queue)

# --- Main Application Page ---
class FileBrowserPage(ctk.CTkFrame):
    """A CustomTkinter page for browsing and managing files and directories."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=MAIN_BG_COLOR)
        self.controller = controller
        self.current_path = Path.home()
        self.clipboard = {CLIPBOARD_PATH_KEY: None, CLIPBOARD_OPERATION_KEY: None}
        self.long_press_timer = None
        self.selected_item_frame = None
        self.selected_item_path = None
        
        # Pi-Optimization: Cache directory contents to speed up sorting
        self.directory_cache = []
        self.sort_criterion = tk.StringVar(value="Name")
        self.sort_order = tk.StringVar(value="Ascending")

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.folder_icon, self.file_icon, self.script_icon = None, None, None

        self._setup_layout()
        self.load_icons()
        self.navigate(self.current_path)

    def _setup_layout(self):
        """Sets up the main layout and widgets for the file browser page."""
        self.grid_columnconfigure(0, weight=4) # File list column
        self.grid_columnconfigure(1, weight=2) # Properties panel column
        self.grid_rowconfigure(3, weight=1)

        # --- Header ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        header_frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(header_frame, text="FILE BROWSER (PI-OPTIMIZED)", font=HEADER_FONT, text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header_frame, text="Back to Home", command=lambda: self.controller.show_page("HomePage"),
                      font=APP_FONT, fg_color=PIPBOY_FRAME, hover_color=PIPBOY_GREEN).grid(row=0, column=1, sticky="e")

        # --- Top Bar with Breadcrumbs ---
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        top_bar.grid_columnconfigure(1, weight=1)
        self.up_button = ctk.CTkButton(top_bar, text="↑", font=APP_FONT, width=40, command=self.go_up,
                                        fg_color=PIPBOY_FRAME, hover_color=PIPBOY_GREEN)
        self.up_button.grid(row=0, column=0, padx=(0, 5), sticky="w")
        self.breadcrumb_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        self.breadcrumb_frame.grid(row=0, column=1, sticky="ew")
        self.home_button = ctk.CTkButton(top_bar, text="Home", font=APP_FONT, width=60, command=lambda: self.navigate(Path.home()),
                                         fg_color=PIPBOY_FRAME, hover_color=PIPBOY_GREEN)
        self.home_button.grid(row=0, column=2, padx=(5, 0), sticky="e")

        # --- Sorting Controls ---
        sorting_frame = ctk.CTkFrame(self, fg_color="transparent")
        sorting_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(sorting_frame, text="Sort by:", font=APP_FONT).pack(side="left", padx=(0, 5))
        ctk.CTkOptionMenu(sorting_frame, variable=self.sort_criterion, values=["Name", "Size", "Date"],
                          font=APP_FONT, fg_color=PIPBOY_FRAME, button_color=PIPBOY_FRAME, command=lambda _: self._update_display()).pack(side="left", padx=5)
        ctk.CTkOptionMenu(sorting_frame, variable=self.sort_order, values=["Ascending", "Descending"],
                          font=APP_FONT, fg_color=PIPBOY_FRAME, button_color=PIPBOY_FRAME, command=lambda _: self._update_display()).pack(side="left")

        # --- Main File List ---
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Contents", label_text_color=PIPBOY_GREEN,
                                                   fg_color=PIPBOY_FRAME, label_font=APP_FONT)
        self.scroll_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        self._bind_background_events(self.scroll_frame)
        self._bind_background_events(self.scroll_frame._parent_canvas) # Bind to inner canvas too

        # --- Properties Panel ---
        self.properties_panel = ctk.CTkFrame(self, fg_color=PIPBOY_FRAME)
        self.properties_panel.grid(row=3, column=1, sticky="nsew", padx=(0, 10), pady=5)
        self.properties_panel.grid_columnconfigure(0, weight=1)

    def _bind_background_events(self, widget):
        widget.bind("<ButtonPress-1>", lambda e: self.on_bg_press(e))
        widget.bind("<ButtonRelease-1>", lambda e: self.on_bg_release(e))
        widget.bind("<ButtonRelease-3>", lambda e: self.on_bg_right_click(e))

    def load_icons(self):
        try:
            assets_dir = Path(self.controller.ASSETS_DIR)
            if not assets_dir.is_dir(): assets_dir = Path(__file__).parent / "assets"
            
            with Image.open(assets_dir / "folder_icon.png") as img: self.folder_icon = ctk.CTkImage(img.resize((20, 20), Image.LANCZOS))
            with Image.open(assets_dir / "file_icon.png") as img: self.file_icon = ctk.CTkImage(img.resize((20, 20), Image.LANCZOS))
            with Image.open(assets_dir / "script_icon.png") as img: self.script_icon = ctk.CTkImage(img.resize((20, 20), Image.LANCZOS))
            logger.info("File browser icons loaded.")
        except Exception as e:
            logger.warning(f"Could not load one or more icons: {e}. Falling back to text.")
            self.folder_icon, self.file_icon, self.script_icon = None, None, None

    def _update_breadcrumbs(self):
        if not self.breadcrumb_frame.winfo_exists():
            return
        for widget in self.breadcrumb_frame.winfo_children():
            widget.destroy()
        
        path_parts = self.current_path.parts
        
        for i, part in enumerate(path_parts):
            # For Windows drive letters, Path.parts[0] is 'C:\'
            # For other parts, it's just the name.
            # For the root of a drive, display the drive letter.
            if i == 0 and sys.platform == "win32" and len(path_parts) > 1:
                display_text = part.replace('\\', '') # Remove trailing backslash for display
            else:
                display_text = part

            # Don't create a button for the final part (current directory)
            if i < len(path_parts) - 1:
                p = Path(*path_parts[:i+1])
                btn = ctk.CTkButton(self.breadcrumb_frame, text=display_text, font=APP_FONT,
                                    command=lambda path=p: self.navigate(path),
                                    fg_color="transparent", text_color=PIPBOY_GREEN, hover=False, width=10)
                btn.pack(side="left")
                ctk.CTkLabel(self.breadcrumb_frame, text=">", font=APP_FONT, text_color="gray").pack(side="left")
            else:
                # Add the current directory as a non-clickable label
                ctk.CTkLabel(self.breadcrumb_frame, text=display_text, font=APP_FONT, text_color="white").pack(side="left")

    def navigate(self, path: Path):
        try:
            resolved_path = path.resolve()
            if not resolved_path.is_dir():
                messagebox.showerror("Error", "Path is not a directory.", parent=self)
                return

            self.current_path = resolved_path
            self._update_breadcrumbs()
            self.deselect_all()
            
            # Pi-Optimization: Load file stats into a cache in the background
            def _load_cache():
                temp_cache = []
                try:
                    for p in self.current_path.iterdir():
                        if not p.name.startswith('.'):
                            try:
                                temp_cache.append({'path': p, 'stat': p.stat()})
                            except FileNotFoundError:
                                continue # File deleted during scan
                except PermissionError:
                    self.after(0, lambda: messagebox.showerror("Permission Denied", f"Cannot access directory:\n{path}", parent=self))
                    return []
                return temp_cache

            def _on_cache_loaded(future):
                try:
                    self.directory_cache = future.result()
                    logger.info(f"Cache loaded for {self.current_path}. Items: {len(self.directory_cache)}")
                except Exception as e:
                    logger.error(f"Error loading cache for {self.current_path}: {e}")
                    self.directory_cache = [] # Ensure cache is empty on error
                    self.after(0, lambda: messagebox.showerror("Error", f"Failed to load directory contents:\n{e}", parent=self))
                finally:
                    self._update_display() # Always update display, even if cache loading failed
                    logger.info(f"Navigated to: {self.current_path}")

            self.executor.submit(_load_cache).add_done_callback(_on_cache_loaded)
        except Exception as e:
            messagebox.showerror("Navigation Error", f"Could not access path:\n{e}", parent=self)
            logger.exception(f"Error during navigation to {path}")

    def _update_display(self):
        """Sorts the cache and populates the scroll frame. Called after cache is loaded."""
        if not self.scroll_frame.winfo_exists():
            return
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Pi-Optimization: Sort the in-memory cache, not by accessing disk
        criterion = self.sort_criterion.get()
        is_desc = self.sort_order.get() == "Descending"
        
        def sort_key(item):
            p = item['path']
            s = item['stat']
            if criterion == "Name":
                return p.name.lower()
            elif criterion == "Size":
                return s.st_size
            elif criterion == "Date":
                return s.st_mtime
            return p.name.lower()

        sorted_cache = sorted(self.directory_cache, key=sort_key, reverse=is_desc)
        
        # Always put directories first
        sorted_cache.sort(key=lambda item: not item['path'].is_dir(), reverse=False)

        for item_data in sorted_cache:
            self.create_item_widget(item_data['path'])

    def create_item_widget(self, item_path: Path):
        is_dir = item_path.is_dir()
        item_frame = ctk.CTkFrame(self.scroll_frame, fg_color=ITEM_NORMAL_BG_COLOR, corner_radius=4)
        item_frame.pack(fill="x", pady=2, padx=2)

        icon = self.folder_icon if is_dir else self.file_icon
        text_icon = "📁" if is_dir else "📄"
        if item_path.suffix.lower() in ['.py', '.sh']:
            icon = self.script_icon
            text_icon = "📜"

        icon_label = ctk.CTkLabel(item_frame, text=text_icon if icon is None else "", image=icon, compound="left", font=APP_FONT)
        icon_label.pack(side="left", padx=5)

        name_label = ctk.CTkLabel(item_frame, text=item_path.name, font=APP_FONT, anchor="w")
        name_label.pack(side="left", fill="x", expand=True)

        for widget in [item_frame, icon_label, name_label]:
            widget.bind("<ButtonPress-1>", lambda e, p=item_path, f=item_frame: self.on_item_press(e, p, f))
            widget.bind("<ButtonRelease-1>", lambda e: self.on_item_release(e))
            widget.bind("<ButtonRelease-3>", lambda e, p=item_path, f=item_frame: self.on_item_right_click(e, p, f))
            if is_dir:
                widget.bind("<Double-1>", lambda e, p=item_path: self.navigate(p))
            else: # Bind double click on files to open them
                widget.bind("<Double-1>", lambda e, p=item_path: self.open_item(p))

    def go_up(self):
        if self.current_path.parent != self.current_path:
            self.navigate(self.current_path.parent)

    def select_item(self, item_frame: ctk.CTkFrame, item_path: Path):
        self.deselect_all()
        self.selected_item_frame = item_frame
        self.selected_item_path = item_path
        self.selected_item_frame.configure(fg_color=PIPBOY_FRAME)
        self.update_properties_panel(item_path)

    def deselect_all(self):
        if self.selected_item_frame and self.selected_item_frame.winfo_exists():
            self.selected_item_frame.configure(fg_color=ITEM_NORMAL_BG_COLOR)
        self.selected_item_frame = None
        self.selected_item_path = None
        for widget in self.properties_panel.winfo_children():
            widget.destroy()

    def update_properties_panel(self, path: Path):
        for widget in self.properties_panel.winfo_children(): widget.destroy()
        
        try:
            stats = path.stat()
            ctk.CTkLabel(self.properties_panel, text=f"Name:", font=APP_FONT, anchor="w").pack(fill="x", padx=10, pady=(10, 0))
            ctk.CTkLabel(self.properties_panel, text=path.name, font=APP_FONT, text_color=PIPBOY_GREEN, anchor="w", wraplength=200).pack(fill="x", padx=10)
            
            size_mb = stats.st_size / (1024 * 1024)
            ctk.CTkLabel(self.properties_panel, text=f"Size: {size_mb:.2f} MB", font=APP_FONT, anchor="w").pack(fill="x", padx=10, pady=5)
            
            mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.st_mtime))
            ctk.CTkLabel(self.properties_panel, text=f"Modified: {mod_time}", font=APP_FONT, anchor="w").pack(fill="x", padx=10, pady=5)

            if path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']:
                preview_label = ctk.CTkLabel(self.properties_panel, text="Loading preview...", font=APP_FONT)
                preview_label.pack(pady=10)
                
                # Pi-Optimization: Load thumbnail in background to prevent UI lag
                def _load_thumb():
                    with Image.open(path) as img:
                        img.thumbnail((200, 200))
                        return ctk.CTkImage(img, size=img.size)
                
                def _on_thumb_loaded(future):
                    try:
                        image = future.result()
                        if preview_label.winfo_exists():
                           preview_label.configure(text="", image=image)
                    except Exception as e:
                        logger.warning(f"Failed to create preview for {path}: {e}")
                        if preview_label.winfo_exists():
                           preview_label.configure(text="Preview failed")
                
                self.executor.submit(_load_thumb).add_done_callback(_on_thumb_loaded)

        except Exception as e:
            logger.error(f"Could not get properties for {path}: {e}")
            ctk.CTkLabel(self.properties_panel, text="Could not load properties.", font=APP_FONT).pack()

    # --- Event Handlers (Press, Release, Clicks) ---
    def on_item_press(self, event, path: Path, frame: ctk.CTkFrame):
        self.select_item(frame, path)
        if self.long_press_timer: self.after_cancel(self.long_press_timer)
        self.long_press_timer = self.after(LONG_PRESS_DURATION_MS, lambda: self.show_context_menu_item(event, path))

    def on_item_release(self, event):
        if self.long_press_timer: self.after_cancel(self.long_press_timer)
        self.long_press_timer = None

    def on_item_right_click(self, event, path: Path, frame: ctk.CTkFrame):
        self.select_item(frame, path)
        if self.long_press_timer: self.after_cancel(self.long_press_timer)
        self.show_context_menu_item(event, path)

    def on_bg_press(self, event):
        self.deselect_all()
        if self.long_press_timer: self.after_cancel(self.long_press_timer)
        self.long_press_timer = self.after(LONG_PRESS_DURATION_MS, lambda: self.show_context_menu_bg(event))

    def on_bg_release(self, event):
        if self.long_press_timer: self.after_cancel(self.long_press_timer)

    def on_bg_right_click(self, event):
        self.deselect_all()
        if self.long_press_timer: self.after_cancel(self.long_press_timer)
        self.show_context_menu_bg(event)
        
    def _create_context_menu(self) -> tk.Menu:
        return tk.Menu(self, tearoff=0, bg=PIPBOY_FRAME, fg="white", font=APP_FONT,
                       activebackground=PIPBOY_GREEN, activeforeground="black", border=0, bd=0)

    def show_context_menu_item(self, event, path: Path):
        menu = self._create_context_menu()
        if not path.is_dir():
            menu.add_command(label="Open", command=lambda: self.open_item(path))
            if path.suffix in ['.py', '.sh']:
                menu.add_command(label="Execute in Terminal", command=lambda: self.execute_script(path))
            menu.add_separator()
        menu.add_command(label="Copy", command=lambda: self.copy_item(path))
        menu.add_command(label="Cut", command=lambda: self.cut_item(path))
        menu.add_command(label="Rename", command=lambda: self.rename_item(path))
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self.delete_item(path))
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def show_context_menu_bg(self, event):
        menu = self._create_context_menu()
        paste_state = "normal" if self.clipboard.get(CLIPBOARD_PATH_KEY) else "disabled"
        menu.add_command(label="Paste", state=paste_state, command=self.paste_item)
        menu.add_separator()
        menu.add_command(label="New Folder", command=self.create_folder)
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    # --- Core File Operations ---
    def open_item(self, path: Path):
        """Opens a file with the default system application (for Linux/Pi)."""
        if path.is_dir():
            self.navigate(path)
            return
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": subprocess.run(["open", path])
            else: subprocess.run(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file:\n{e}", parent=self)

    def execute_script(self, path: Path):
        """Executes a script in a new terminal window."""
        try:
            # Command assumes a common terminal emulator on Raspberry Pi OS.
            # It changes to the script's directory before running it.
            cmd = "lxterminal -e 'bash -c \"cd \"{}\" && ./{}; echo Press Enter to exit...; read\"'".format(str(path.parent), str(path.name))
            subprocess.Popen(cmd, shell=True)
            logger.info(f"Executing script: {path}")
        except Exception as e:
            messagebox.showerror("Execution Error", f"Failed to execute script:\n{e}", parent=self)

    def _execute_file_operation(self, operation_func, *args, success_msg: str, error_msg: str):
        def run_op():
            try:
                result = operation_func(*args)
                self.after(0, lambda: self._handle_file_operation_result(True, result or success_msg))
            except Exception as e:
                self.after(0, lambda: self._handle_file_operation_result(False, f"{error_msg}\n{e}"))
        self.executor.submit(run_op)

    def _handle_file_operation_result(self, success: bool, message: str):
        if success:
            logger.info(message)
            self.navigate(self.current_path)
        else:
            logger.error(f"File operation failed: {message}")
            messagebox.showerror("Error", f"File operation failed:\n{message}", parent=self)
            self.navigate(self.current_path) # Refresh even on failure

    def copy_item(self, path: Path):
        self.clipboard = {CLIPBOARD_PATH_KEY: path, CLIPBOARD_OPERATION_KEY: CLIPBOARD_OPERATION_COPY}
        logger.info(f"Copied: {path}")

    def cut_item(self, path: Path):
        self.clipboard = {CLIPBOARD_PATH_KEY: path, CLIPBOARD_OPERATION_KEY: CLIPBOARD_OPERATION_CUT}
        logger.info(f"Cut: {path}")

    def paste_item(self):
        src_path = self.clipboard.get(CLIPBOARD_PATH_KEY)
        op = self.clipboard.get(CLIPBOARD_OPERATION_KEY)
        if not src_path or not src_path.exists():
            messagebox.showerror("Paste Error", "Source item does not exist.", parent=self)
            return

        dest_path = self.current_path / src_path.name
        if dest_path.exists():
            if not messagebox.askyesno("Confirm", f"'{dest_path.name}' already exists. Overwrite?", parent=self):
                return
        
        # --- Progress Bar implementation for Copy ---
        if op == CLIPBOARD_OPERATION_COPY:
            progress_dialog = ProgressDialog(self, title=f"Copying {src_path.name}")
            
            def _copy_with_progress():
                try:
                    total_size = sum(f.stat().st_size for f in src_path.glob('**/*') if f.is_file()) if src_path.is_dir() else src_path.stat().st_size
                    progress_dialog.progress_queue.put(f"Copying to {self.current_path.name}")

                    if src_path.is_dir():
                        shutil.copytree(src_path, dest_path, dirs_exist_ok=True) # shutil is fast; fine for Pi
                    else:
                        shutil.copy2(src_path, dest_path)
                    
                    progress_dialog.progress_queue.put("done")
                    return f"Copied '{src_path.name}' successfully."
                except Exception as e:
                    progress_dialog.progress_queue.put("done")
                    raise e # Re-raise to be caught by _execute_file_operation

            self._execute_file_operation(
                _copy_with_progress,
                success_msg="Copy successful",
                error_msg=f"Failed to copy '{src_path.name}'"
            )
        elif op == CLIPBOARD_OPERATION_CUT:
            def _do_move():
                shutil.move(src_path, dest_path)
                self.after(0, self.clear_clipboard)
                return f"Moved '{src_path.name}' successfully."
            
            self._execute_file_operation(
                _do_move,
                success_msg="Move successful",
                error_msg=f"Failed to move '{src_path.name}'"
            )

    def clear_clipboard(self):
        self.clipboard = {CLIPBOARD_PATH_KEY: None, CLIPBOARD_OPERATION_KEY: None}
        logger.info("Clipboard cleared.")

    def delete_item(self, path: Path):
        item_type = "directory" if path.is_dir() else "file"
        if not messagebox.askyesno("Confirm Delete", f"Permanently delete the {item_type} '{path.name}'?", parent=self):
            return
        def _do_delete():
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
        self._execute_file_operation(_do_delete, success_msg=f"Deleted '{path.name}'", error_msg=f"Failed to delete '{path.name}'")

    def rename_item(self, path: Path):
        old_name = path.name
        dialog = ctk.CTkInputDialog(text=f"New name for '{old_name}':", title="Rename")
        new_name = dialog.get_input()
        if not new_name or new_name == old_name: return
        
        new_path = path.parent / new_name
        if new_path.exists():
            messagebox.showerror("Error", f"'{new_name}' already exists.", parent=self)
            return
        def _do_rename(): path.rename(new_path)
        self._execute_file_operation(_do_rename, success_msg=f"Renamed to '{new_name}'", error_msg=f"Failed to rename '{old_name}'")

    def create_folder(self):
        dialog = ctk.CTkInputDialog(text="Enter new folder name:", title="Create Folder")
        folder_name = dialog.get_input()
        if not folder_name: return
        
        new_folder_path = self.current_path / folder_name
        if new_folder_path.exists():
            messagebox.showerror("Error", f"'{folder_name}' already exists.", parent=self)
            return
        def _do_create(): new_folder_path.mkdir()
        self._execute_file_operation(_do_create, success_msg=f"Created folder '{folder_name}'", error_msg=f"Failed to create '{folder_name}'")

    def destroy(self):
        logger.info("Shutting down file operation executor.")
        self.executor.shutdown(wait=True)
        super().destroy()

    def on_hide(self):
        if self.long_press_timer:
            self.after_cancel(self.long_press_timer)
            self.long_press_timer = None
        
        # Explicitly destroy all widgets in scroll_frame and properties_panel
        for widget in self.scroll_frame.winfo_children():
            if widget.winfo_exists(): # Check if widget still exists before destroying
                widget.destroy()
        for widget in self.properties_panel.winfo_children():
            if widget.winfo_exists(): # Check if widget still exists before destroying
                widget.destroy()

# --- Main Execution Block ---
if __name__ == "__main__":
    setup_logging()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")

    app = ctk.CTk()
    app.title("Raspberry Pi File Browser")
    app.geometry("960x600")

    controller = MockController()
    controller._create_dummy_assets()

    file_browser_page = FileBrowserPage(app, controller)
    file_browser_page.pack(fill="both", expand=True)

    # Setup a test directory
    test_dir = Path.home() / "file_browser_test_dir"
    test_dir.mkdir(exist_ok=True)
    (test_dir / "document.txt").write_text("Test document.")
    (test_dir / "script.py").write_text("print('Hello from the Pi!')")
    (test_dir / "run.sh").write_text("#!/bin/bash\necho 'Hello from a shell script!'")
    (test_dir / "another_folder").mkdir(exist_ok=True)

    file_browser_page.navigate(test_dir)

    app.mainloop()