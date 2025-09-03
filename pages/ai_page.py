import tkinter as tk
import customtkinter as ctk
import threading
import logging
import queue
import os
import re
import tempfile
from tkinter import messagebox
import shutil
from typing import Tuple

# --- Conditional Imports and Global Flags ---
GPIO_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    GPIO.setwarnings(False)
except ImportError:
    pass

GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    pass

PIPER_AVAILABLE = False
try:
    from piper.voice import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    pass

try:
    from .prompts import DEFAULT_PROMPT, CODE_PROMPT, CMD_PROMPT
except ImportError:
    logging.warning("prompts.py module not found. Using default internal prompts.")
    DEFAULT_PROMPT = "You are a helpful AI assistant. Respond concisely."
    CODE_PROMPT = "You are an expert Python coder. Provide code snippets only, within markdown blocks."
    CMD_PROMPT = "You are a command-line interpreter. Respond with shell commands."

logger = logging.getLogger(__name__)

# --- Constants ---
PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME = "#2a2d2e"
DARK_BACKGROUND = "#1a1a1a"
USER_BUBBLE_COLOR = "#004A20"
SYSTEM_BUBBLE_COLOR = "#4a4d4e"
AI_BUBBLE_COLOR = PIPBOY_FRAME
INDICATOR_COLOR = "#FFD700"
TEXT_COLOR_PRIMARY = "#FFFFFF"
TEXT_COLOR_SECONDARY = PIPBOY_GREEN
TEXT_COLOR_SYSTEM = "#FFD700"
MAX_MESSAGE_WIDTH = 500

class AIPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, controller: object, llm=None):
        super().__init__(parent, fg_color=DARK_BACKGROUND)
        self.controller = controller
        self.llm = llm

        self.response_queue: queue.Queue = queue.Queue()
        self.ui_update_queue: queue.Queue = queue.Queue()
        self.is_thinking: bool = False
        self._current_ai_bubble_label: ctk.CTkLabel | None = None
        self._full_response_text: str = ""
        self.current_prompt: str = DEFAULT_PROMPT
        self.chat_history: list[dict] = []

        self._piper_voice: PiperVoice | None = None
        self._piper_available: bool = PIPER_AVAILABLE

        self._configure_gemini()
        self._load_tts_model()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self._create_widgets()
        self._process_response_queue()
        self._process_ui_queue() # Start processing UI updates
        self._show_welcome_message()

    def _create_widgets(self) -> None:
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        self.title_label = ctk.CTkLabel(header_frame, text="V.I.N.C.E.", font=("Arial", 20, "bold"), text_color=PIPBOY_GREEN)
        self.title_label.pack(side="left", padx=10)
        back_button = ctk.CTkButton(header_frame, text="Back to Home", command=lambda: self.controller.show_page("HomePage"))
        back_button.pack(side="right", padx=10)
        self.speaking_indicator = ctk.CTkLabel(header_frame, text=" ◄ SPEAKING", font=("Arial", 10, "bold"), text_color=INDICATOR_COLOR)
        self.speaking_indicator.pack_forget()

        # Chat and Input
        chat_input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        chat_input_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        chat_input_frame.grid_rowconfigure(0, weight=1)
        chat_input_frame.grid_columnconfigure(0, weight=1)
        self.chat_frame = ctk.CTkScrollableFrame(chat_input_frame, fg_color=DARK_BACKGROUND)
        self.chat_frame.grid(row=0, column=0, sticky="nsew")
        self.entry = ctk.CTkEntry(chat_input_frame, placeholder_text="Ask V.I.N.C.E. a question...", font=("Arial", 12), border_color=PIPBOY_FRAME, fg_color=PIPBOY_FRAME, text_color=TEXT_COLOR_PRIMARY)
        self.entry.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.entry.bind("<Return>", self._send_message)
        
        # Sidebar
        sidebar_frame = ctk.CTkFrame(main_frame, width=150, fg_color=PIPBOY_FRAME)
        sidebar_frame.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=10)
        sidebar_label = ctk.CTkLabel(sidebar_frame, text="AI Modes", font=("Arial", 14, "bold"), text_color=PIPBOY_GREEN)
        sidebar_label.pack(pady=10)
        ctk.CTkButton(sidebar_frame, text="/chat", command=lambda: self._set_mode("chat")).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(sidebar_frame, text="/code", command=lambda: self._set_mode("code")).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(sidebar_frame, text="/cmd", command=lambda: self._set_mode("cmd")).pack(fill="x", padx=10, pady=5)

    def _set_mode(self, mode: str):
        mode_map = {"chat": DEFAULT_PROMPT, "code": CODE_PROMPT, "cmd": CMD_PROMPT}
        self.current_prompt = mode_map.get(mode, DEFAULT_PROMPT)
        self._add_message("system", f"V.I.N.C.E. set to {mode.capitalize()} Mode.")
        self.entry.focus()

    def _configure_gemini(self):
        if not GEMINI_AVAILABLE: return
        api_key = self.controller.config.get('GEMINI', 'api_key', fallback=None)
        if api_key and api_key.startswith('AIza'):
            try:
                genai.configure(api_key=api_key)
                logger.info("Gemini API configured.")
            except Exception as e:
                logger.error(f"Failed to configure Gemini API: {e}")
        else:
            logger.warning("Gemini API key not found or invalid.")

    def _load_tts_model(self):
        if not PIPER_AVAILABLE:
            self._piper_available = False
            return
        try:
            relative_path = self.controller.config.get('PATHS', 'piper_model_path', fallback='').strip()
            model_path = os.path.join(self.controller.app_dir, relative_path)
            config_path = f"{model_path}.json"
            if not os.path.exists(model_path): raise FileNotFoundError
            self._piper_voice = PiperVoice.load(model_path, config_path=config_path)
            self._piper_available = True
            logger.info("Piper TTS model loaded.")
        except Exception as e:
            self._piper_voice = None
            self._piper_available = False
            logger.error(f"Failed to load Piper TTS model: {e}")

    def _show_welcome_message(self):
        for widget in self.chat_frame.winfo_children(): widget.destroy()
        backend = self.controller.config.get('AI', 'backend', fallback='local')
        if self.llm is None and backend == 'local':
            self._add_message("ai", "V.I.N.C.E. OFFLINE. Model failed to load. Check logs for details.")
        else:
            welcome_msg = f"V.I.N.C.E. is online using the {backend.capitalize()} backend."
            self._add_message("ai", welcome_msg)
            self._speak_text(welcome_msg)

    def _speak_text(self, text_to_speak: str):
        if not self._piper_available or not hasattr(self.controller, 'radio_play_tts') or not text_to_speak:
            return

        def run_tts():
            self.ui_update_queue.put("show_indicator")
            sound_file_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio_file:
                    sound_file_path = temp_audio_file.name
                
                with open(sound_file_path, "wb") as f:
                    self._piper_voice.synthesize(text_to_speak, f)
                
                # Delegate playback to the main controller
                self.controller.radio_play_tts(sound_file_path)

            except Exception as e:
                logger.error(f"Error during TTS generation: {e}")
                if sound_file_path and os.path.exists(sound_file_path):
                    try: os.remove(sound_file_path) # Clean up if something went wrong before playback
                    except OSError: pass
            finally:
                # The controller will be responsible for deleting the file after playback
                self.ui_update_queue.put("hide_indicator")

        threading.Thread(target=run_tts, daemon=True).start()

    def _add_message(self, sender: str, message: str, is_stream: bool = False):
        color_map = {"user": USER_BUBBLE_COLOR, "system": SYSTEM_BUBBLE_COLOR, "ai": AI_BUBBLE_COLOR}
        text_color_map = {"user": TEXT_COLOR_PRIMARY, "system": TEXT_COLOR_SYSTEM, "ai": TEXT_COLOR_SECONDARY}
        anchor_map = {"user": "e", "system": "w", "ai": "w"}
        
        bubble = ctk.CTkFrame(self.chat_frame, fg_color=color_map.get(sender), corner_radius=10)
        bubble.pack(anchor=anchor_map.get(sender), padx=10, pady=4)
        label = ctk.CTkLabel(bubble, text=message, wraplength=MAX_MESSAGE_WIDTH, justify="left", text_color=text_color_map.get(sender))
        label.pack(padx=8, pady=5)
        
        if is_stream: self._current_ai_bubble_label = label
        if sender in ["user", "ai"] and not is_stream:
            self.chat_history.append({"role": "user" if sender == "user" else "model", "content": message})
        self.after(50, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))

    def _send_message(self, event=None):
        if self.is_thinking: return
        query = self.entry.get().strip()
        if not query: return
        
        self._add_message("user", query)
        self.entry.delete(0, "end")
        
        if query.lower() in ["/code", "/chat", "/cmd"]:
            self._set_mode(query.lower().replace("/", ""))
            return

        self._add_message("ai", "", is_stream=True)
        self._full_response_text = ""
        self.is_thinking = True
        self.entry.configure(state="disabled", placeholder_text="V.I.N.C.E. is thinking...")
        threading.Thread(target=self._ask_ai, args=(query,), daemon=True).start()

    def _get_conversation_context(self, num_turns: int = 3) -> str:
        context_parts = []
        for entry in self.chat_history[-(2*num_turns):]:
            role = "User" if entry["role"] == "user" else "V.I.N.C.E."
            context_parts.append(f"{role}: {entry['content']}")
        return "\n".join(context_parts)

    def _ask_ai(self, query: str):
        backend = self.controller.config.get('AI', 'backend', fallback='local')
        context = self._get_conversation_context()
        full_prompt = f"{self.current_prompt}\n\n{context}\n\nUser: {query}"
        
        try:
            if backend == 'gemini':
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(full_prompt, stream=True)
                for chunk in response: self.response_queue.put(chunk.text)
            else: # local
                if self.llm is None: raise ValueError("Local LLM not loaded.")
                stream = self.llm(full_prompt, max_tokens=1024, stop=["\nUser:"], stream=True)
                for output in stream: self.response_queue.put(output["choices"][0]["text"])
        except Exception as e:
            logger.error(f"Error with AI backend: {e}")
            self.response_queue.put(f"[ERROR: {e}]")
        finally:
            self.response_queue.put(None)

    def _process_response_queue(self):
        try:
            while not self.response_queue.empty():
                chunk = self.response_queue.get_nowait()
                if chunk is None: # End of stream
                    try:
                        # --- NEW: Centralized end-of-stream processing ---
                        self._handle_response_completion(self._full_response_text)
                        
                        self.chat_history.append({"role": "model", "content": self._full_response_text})
                    except Exception as e:
                        logger.error(f"Error during AI response completion: {e}")
                        self._add_message("system", f"Error processing AI response: {e}")
                    finally:
                        self.is_thinking = False
                        self.entry.configure(state="normal", placeholder_text="Ask V.I.N.C.E. a question...")
                        self._full_response_text = ""
                        self._current_ai_bubble_label = None
                elif self._current_ai_bubble_label:
                    # Clean the chunk: remove any leading "V.I.N.C.E.:" or similar phrases
                    cleaned_chunk = chunk # No longer stripping prefixes, assuming fine-tuned model won't generate them
                    
                    current_text = self._current_ai_bubble_label.cget("text")
                    self._current_ai_bubble_label.configure(text=current_text + cleaned_chunk)
                    self._full_response_text += cleaned_chunk
        except queue.Empty:
            pass
        finally:
            self.after(50, self._process_response_queue)

    def _process_ui_queue(self):
        try:
            while not self.ui_update_queue.empty():
                message = self.ui_update_queue.get_nowait()
                if message == "show_indicator":
                    self.speaking_indicator.pack(side="left", padx=10)
                elif message == "hide_indicator":
                    self.speaking_indicator.pack_forget()
        except queue.Empty:
            pass
        finally:
            self.after(50, self._process_ui_queue) # Schedule itself to run again

    # --- NEW: Bug fix and AI enhancement logic ---
    def _handle_response_completion(self, final_text: str):
        """
        Processes the final, complete AI response.
        It extracts and executes commands, then cleans the text for display and TTS.
        """
        # Process commands first to get the text that should be spoken/displayed
        speakable_text, system_feedback = self._process_ai_commands(final_text)

        # Update the final bubble with the cleaned text
        if self._current_ai_bubble_label and self._current_ai_bubble_label.winfo_exists():
            self._current_ai_bubble_label.configure(text=speakable_text if speakable_text else "Command acknowledged.")
        
        # Speak the cleaned text
        self._speak_text(speakable_text)

        # If there was system feedback from a command, add it as a new message
        if system_feedback:
            self._add_message("system", system_feedback)

    def _process_ai_commands(self, text: str) -> Tuple[str, str]:
        """
        Parses AI response for command tags, executes them via the controller,
        and returns the cleaned (speakable) text and any system feedback.
        """
        # Regex to find any of our command tags
        command_pattern = re.compile(r"<\|(.*?)\|>")
        matches = command_pattern.finditer(text)
        
        clean_text = text
        feedback_messages = []

        for match in matches:
            full_tag = match.group(0)
            command_str = match.group(1)
            clean_text = clean_text.replace(full_tag, "") # Remove the tag from the text
            
            parts = command_str.split()
            command_name = parts[0]
            
            # Simple attribute parser (e.g., pin="23")
            args = {key: val.strip('"') for key, val in (part.split('=') for part in parts[1:])}

            success = False
            message = "Unknown command."

            try:
                if command_name == "execute_gpio_command":
                    pin = int(args.get("pin"))
                    state = args.get("state")
                    success, message = self.controller.request_gpio_action(pin, state)
                elif command_name == "execute_gpio_pulse":
                    pin = int(args.get("pin"))
                    interval = int(args.get("interval_ms"))
                    success, message = self.controller.request_gpio_pulse(pin, interval)
                elif command_name == "query_system_status":
                    query = args.get("query")
                    success, message = self.controller.request_system_status(query)
                elif command_name == "run_vehicle_diagnostics":
                    action = args.get("action")
                    success, message = self.controller.request_vehicle_diagnostics(action)
            except (ValueError, KeyError, TypeError) as e:
                message = f"Command parse error: {e}"
                success = False
            
            feedback = f"CMD: {command_name} {'OK' if success else 'FAIL'}. Response: {message}"
            feedback_messages.append(feedback)
            logger.info(feedback)

        # This part was incorrect in the original code, causing an error.
        # It seems like it was trying to append to clean_text_parts which was not defined.
        # The logic for clean_text should already be handled by the replace calls above.
        # I'm commenting it out as it's likely a remnant or incorrect logic.
        # clean_text_parts.append(text[last_idx:]) # Add any remaining text after the last command tag
        # clean_text = "".join(clean_text_parts)

        return clean_text.strip(), "\n".join(feedback_messages)