#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# =============================================================================
# WebSocket Radio Client with RDS, Audio, and Streaming
# =============================================================================
#
# Description:
#   Connects to FM-DX Webserver WebSocket servers  
#   (https://github.com/NoobishSVK/fm-dx-webserver) to receive FM radio 
#   metadata (RDS) and MP3 audio.
#   It can display the RDS information, optionally play the audio locally
#   using 'ffplay', and optionally re-encode the audio to AAC and stream it
#   over HTTP using 'ffmpeg' and 'aiohttp'. The application offers both a
#   graphical user interface (GUI) using Tkinter and a command-line interface
#   (CLI).
#
# Author:
#   Original work by antonioag95.
#
# Date:
#   March 31, 2025
#
# License:
#   This project is licensed under the GNU-GPL v3 License.
#
# =============================================================================
#
# Capabilities:
#   - WebSocket Client: Connects to separate text (RDS/JSON) and audio (MP3)
#     WebSocket endpoints provided by the server. Handles reconnection attempts.
#   - RDS Display: Parses JSON messages from the text WebSocket to display:
#     - Program Service name (PS)
#     - Program Identification code (PI)
#     - Program Type (PTY) name
#     - RadioText (RT) messages (supports RT+/RT)
#     - Traffic Program (TP) and Traffic Announcement (TA) flags
#     - Music/Speech (MS) flag
#     - Stereo/Mono indicator
#     - Transmitter Information (Name, City, Country/ITU, ERP, Polarity,
#       Distance, Azimuth) if provided by the server.
#     - Signal Strength (Current and Peak, assumes dBf unit from source)
#     - Active listener count (if provided by the server)
#   - Audio Playback: If 'ffplay' is installed and not in --restream-only mode,
#     pipes the received MP3 audio stream to ffplay for local playback.
#   - AAC Restreaming: If 'ffmpeg' and 'aiohttp' are installed and the
#     --stream flag is used, re-encodes the MP3 audio stream to AAC in real-time
#     and serves it via a local HTTP server. This allows other devices/apps
#     on the network to listen to the AAC stream.
#   - Interface Options:
#     - GUI Mode (Default): Uses Tkinter for a graphical display. Requires
#       Tkinter to be available in the Python environment.
#     - CLI Mode (--cli): Uses the console for display and interaction. Requires
#       the 'readchar' library for keyboard input.
#   - Restream-Only Mode (--restream-only): Disables local audio playback via
#     ffplay, focusing solely on receiving data and potentially restreaming.
#     Automatically enables AAC streaming (--stream). Useful for running on
#     servers or headless devices where local playback is not needed.
#
# =============================================================================
#
# Command-Line Interface (CLI) Options (--cli):
#
#   Usage:
#     python fm-dx-client.py --cli <server_address> [options]
#
#   Arguments:
#     server_address        Required. Server address and port
#                           (e.g., example.com:8073). HTTP/HTTPS scheme
#                           is optional (defaults to http/ws).
#
#   Options:
#     -s, --stream          Enable AAC restreaming. Requires 'ffmpeg' and
#                           'aiohttp'. Stream available at
#                           http://<your-ip>:<port>/stream.aac
#                           (Default: Disabled)
#     -p PORT, --port PORT  Port number for the AAC restreaming server.
#                           (Default: 8080)
#     --restream-only       Run without local ffplay audio output. Implies -s.
#                           (Default: Disabled)
#
#   CLI Interaction:
#     - Display: Shows current station info, RDS data, signal, etc.
#     - Tuning Input: Enter frequency in MHz (e.g., 97.3) in the input prompt.
#     - Keyboard Controls:
#       - Up/Right Arrow : Tune frequency up by step (default 100 kHz).
#       - Down/Left Arrow: Tune frequency down by step.
#       - Enter          : If frequency entered, tune to it. If empty, refresh display.
#       - Backspace      : Delete last character in frequency input.
#       - Esc            : Clear frequency input buffer.
#       - Ctrl+C         : Exit the application.
#
#   CLI Dependencies:
#     - Python Libraries: websockets, readchar
#     - External Programs: ffplay (optional, for audio), ffmpeg (optional, for streaming)
#
# =============================================================================
#
# Graphical User Interface (GUI) Options (Default):
#
#   Usage:
#     python fm-dx-client.py [server_address] [options]
#
#   Arguments:
#     server_address        Optional. Server address and port to pre-fill and
#                           optionally auto-connect to.
#
#   Options:
#     -s, --stream          Enable AAC restreaming on connect. Requires
#                           'ffmpeg' and 'aiohttp'. Status shown in status bar.
#                           (Default: Disabled)
#     -p PORT, --port PORT  Port number for the AAC restreaming server.
#                           (Default: 8080)
#     --restream-only       Run without local ffplay audio output. Implies -s.
#                           Window title indicates this mode.
#                           (Default: Disabled)
#
#   GUI Layout:
#     - Top Bar: Server address input, Connect/Disconnect button.
#     - Main Area (when connected):
#       - Station Name (PS), PI Code
#       - RDS Info (PTY, TP, TA, Stereo, Music/Speech flags)
#       - Frequency Display
#       - Signal Strength Display (Current, Peak)
#       - RadioText Display
#       - Transmitter Info Display
#       - Tuning Controls (Up/Down buttons, Manual frequency entry + Tune button)
#     - Status Bar (Bottom): Connection status, Listener count, Streaming status.
#
#   GUI Interaction:
#     - Connect: Enter server address, click "Connect".
#     - Disconnect: Click "Disconnect".
#     - Tune: Use "<" / ">" buttons, or enter frequency (MHz) and click "Tune" or press Enter.
#     - Keyboard Shortcuts:
#       - Left/PageDown : Tune down.
#       - Right/PageUp  : Tune up.
#
#   GUI Dependencies:
#     - Python Libraries: websockets, tkinter (usually built-in)
#     - External Programs: ffplay (optional, for audio), ffmpeg (optional, for streaming), aiohttp (optional, for streaming)
#
# =============================================================================

# --- Core Imports ---
import asyncio
import sys
import subprocess
import json
import shutil
import signal
import traceback
import os
import argparse
from urllib.parse import urlparse, urlunparse
import threading
import time
import queue
from collections import deque

# --- GUI Imports (Conditional) ---
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, font as tkFont
    import ctypes  # For Windows DPI awareness
    tkinter_available = True
except ImportError:
    tkinter_available = False
    # Informational, script can proceed in CLI mode or exit later if GUI needed
    # print("Info: Tkinter not available. GUI mode (--gui) will not work.")

# --- CLI Imports (Conditional) ---
try:
    import readchar
    readchar_available = True
except ImportError:
    readchar_available = False
    # Informational, GUI might still work
    # print("Info: 'readchar' not found. CLI mode (--cli) will not work.")

# --- Networking Imports ---
try:
    import websockets
except ImportError:
    # Fatal if websockets is missing, as it's core functionality
    print("Fatal Error: 'websockets' library not found.")
    print("Install using: pip install websockets")
    if tkinter_available:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror(
                "Import Error",
                "Fatal Error: 'websockets' library not found.\n"
                "Install using: pip install websockets"
            )
            root.destroy()
        except tk.TclError:
            pass # Tkinter itself might fail early
    sys.exit(1)

# --- Streaming Imports (Conditional) ---
aiohttp_available = False
try:
    import aiohttp
    from aiohttp import web
    aiohttp_available = True
except ImportError:
    # Informational, streaming feature will be disabled if selected
    # print("Info: 'aiohttp' library not found. Install using: pip install aiohttp")
    # print("Info: AAC restreaming (-s) feature will be unavailable.")
    pass

# --- Configuration Constants ---
WEBSOCKET_AUDIO_PATH = "/audio" # WebSocket path for MP3 audio data
WEBSOCKET_TEXT_PATH = "/text"   # WebSocket path for JSON RDS/metadata
MIN_FREQ_MHZ = 87.5             # Minimum tunable FM frequency
MAX_FREQ_MHZ = 108.0            # Maximum tunable FM frequency
FREQ_STEP_KHZ = 100             # Tuning step in kHz
RECONNECT_DELAY_SECONDS = 5     # Delay before attempting WebSocket reconnection
AUDIO_WEBSOCKET_TIMEOUT = 15    # Timeout for receiving audio data / keepalive ping
TEXT_WEBSOCKET_TIMEOUT = 10     # Timeout for initial text WebSocket connection

# --- ffplay Configuration (Local Audio Playback) ---
FFPLAY_CMD = [
    "ffplay",
    "-probesize", "32",          # Lower probesize for faster start
    "-analyzeduration", "0",     # Don't analyze duration
    "-fflags", "nobuffer",       # Reduce buffering
    "-flags", "low_delay",       # Prioritize low latency
    "-f", "mp3",                 # Input format is MP3
    "-",                         # Read from stdin
    "-nodisp",                   # Disable video window
    "-autoexit",                 # Exit when stdin closes
    "-loglevel", "error",        # Suppress verbose output
]

# --- AAC Streaming Configuration ---
STREAM_ENABLED_DEFAULT = False  # Default for the --stream flag
STREAM_PORT = 8080              # Default HTTP port for AAC stream
STREAM_AAC_BITRATE = "96k"      # Target AAC bitrate
STREAM_PATH = "/stream.aac"     # HTTP path for the AAC stream
STREAM_CONTENT_TYPE = "audio/aac" # MIME type for the stream
FFMPEG_RECODE_CMD = [           # Command to recode MP3 stdin to AAC stdout
    "ffmpeg",
    "-hide_banner",              # Suppress version banner
    "-loglevel", "error",        # Show only errors
    "-probesize", "32",          # Keep low probesize for faster start
    "-analyzeduration", "0",     # Keep low analyze duration
    # --- Input Specification ---
    "-f", "mp3", "-i", "-",      # Input MP3 from stdin
    # --- Output Specification ---
    "-c:a", "aac",               # Output codec AAC
    "-b:a", STREAM_AAC_BITRATE,  # Output bitrate
    "-f", "adts",                # Output format ADTS (for streaming AAC)
    "-avioflags", "direct",      # Keep output direct flag (less likely to cause input issues)
    "-flush_packets", "1",       # Keep output flush flag
    "-"                          # Output to stdout
]

# --- UI Appearance Constants (GUI) ---
WINDOW_WIDTH = 700
WINDOW_HEIGHT = 550
PAD_X = 8
PAD_Y = 5
PS_WRAP_LENGTH = 280             # Max width for PS label before wrapping
PTY_AF_WRAP_LENGTH = 160         # Max width for PTY/AF before wrapping
INTERNAL_CONTENT_FRAME_PADDING_X = PAD_X * 2
FULL_WIDTH_WRAP_LENGTH = WINDOW_WIDTH - (PAD_X * 2) - INTERNAL_CONTENT_FRAME_PADDING_X - (PAD_X // 2)
RT_WRAP_LENGTH = FULL_WIDTH_WRAP_LENGTH # Max width for RadioText labels
TX_WRAP_LENGTH = FULL_WIDTH_WRAP_LENGTH # Max width for Transmitter info labels

# --- CLI Constants ---
CLEAR_LINE = "\033[K"             # ANSI: Clear line from cursor to end
SAVE_CURSOR = "\033[s"            # ANSI: Save cursor position
RESTORE_CURSOR = "\033[u"         # ANSI: Restore cursor position
SHOW_CURSOR = "\033[?25h"         # ANSI: Show cursor
HIDE_CURSOR = "\033[?25l"         # ANSI: Hide cursor
# Standard ANSI/VT sequences for arrow keys
KEY_UP_SEQ = ["\x1b[A", "\x1bOA"]
KEY_DOWN_SEQ = ["\x1b[B", "\x1bOB"]
KEY_RIGHT_SEQ = ["\x1b[C", "\x1bOC"]
KEY_LEFT_SEQ = ["\x1b[D", "\x1bOD"]
# Windows specific sequences from readchar (often prefixed with \x00 or \xe0)
WIN_KEY_UP = "\x00H"; WIN_KEY_UP_E0 = "\xe0H"
WIN_KEY_DOWN = "\x00P"; WIN_KEY_DOWN_E0 = "\xe0P"
WIN_KEY_LEFT = "\x00K"; WIN_KEY_LEFT_E0 = "\xe0K"
WIN_KEY_RIGHT = "\x00M"; WIN_KEY_RIGHT_E0 = "\xe0M"
# Add Windows codes to sequences for broader compatibility
KEY_UP_SEQ.extend([WIN_KEY_UP, WIN_KEY_UP_E0])
KEY_DOWN_SEQ.extend([WIN_KEY_DOWN, WIN_KEY_DOWN_E0])
KEY_LEFT_SEQ.extend([WIN_KEY_LEFT, WIN_KEY_LEFT_E0])
KEY_RIGHT_SEQ.extend([WIN_KEY_RIGHT, WIN_KEY_RIGHT_E0])
# Other common key codes
KEY_BACKSPACE = ["\x08", "\x7f"] # Backspace and Delete often map differently
KEY_ENTER = ["\r", "\n"]         # Carriage Return and Line Feed
KEY_ESC = "\x1b"                 # Escape key
KEY_CTRL_C = "\x03"              # Control-C character

# --- Standard RDS Program Type (PTY) Codes (ETSI EN 300 401) ---
PTY_CODES = {
    0: "No PTY / Undefined", 1: "News", 2: "Current Affairs", 3: "Information",
    4: "Sport", 5: "Education", 6: "Drama", 7: "Culture", 8: "Science",
    9: "Varied", 10: "Pop Music", 11: "Rock Music", 12: "Easy Listening",
    13: "Light Classical", 14: "Serious Classical", 15: "Other Music",
    16: "Weather", 17: "Finance", 18: "Children's", 19: "Social Affairs",
    20: "Religion", 21: "Phone-In", 22: "Travel", 23: "Leisure",
    24: "Jazz Music", 25: "Country Music", 26: "National Music",
    27: "Oldies Music", 28: "Folk Music", 29: "Documentary",
    30: "Alarm Test", 31: "Alarm",
}

# --- Global State ---
# Used for cross-thread communication and shutdown coordination
app_running = threading.Event() # Thread-safe flag to signal application shutdown
app_running.set()               # Start in the 'running' state
# Queues and controller reference are initialized in run_cli/run_gui
cli_command_queue = None        # Queue for sending commands (tune) to controller (CLI)
cli_update_queue = None         # Queue for receiving updates from controller (CLI)
cli_asyncio_controller = None   # Reference to the controller instance (CLI)
# CLI Display State Variables
cli_display_lines_printed = 0   # Number of lines used by the last data display
cli_current_freq_khz = 0        # Currently tuned frequency in kHz (CLI)
cli_last_data = {}              # Last received data dictionary (CLI)
cli_input_buffer = ""           # User input buffer for frequency (CLI)
cli_input_line_row = 15         # Estimated row for input line (CLI, adjusted dynamically)
cli_status_message = ""         # Status message line (CLI)

# --- DPI Awareness (Windows GUI) ---
if sys.platform == 'win32' and tkinter_available:
    try:
        # Attempt to set per-monitor DPI awareness v2 for crisp UI on scaled displays
        PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        # print("Info: Successfully set DPI awareness (Windows).")
    except AttributeError:
        # Fallback or older Windows: Process might be blurry on high-DPI screens
        # print("Warning: Failed to set DPI awareness (older Windows?). UI might be blurry.")
        pass # Continue execution
    except Exception as e:
        # print(f"Warning: Error setting DPI awareness: {e}")
        pass # Continue execution

# =============================================================================
# Helper Functions
# =============================================================================

def check_command(cmd_name, show_error_popup=False):
    """Checks if an external command exists in the system's PATH."""
    if shutil.which(cmd_name) is None:
        err_msg = f"Error: Required command '{cmd_name}' not found in PATH."
        print(err_msg)
        # Show popup only if requested AND tkinter is available and working
        if show_error_popup and tkinter_available:
            try:
                root = tk.Tk(); root.withdraw()
                messagebox.showerror("Dependency Error", err_msg)
                root.destroy()
            except tk.TclError:
                pass # Ignore if Tk fails here
        return False
    return True

def is_unexpected_exit(return_code):
    """Checks if a process exit code signifies an unexpected termination."""
    # None means process is still running, 0 is clean exit
    if return_code is None or return_code == 0:
        return False
    # Check against common graceful termination signals (negative values on Unix)
    graceful_signals = [-signal.SIGTERM.value] # Typically -15
    if sys.platform != "win32":
        # SIGKILL is generally not considered graceful but is an expected way to stop
        graceful_signals.append(-signal.SIGKILL.value) # Typically -9
    # Any other non-zero code is considered potentially unexpected
    return return_code not in graceful_signals

def check_ffplay(show_error_popup=False):
    """Convenience function to check for ffplay."""
    return check_command("ffplay", show_error_popup)

def check_ffmpeg(show_error_popup=False):
    """Convenience function to check for ffmpeg."""
    return check_command("ffmpeg", show_error_popup)

def mhz_to_khz(mhz_str):
    """Converts frequency string (MHz) to integer (kHz), validating range."""
    if not isinstance(mhz_str, str):
        return None
    try:
        # Allow comma or dot as decimal separator
        mhz = float(mhz_str.replace(",", "."))
        # Validate frequency is within FM band
        if MIN_FREQ_MHZ <= mhz <= MAX_FREQ_MHZ:
            return int(mhz * 1000)
        else:
            return None
    except (ValueError, TypeError):
        return None

def khz_to_mhz_str(khz_int):
    """Converts frequency integer (kHz) to string (MHz, 3 decimal places)."""
    if not isinstance(khz_int, int) or khz_int <= 0:
        return "N/A" # Not Available / Not Tuned
    return f"{khz_int / 1000:.3f}"

# =============================================================================
# AsyncioController Class
# =============================================================================
# Handles all backend asynchronous tasks: WebSocket connections,
# data processing, external process management (ffplay, ffmpeg),
# and communication with the UI (via queues). Runs in a separate thread.
# =============================================================================

class AsyncioController:
    def __init__(self, audio_uri, text_uri, command_queue, update_queue,
                 stream_enabled=False, is_restream_only=False, stream_port=STREAM_PORT):
        """
        Initializes the controller.

        Args:
            audio_uri (str): WebSocket URI for the audio stream.
            text_uri (str): WebSocket URI for the text/JSON stream.
            command_queue (queue.Queue): Queue to receive commands from the UI (e.g., tune).
            update_queue (queue.Queue): Queue to send updates to the UI (data, status, errors).
            stream_enabled (bool): Whether AAC streaming should be enabled.
            is_restream_only (bool): Whether to run in restream-only mode (no ffplay).
            stream_port (int): Port for the AAC streaming HTTP server.
        """
        self.audio_uri = audio_uri
        self.text_uri = text_uri
        self.command_queue = command_queue
        self.update_queue = update_queue
        self.stream_enabled = stream_enabled and aiohttp_available # Can only stream if lib available
        self.is_restream_only = is_restream_only
        self.stream_port = stream_port

        self.loop = None        # The asyncio event loop for this controller
        self.thread = None      # The thread running the event loop
        self.app_running_event = app_running # Use the global shutdown event
        self._text_ws_for_commands = None # Holds ref to text WS for sending tune commands

        # External process references
        self.ffplay_proc = None
        self.ffmpeg_proc = None

        # Streaming-related attributes
        self.http_runner = None      # aiohttp application runner
        self.http_site = None        # aiohttp TCP site
        self.aac_clients = set()     # Set of client queues for AAC stream
        self.aac_relay_task = None   # Task for relaying AAC data
        self.stream_server_task = None # Task for running the HTTP server

        # For logging changes in client counts
        self.last_text_user_count = 0
        self.last_aac_client_count = 0

        # Initial status logging based on mode
        # if self.is_restream_only:
        #     print("AsyncioController: Initialized in Restream-Only mode.")
        # if self.is_restream_only and not self.stream_enabled:
        #     print("AsyncioController: Warning - Restream-Only mode active, but streaming (-s) is disabled or aiohttp missing. No audio output.")
        # elif self.stream_enabled:
        #     print(f"AsyncioController: Streaming configured for port {self.stream_port}.")

    def start(self):
        """Starts the asyncio event loop in a new background thread."""
        if self.thread is None or not self.thread.is_alive():
            self.app_running_event.set() # Ensure flag is set before starting
            self.thread = threading.Thread(target=self._run_asyncio_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Signals the controller and its tasks to shut down gracefully."""
        if self.app_running_event.is_set():
            self.app_running_event.clear() # Signal shutdown to all tasks/loops

            # Wake up command queue listener if it's blocking
            if self.command_queue:
                try: self.command_queue.put_nowait(None)
                except queue.Full: pass

            # Request the asyncio loop to stop from the controlling thread
            if self.loop and self.loop.is_running():
                # print("AsyncioController: Requesting event loop stop...")
                self.loop.call_soon_threadsafe(self.loop.stop)

            # Wait for the thread (and implicitly the loop/cleanup) to finish
            if self.thread and self.thread.is_alive():
                # print("AsyncioController: Waiting for controller thread to join...")
                self.thread.join(timeout=7.0) # Reasonable timeout

                # if self.thread.is_alive():
                #     print("Warning: AsyncioController thread did not exit cleanly after stop request.")

        # Ensure external processes are terminated *after* attempting thread join
        # This acts as a final cleanup guarantee.
        # print("AsyncioController stop: Final termination of external processes...")
        self._kill_ffplay()
        self._kill_ffmpeg()
        # print("AsyncioController stop: Processes termination initiated.")
        self.thread = None # Clear thread reference after it has joined/timed out

    def is_running(self):
        """Checks if the controller thread is alive and shutdown hasn't been signaled."""
        return self.app_running_event.is_set() and self.thread and self.thread.is_alive()

    def _run_asyncio_loop(self):
        """The target method for the controller's thread. Sets up and runs the event loop."""
        # print("AsyncioController: Thread started.")
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            main_task = self.loop.create_task(self._main_async(), name="MainAsync")
            # print("AsyncioController: Starting event loop.")
            self.loop.run_forever() # Runs until loop.stop() is called externally
            # print("AsyncioController: Event loop stopped normally.")
        except Exception as e:
            # Catch unexpected errors during loop setup or execution
            self.put_update("error", f"Asyncio loop crashed: {e}")
            traceback.print_exc()
            self.app_running_event.clear() # Ensure shutdown on crash
        finally:
            # print("AsyncioController: Starting final loop cleanup sequence...")
            if self.loop:
                try:
                    # Ensure loop is stopped if it wasn't already
                    if self.loop.is_running():
                        # print("AsyncioController: Forcing loop stop during cleanup.")
                        self.loop.stop()

                    # Gather and cancel all pending tasks
                    all_tasks = asyncio.all_tasks(self.loop)
                    pending_tasks = {task for task in all_tasks if not task.done()}
                    if pending_tasks:
                        # print(f"AsyncioController: Cancelling {len(pending_tasks)} outstanding tasks...")
                        for task in pending_tasks:
                            task.cancel()

                    # Prepare cleanup coroutines (cancelled tasks + specific cleanup)
                    cleanup_coroutines = list(pending_tasks)
                    if self.http_runner:
                        # print("AsyncioController: Adding HTTP runner cleanup...")
                        cleanup_coroutines.append(self.http_runner.cleanup())
                    if hasattr(self.loop, "shutdown_asyncgens"):
                        # print("AsyncioController: Adding async gen shutdown...")
                        cleanup_coroutines.append(self.loop.shutdown_asyncgens())

                    # Run cleanup tasks until completion
                    if cleanup_coroutines:
                        # print("AsyncioController: Waiting for final cleanup tasks/coroutines...")
                        self.loop.run_until_complete(asyncio.gather(*cleanup_coroutines, return_exceptions=True))
                        # print("AsyncioController: Final cleanup tasks/coroutines complete.")

                except RuntimeError as e_runtime:
                     # Ignore common error when scheduling during shutdown
                     if "cannot schedule new futures after shutdown" not in str(e_runtime):
                          print(f"RuntimeError during loop cleanup gather/run: {e_runtime}")
                except Exception as e_shutdown:
                    print(f"Error during final asyncio cleanup processing: {e_shutdown}")
                    traceback.print_exc()
                finally:
                    # Close the loop itself
                    if self.loop and not self.loop.is_closed():
                        # print("AsyncioController: Closing event loop.")
                        self.loop.close()
                    self.loop = None
                    # print("AsyncioController: Event loop closed.")

            # Final kill of external processes *after* loop cleanup
            # print("AsyncioController: Final termination of external processes post-loop...")
            self._kill_ffplay()
            self._kill_ffmpeg()

            # Signal that the controller is fully stopped and cleaned up
            self.put_update("closed", None)
            # print("AsyncioController: Loop thread finished.")

    async def _main_async(self):
        """The main async function that creates and manages the core tasks."""
        # print("AsyncioController: _main_async started.")
        tasks = {
            asyncio.create_task(self._handle_gui_commands(), name="CmdListen"),
            asyncio.create_task(self._handle_text_websocket(), name="TxtWS"),
            asyncio.create_task(self._play_audio_stream(), name="AudWS")
        }

        # Conditionally add streaming tasks if enabled and possible
        if self.stream_enabled:
            # print("AsyncioController: Enabling streaming tasks.")
            self.aac_relay_task = asyncio.create_task(self._relay_aac_data(), name="AACRelay")
            tasks.add(self.aac_relay_task)
            self.stream_server_task = asyncio.create_task(self._run_streaming_server(), name="StreamSrv")
            tasks.add(self.stream_server_task)
        elif args.stream and not aiohttp_available: # Check args directly for user intent
             # print("AsyncioController: Streaming requested but aiohttp not found. Disabling.")
             self.put_update("stream_status", "Stream: Disabled (aiohttp missing)")
             self.put_update("error", "Feature Error: aiohttp required for streaming.")

        # Main monitoring loop: waits for tasks to complete or shutdown signal
        while self.app_running_event.is_set():
            # Wait for any task to finish or a short timeout
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED, timeout=0.5
            )

            # Check for shutdown signal after waiting
            if not self.app_running_event.is_set():
                # print("AsyncioController: Shutdown detected in _main_async loop.")
                break

            # If timeout occurred, loop back to check running state
            if not done:
                continue

            # Process completed tasks
            for task in done:
                tasks.remove(task)
                task_name = task.get_name()
                if task.cancelled():
                    # Task cancellation is expected during shutdown
                    # print(f"AsyncioController: Task {task_name} was cancelled.")
                    continue

                try:
                    exc = task.exception() # Check if task exited with an exception
                    if exc:
                        is_fatal = False # Assume non-fatal unless specified

                        # --- Handle Specific Non-Fatal/Recoverable Errors ---
                        if task_name == "StreamSrv" and isinstance(exc, OSError) and "Address already in use" in str(exc):
                             port_in_use = self.stream_port
                             err_msg = f"Stream Err: Port {port_in_use} in use"
                             self.put_update("stream_status", err_msg)
                             self.put_update("error", f"Fatal: Port {port_in_use} already in use. Streaming disabled.")
                             print(f"ERROR: Port {port_in_use} for streaming server is already in use. Disabling streaming.")
                             self.stream_enabled = False # Disable streaming for this run
                             # Cancel related tasks if they exist and are pending
                             if self.aac_relay_task in pending: tasks.discard(self.aac_relay_task); self.aac_relay_task.cancel()
                             continue # Don't restart server, just handle error

                        # --- Identify Potentially Fatal Errors ---
                        if isinstance(exc, websockets.exceptions.InvalidURI) and task_name != "StreamSrv":
                            is_fatal = True # Invalid WS URI is fatal

                        # FileNotFoundError for dependencies is fatal under certain conditions
                        if isinstance(exc, FileNotFoundError):
                            if task_name == "AudWS" and 'ffplay' in str(exc) and not self.is_restream_only:
                                is_fatal = True # ffplay needed if not restream-only
                            elif task_name == "AudWS" and 'ffmpeg' in str(exc) and self.stream_enabled:
                                is_fatal = True # ffmpeg needed if streaming enabled

                        # Log the error regardless of fatality
                        self.put_update("error", f"Task {task_name} failed: {type(exc).__name__}: {exc}")
                        print(f"--- Error in Task: {task_name} ---")
                        traceback.print_exception(type(exc), exc, exc.__traceback__)
                        print(f"--- End Error Traceback ({task_name}) ---")

                        # --- Handle Fatal Errors ---
                        if is_fatal:
                            self.put_update("error", f"Fatal error in {task_name}. Stopping.")
                            print(f"FATAL ERROR in task {task_name}. Stopping application.")
                            self.app_running_event.clear() # Signal shutdown
                            break # Exit the outer while loop immediately

                        # --- Restart Logic for Non-Fatal Errors ---
                        if self.app_running_event.is_set(): # Only restart if not shutting down
                            print(f"AsyncioController: Restarting task {task_name} after error...")
                            if task_name == "TxtWS":
                                tasks.add(asyncio.create_task(self._handle_text_websocket(), name="TxtWS"))
                            elif task_name == "AudWS":
                                tasks.add(asyncio.create_task(self._play_audio_stream(), name="AudWS"))
                            elif task_name == "AACRelay" and self.stream_enabled:
                                # Only restart relay if streaming is still supposed to be enabled
                                tasks.add(asyncio.create_task(self._relay_aac_data(), name="AACRelay"))
                            elif task_name == "StreamSrv":
                                # Generally don't restart the server automatically on failure
                                print(f"Warning: Stream server task ({task_name}) failed unexpectedly. Streaming disabled.")
                                self.stream_enabled = False # Assume server failure disables streaming
                                self.put_update("stream_status", "Stream: Server Failed")

                except asyncio.CancelledError:
                     # Expected during shutdown
                     pass
                except Exception as e_check:
                     # Error during exception checking itself (should be rare)
                     self.put_update("error", f"Internal Error checking task {task_name}: {e_check}")
                     print(f"CRITICAL: Error while checking exception for task {task_name}: {e_check}")

            # Check shutdown flag again after processing completed tasks
            if not self.app_running_event.is_set(): break

        # --- Shutdown Cleanup within _main_async ---
        # print("AsyncioController: _main_async loop ending. Cancelling remaining tasks...")
        remaining_tasks = list(tasks) # Get tasks still in the set
        for task in remaining_tasks:
            if not task.done():
                task.cancel()
        # Wait for cancellations to be processed before exiting _main_async
        if remaining_tasks:
            await asyncio.gather(*remaining_tasks, return_exceptions=True)
        # print("AsyncioController: _main_async finished.")

    def put_update(self, message_type, data):
        """Safely puts an update message onto the queue for the UI."""
        if self.update_queue:
             try:
                 # Use put_nowait to avoid blocking the controller thread
                 self.update_queue.put_nowait((message_type, data))
             except queue.Full:
                 # This indicates the UI thread is not processing messages fast enough
                 print(f"Warning: Update queue full. Dropping update: {message_type}")

    def _kill_process(self, proc, name="process"):
        """Attempts to terminate and then kill an asyncio subprocess."""
        if proc and proc.returncode is None: # Check if process exists and is running
            pid = proc.pid
            # print(f"AsyncioController: Attempting to terminate {name} (PID: {pid})...")
            try:
                # Close stdin first (can sometimes help process exit)
                if proc.stdin and hasattr(proc.stdin, 'is_closing') and not proc.stdin.is_closing():
                    try:
                        proc.stdin.close()
                    except Exception:
                        # Ignore errors closing stdin during shutdown
                        pass

                # Send SIGTERM first for graceful shutdown
                proc.terminate()
                # print(f"AsyncioController: Sent SIGTERM to {name} (PID: {pid}).")

                # Note: We don't explicitly wait here in the sync cleanup.
                # If terminate fails, kill will be attempted if necessary by caller or OS.
                # The main async loop relies on returncode checks. Stop() function ensures final kill.

            except ProcessLookupError:
                # Process already finished between check and signal attempt
                # print(f"AsyncioController: {name} (PID: {pid}) already exited.")
                pass
            except Exception as e_term:
                print(f"AsyncioController: Error during termination attempt for {name} (PID: {pid}): {e_term}")
                # Attempt SIGKILL as fallback if terminate fails and process still running
                try:
                    if proc.returncode is None:
                        proc.kill()
                        # print(f"AsyncioController: Sent SIGKILL to {name} (PID: {pid}).")
                except ProcessLookupError:
                    pass # Already gone
                except Exception as e_kill:
                    print(f"AsyncioController: Error during final kill attempt for {name} (PID: {pid}): {e_kill}")

        return None # Return None so caller can clear their process variable

    def _kill_ffplay(self):
        """Safely terminates the ffplay process if it's running."""
        if hasattr(self, 'ffplay_proc'): # Ensure attribute exists
            self.ffplay_proc = self._kill_process(self.ffplay_proc, "ffplay")

    def _kill_ffmpeg(self):
        """Safely terminates the ffmpeg process if it's running."""
        if hasattr(self, 'ffmpeg_proc'): # Ensure attribute exists
            self.ffmpeg_proc = self._kill_process(self.ffmpeg_proc, "ffmpeg")

    async def _handle_gui_commands(self):
        """Task to listen for commands from the UI queue and send them via WebSocket."""
        # print("AsyncioController: Command listener task started.")
        while self.app_running_event.is_set():
            try:
                # Use asyncio.to_thread for the blocking queue get
                # Use a timeout to periodically check the app_running_event
                command = await asyncio.to_thread(self.command_queue.get, block=True, timeout=0.5)

                if command is None: # Check for shutdown signal (None)
                    if not self.app_running_event.is_set():
                        break # Exit loop if shutdown is signaled
                    else:
                        continue # Ignore None if not shutting down

                # Process valid commands (currently only tune commands 'T<freq_khz>')
                ws = self._text_ws_for_commands
                # Check if the WebSocket is still open and valid
                if ws and ws.close_code is None:    
                    if isinstance(command, str) and command.startswith("T"):
                        try:
                            await ws.send(command)
                            # Optimistically update frequency status via update queue
                            try:
                                target_freq_khz = int(command[1:])
                                self.put_update("current_freq", target_freq_khz)
                            except ValueError:
                                pass # Ignore if frequency part is invalid
                        except websockets.exceptions.ConnectionClosed:
                            self.put_update("status", "Text WS closed, cannot send cmd.")
                            self._text_ws_for_commands = None # Invalidate WS reference
                        except Exception as e:
                            self.put_update("error", f"Send command failed: {e}")
                    # else: ignore non-tune commands silently
                elif command.startswith("T"): # Only report error if it was a tune command
                    self.put_update("status", "Text WS not connected, cannot tune.")

                # Mark task as done only if it wasn't the shutdown signal
                if command is not None:
                    self.command_queue.task_done()

            except queue.Empty:
                # Timeout occurred, loop continues to check app_running_event
                await asyncio.sleep(0.01) # Small sleep to yield control
            except asyncio.CancelledError:
                # print("AsyncioController: Command listener task cancelled.")
                break
            except Exception as e:
                self.put_update("error", f"Cmd handling error: {e}")
                print(f"AsyncioController: Unexpected error in command listener: {e}")
                traceback.print_exc()
                await asyncio.sleep(1) # Avoid tight loop on persistent error
        # print("AsyncioController: Command listener task finished.")

    async def _handle_text_websocket(self):
        """Task to manage the text/JSON WebSocket connection and receive data."""
        # print("AsyncioController: Text WS handler task started.")
        last_connect_time = 0
        websocket = None
        self._text_ws_for_commands = None # Ensure reset at start

        while self.app_running_event.is_set():
            websocket = None # Reset on each connection attempt
            self._text_ws_for_commands = None
            retry_delay = RECONNECT_DELAY_SECONDS

            try:
                # --- Reconnection Delay ---
                now = time.monotonic()
                time_since_last = now - last_connect_time
                if time_since_last < retry_delay:
                    await asyncio.sleep(retry_delay - time_since_last)
                if not self.app_running_event.is_set(): break # Check flag after sleep

                # --- Attempt Connection ---
                last_connect_time = time.monotonic()
                self.put_update("status", f"Connecting Text WS...")
                # print(f"AsyncioController: Connecting Text WS: {self.text_uri}")
                connect_options = {
                    "open_timeout": TEXT_WEBSOCKET_TIMEOUT,
                    "ping_interval": 20, # Send pings to keep connection alive
                    "ping_timeout": 10   # Wait for pong replies
                }
                websocket = await websockets.connect(self.text_uri, **connect_options)

                self._text_ws_for_commands = websocket # Make available for sending commands
                self.put_update("status", "Text WS connected.")
                # print("AsyncioController: Text WS connected.")

                # --- Receive Loop ---
                async for message in websocket:
                    if not self.app_running_event.is_set(): break # Check before processing
                    try:
                        data = json.loads(message)
                        # Send data to UI
                        self.put_update("data", data)
                        # Immediately update frequency if present in data
                        # Note: This might be slightly redundant if server also confirms via tune command response
                        data_freq_khz = mhz_to_khz(data.get("freq"))
                        if data_freq_khz is not None:
                            self.put_update("current_freq", data_freq_khz)
                    except json.JSONDecodeError:
                        self.put_update("error", "Invalid JSON received (Text WS).")
                    except Exception as e_proc:
                        self.put_update("error", f"Processing text data failed: {e_proc}")

                # If the loop exits "normally" (server closed connection), check why
                if self.app_running_event.is_set():
                    # This path is usually taken if the server closes the connection gracefully.
                    # The 'except ConnectionClosed' block below handles unexpected closures better.
                    pass

            except asyncio.CancelledError:
                # print("AsyncioController: Text WS handler task cancelled.")
                break # Exit loop immediately
            except websockets.exceptions.ConnectionClosed as e_cls:
                close_reason = f"Code: {e_cls.code}, Reason: {e_cls.reason}" if e_cls.code else "Closed unexpectedly"
                self.put_update("status", f"Text WS closed ({close_reason})")
            except websockets.exceptions.InvalidURI:
                # This is a fatal configuration error
                self.put_update("error", f"Fatal: Invalid Text URI: {self.text_uri}")
                print(f"FATAL ERROR: Invalid Text WebSocket URI: {self.text_uri}")
                self.app_running_event.clear(); break # Stop the application
            except ConnectionRefusedError:
                self.put_update("status", "Text WS connection refused.")
            except asyncio.TimeoutError:
                self.put_update("status", "Text WS connection timeout.")
            except OSError as e:
                # Catch potential network errors (e.g., Network unreachable)
                self.put_update("error", f"Text WS OS Error: {e}")
            except Exception as e:
                # Catch any other unexpected errors during connection or receive
                self.put_update("error", f"Text WS Error: {e}")
                print(f"AsyncioController: Unexpected Text WS Error: {e}")
                traceback.print_exc()
            finally:
                # Cleanup after connection attempt (success or failure)
                self._text_ws_for_commands = None # Clear command ws reference
                if websocket and not websocket.closed:
                    await websocket.close()
                # Add a short delay before the main retry logic kicks in
                if self.app_running_event.is_set():
                    self.put_update("status", "Text WS disconnected. Retrying...")
                    await asyncio.sleep(0.5)

        # --- Final Cleanup on Task Exit ---
        self._text_ws_for_commands = None
        if websocket and not websocket.closed: await websocket.close()
        # print("AsyncioController: Text WS handler task finished.")

    async def _play_audio_stream(self):
        """Task to manage the audio WebSocket, pipe to ffplay (optional), and ffmpeg (optional)."""
        # print("AsyncioController: Audio stream handler task started.")
        # if self.is_restream_only:
        #     print("AsyncioController: Running in Restream-Only mode (no ffplay).")

        last_connect_time = 0
        websocket = None
        # Request MP3 format from server upon connection
        fallback_request = json.dumps({"type": "fallback", "data": "mp3"})
        # Tasks for reading stderr from external processes
        ffplay_stderr_task = None
        ffmpeg_stderr_task = None

        while self.app_running_event.is_set():
            # --- Cleanup Processes from Previous Attempt ---
            # Ensure external processes from the previous loop iteration are stopped
            if not self.is_restream_only: self._kill_ffplay()
            if self.stream_enabled: self._kill_ffmpeg() # Kill ffmpeg if it was running

            # Cancel any lingering stderr reader tasks from previous run
            tasks_to_cancel = []
            if ffplay_stderr_task and not ffplay_stderr_task.done(): tasks_to_cancel.append(ffplay_stderr_task)
            if ffmpeg_stderr_task and not ffmpeg_stderr_task.done(): tasks_to_cancel.append(ffmpeg_stderr_task)
            if tasks_to_cancel:
                 for task in tasks_to_cancel: task.cancel()
                 await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            ffplay_stderr_task = None; ffmpeg_stderr_task = None

            websocket = None
            retry_delay = RECONNECT_DELAY_SECONDS

            try:
                # --- Reconnection Delay ---
                now = time.monotonic()
                time_since_last = now - last_connect_time
                if time_since_last < retry_delay:
                    await asyncio.sleep(retry_delay - time_since_last)
                if not self.app_running_event.is_set(): break

                # --- Attempt Connection ---
                last_connect_time = time.monotonic()
                self.put_update("status", f"Connecting Audio WS...")
                # print(f"AsyncioController: Connecting Audio WS: {self.audio_uri}")
                connect_options = {
                    "open_timeout": AUDIO_WEBSOCKET_TIMEOUT,
                    "ping_interval": None # Rely on recv timeout and manual pings if needed
                }
                websocket = await websockets.connect(self.audio_uri, **connect_options)

                self.put_update("status", "Audio WS connected.")
                # print("AsyncioController: Audio WS connected.")
                # Request MP3 format
                await websocket.send(fallback_request)
                # print("AsyncioController: Sent audio format request (MP3).")

                # --- Start ffplay (Conditionally) ---
                self.ffplay_proc = None # Reset process handle
                if not self.is_restream_only:
                    self.put_update("status", "Starting audio player (ffplay)...")
                    try:
                        self._kill_ffplay() # Ensure no previous instance is lingering
                        # Start ffplay process
                        self.ffplay_proc = await asyncio.create_subprocess_exec(
                            *FFPLAY_CMD,
                            stdin=asyncio.subprocess.PIPE,    # Pipe audio data in
                            stdout=asyncio.subprocess.DEVNULL,# Ignore stdout
                            stderr=asyncio.subprocess.PIPE    # Capture stderr for errors
                        )
                        # Start task to monitor ffplay's stderr
                        ffplay_stderr_task = asyncio.create_task(
                            self._read_process_stderr(self.ffplay_proc, "ffplay"),
                            name="ffplay_stderr"
                        )
                        # print(f"AsyncioController: Started ffplay (PID: {self.ffplay_proc.pid}).")
                    except FileNotFoundError:
                        # ffplay is essential if not in restream-only mode
                        self.put_update("error", "Fatal: 'ffplay' command not found. Playback disabled.")
                        print("FATAL ERROR: 'ffplay' command not found. Cannot play audio.")
                        self.app_running_event.clear(); return # Stop the application
                    except Exception as e_popen:
                        # Other errors starting ffplay
                        self.put_update("error", f"Failed to start ffplay: {e_popen}")
                        print(f"ERROR: Failed to start ffplay: {e_popen}")
                        await asyncio.sleep(retry_delay); continue # Retry connection loop

                # else: ffplay not started in restream-only mode

                # --- Start ffmpeg (if streaming enabled) ---
                self.ffmpeg_proc = None # Reset process handle
                if self.stream_enabled:
                    self.put_update("status", "Starting AAC encoder (ffmpeg)...")
                    try:
                        self._kill_ffmpeg() # Ensure no previous instance lingers
                        # Start ffmpeg process for transcoding
                        self.ffmpeg_proc = await asyncio.create_subprocess_exec(
                            *FFMPEG_RECODE_CMD,
                            stdin=asyncio.subprocess.PIPE,     # Pipe MP3 data in
                            stdout=asyncio.subprocess.PIPE,    # Read AAC data out
                            stderr=asyncio.subprocess.PIPE     # Capture stderr
                        )
                        # Start task to monitor ffmpeg's stderr
                        ffmpeg_stderr_task = asyncio.create_task(
                            self._read_process_stderr(self.ffmpeg_proc, "ffmpeg"),
                            name="ffmpeg_stderr"
                        )
                        # print(f"AsyncioController: Started ffmpeg for streaming (PID: {self.ffmpeg_proc.pid}).")
                    except FileNotFoundError:
                        # ffmpeg is essential for streaming
                        self.put_update("error", "'ffmpeg' not found. Cannot stream.")
                        print("ERROR: 'ffmpeg' not found. Disabling streaming for this session.")
                        self.stream_enabled = False # Disable streaming if ffmpeg missing
                        # No need to stop app, just disable feature
                    except Exception as e_popen:
                        # Other errors starting ffmpeg
                        self.put_update("error", f"Failed to start ffmpeg: {e_popen}. Streaming disabled.")
                        print(f"ERROR: Failed to start ffmpeg: {e_popen}. Disabling streaming.")
                        self.stream_enabled = False # Disable streaming on error

                # --- Main Receive and Pipe Loop ---
                while self.app_running_event.is_set():
                    # --- Check External Process Status First ---
                    ffplay_rc = None
                    if not self.is_restream_only and self.ffplay_proc:
                        ffplay_rc = self.ffplay_proc.returncode

                    ffmpeg_rc = None
                    if self.stream_enabled and self.ffmpeg_proc:
                        ffmpeg_rc = self.ffmpeg_proc.returncode

                    # Handle ffplay exit (only if it was supposed to be running)
                    if ffplay_rc is not None:
                        if is_unexpected_exit(ffplay_rc):
                            self.put_update("error", f"ffplay exited unexpectedly (code {ffplay_rc}).")
                        else:
                            self.put_update("status", "ffplay stopped.")
                        self.ffplay_proc = None # Mark as stopped
                        # Break inner loop to trigger reconnection of audio stream (and restart ffplay)
                        break

                    # Handle ffmpeg exit (only if it was supposed to be running)
                    if ffmpeg_rc is not None:
                        if is_unexpected_exit(ffmpeg_rc):
                            self.put_update("error", f"ffmpeg exited unexpectedly (code {ffmpeg_rc}). Streaming stopped.")
                            print(f"ERROR: ffmpeg exited unexpectedly (code {ffmpeg_rc}). Disabling streaming.")
                        else:
                            self.put_update("stream_status", "Stream: Encoder stopped.")
                        # If ffmpeg dies, disable streaming for this session
                        self.stream_enabled = False
                        self.ffmpeg_proc = None # Mark as stopped
                        self._kill_ffmpeg() # Ensure cleanup
                        # Continue receiving audio, just don't pipe to ffmpeg anymore

                    # --- Receive Audio Data from WebSocket ---
                    try:
                        # Wait for a message with a timeout
                        msg = await asyncio.wait_for(websocket.recv(), timeout=AUDIO_WEBSOCKET_TIMEOUT)

                        if isinstance(msg, bytes) and msg:
                            # --- Pipe to ffplay (if running) ---
                            if not self.is_restream_only and self.ffplay_proc and self.ffplay_proc.stdin and not self.ffplay_proc.stdin.is_closing():
                                try:
                                    self.ffplay_proc.stdin.write(msg)
                                    await self.ffplay_proc.stdin.drain()
                                except (BrokenPipeError, ConnectionResetError, OSError):
                                    # Pipe broken, ffplay likely exiting. Let the exit check handle it.
                                    await asyncio.sleep(0.1) # Small yield
                                    continue # Let returncode check catch the exit

                            # --- Pipe to ffmpeg (if running) ---
                            if self.stream_enabled and self.ffmpeg_proc and self.ffmpeg_proc.stdin and not self.ffmpeg_proc.stdin.is_closing():
                                try:
                                    self.ffmpeg_proc.stdin.write(msg)
                                    await self.ffmpeg_proc.stdin.drain()
                                except (BrokenPipeError, ConnectionResetError, OSError) as e_pipe:
                                    # Pipe broken, ffmpeg likely exiting. Disable streaming.
                                    self.put_update("error", f"ffmpeg stdin pipe broken ({e_pipe}). Stopping stream.")
                                    self.stream_enabled = False
                                    self._kill_ffmpeg()
                                    self.ffmpeg_proc = None
                                    # Continue receiving audio, just stop streaming

                    except asyncio.TimeoutError:
                        # No data received, possibly connection issue. Try pinging.
                        self.put_update("status", "Audio WS recv timeout, pinging...")
                        try:
                            await asyncio.wait_for(websocket.ping(), timeout=5)
                            # Ping successful, continue receiving
                        except asyncio.TimeoutError:
                            self.put_update("status", "Audio WS ping timeout.")
                            break # Break inner loop to reconnect
                        except websockets.exceptions.ConnectionClosed:
                            self.put_update("status", "Audio WS closed during ping.")
                            break # Break inner loop to reconnect
                        except asyncio.CancelledError: raise # Propagate cancellation
                        except Exception as e_ping:
                            self.put_update("error", f"Audio WS ping error: {e_ping}")
                            break # Break inner loop to reconnect
                    except websockets.exceptions.ConnectionClosed as e_cls:
                        close_reason = f"Code: {e_cls.code}" if e_cls.code else "Closed unexpectedly"
                        self.put_update("status", f"Audio WS closed ({close_reason})")
                        break # Break inner loop to reconnect
                    except asyncio.CancelledError:
                        raise # Propagate cancellation immediately
                    except Exception as e_recv:
                        self.put_update("error", f"Audio WS Recv Error: {e_recv}")
                        traceback.print_exc()
                        break # Break inner loop to reconnect

            # --- Handle Connection Errors (Outer Loop Level) ---
            except asyncio.CancelledError:
                # print("AsyncioController: Audio stream handler task cancelled.")
                break # Exit main while loop
            except websockets.exceptions.InvalidURI:
                # Fatal configuration error
                self.put_update("error", f"Fatal: Invalid Audio URI: {self.audio_uri}")
                print(f"FATAL ERROR: Invalid Audio WebSocket URI: {self.audio_uri}")
                self.app_running_event.clear(); break # Stop the application
            except ConnectionRefusedError:
                self.put_update("status", "Audio WS connection refused.")
            except asyncio.TimeoutError:
                self.put_update("status", "Audio WS connection timeout.")
            except OSError as e:
                # Catch OS-level errors during connect (e.g., network unreachable)
                self.put_update("error", f"Audio WS OS Error (connect): {e}")
            except Exception as e:
                # Catch any other unexpected errors during connection setup
                self.put_update("error", f"Audio WS Setup Error: {e}")
                print(f"AsyncioController: Unexpected Audio WS Setup Error: {e}")
                traceback.print_exc()
            finally:
                # --- Cleanup after each connection attempt (success or failure) ---
                # Ensure processes started in this attempt are killed
                if not self.is_restream_only: self._kill_ffplay()
                if self.stream_enabled: self._kill_ffmpeg() # Use self.stream_enabled state

                # Cancel and await stderr tasks associated with this attempt
                tasks_to_await = []
                if ffplay_stderr_task and not ffplay_stderr_task.done():
                    ffplay_stderr_task.cancel(); tasks_to_await.append(ffplay_stderr_task)
                if ffmpeg_stderr_task and not ffmpeg_stderr_task.done():
                    ffmpeg_stderr_task.cancel(); tasks_to_await.append(ffmpeg_stderr_task)
                if tasks_to_await: await asyncio.gather(*tasks_to_await, return_exceptions=True)
                ffplay_stderr_task = None; ffmpeg_stderr_task = None

                # Close the WebSocket connection if it's open
                if websocket and not websocket.closed:
                    await websocket.close()

                # Add a short delay before the main retry logic checks RECONNECT_DELAY_SECONDS
                if self.app_running_event.is_set():
                    self.put_update("status", "Audio stream disconnected. Retrying...")
                    await asyncio.sleep(0.5)

        # --- Final Cleanup when the Task Exits ---
        # print("AsyncioController: Final audio stream cleanup...")
        if not self.is_restream_only: self._kill_ffplay()
        self._kill_ffmpeg() # Always attempt ffmpeg kill on exit, just in case
        # Cancel any final lingering stderr tasks
        tasks_to_cancel = []
        if ffplay_stderr_task and not ffplay_stderr_task.done(): tasks_to_cancel.append(ffplay_stderr_task)
        if ffmpeg_stderr_task and not ffmpeg_stderr_task.done(): tasks_to_cancel.append(ffmpeg_stderr_task)
        if tasks_to_cancel:
             for task in tasks_to_cancel: task.cancel()
             await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        # Final close of websocket if needed
        if websocket and not websocket.closed: await websocket.close()
        # print("AsyncioController: Audio stream handler task finished.")

    async def _read_process_stderr(self, proc, name):
        """Task to read and print stderr lines from a subprocess (ffplay/ffmpeg)."""
        if not proc or not proc.stderr:
            # print(f"AsyncioController: No stderr stream for process '{name}'.")
            return
        # print(f"AsyncioController: Starting stderr reader for {name} (PID: {proc.pid}).")
        try:
            while self.app_running_event.is_set():
                try:
                    # Read line by line
                    line_bytes = await proc.stderr.readline()
                    if not line_bytes:
                        # EOF reached, process likely exited
                        # print(f"AsyncioController: EOF reached for {name} stderr.")
                        break
                    line = line_bytes.decode('utf-8', errors='replace').strip()

                    # Optionally filter or log specific lines
                    # Avoid spamming console with common, non-critical messages
                    if line and "header missing" not in line.lower() and "invalid data" not in line.lower():
                        # Log lines containing error/warning, or potentially all ffmpeg lines
                        if "error" in line.lower() or "warning" in line.lower() or name == "ffmpeg":
                             print(f"{name} stderr: {line}")
                             # Could potentially put critical errors onto update queue here
                             # if "critical" in line.lower() or "fatal" in line.lower():
                             #    self.put_update("error", f"{name}: {line}")

                except asyncio.CancelledError:
                    raise # Propagate cancellation
                except Exception as e_read:
                    # Handle errors during reading (e.g., stream closed unexpectedly)
                    # print(f"AsyncioController: Error reading {name} stderr: {e_read}")
                    break # Exit loop on read error

        except asyncio.CancelledError:
             # Expected during shutdown
             pass
        except Exception as e_outer:
            # Catch errors during setup or loop condition check
            if self.app_running_event.is_set(): # Avoid logging errors during normal shutdown
                 print(f"AsyncioController: Outer error in stderr reader for {name}: {e_outer}")
        finally:
            # print(f"AsyncioController: Stderr reader for {name} finished.")
            pass

    async def _run_streaming_server(self):
        """Task to run the aiohttp server for streaming AAC."""
        # Exit early if streaming isn't enabled or possible
        if not self.stream_enabled:
            # print("AsyncioController: Streaming server task exiting (streaming disabled or aiohttp missing).")
            return

        app = web.Application()
        # Route requests to the stream path to the handler method
        app.router.add_get(STREAM_PATH, self._handle_stream_request)
        runner = web.AppRunner(app)
        await runner.setup()
        self.http_runner = runner # Store runner for later cleanup

        listen_host = '0.0.0.0' # Listen on all available network interfaces
        listen_port = self.stream_port

        try:
            site = web.TCPSite(runner, listen_host, listen_port)
            await site.start()
            self.http_site = site # Store site for later cleanup

            # Try to determine a user-friendly display URL (localhost is safest bet)
            # Actual accessible IP depends on network configuration.
            # stream_url_display = f"http://localhost:{listen_port}{STREAM_PATH}"
            # Placeholder indicating user needs to find their local IP
            stream_url_display = f"<Local IP>:{listen_port}{STREAM_PATH}"

            print(f"Info: AAC Stream available at http://{stream_url_display} (Listening on {listen_host}:{listen_port})")
            self.put_update("stream_status", f"Stream: AAC @ :{listen_port}{STREAM_PATH} | Clients: 0")

            # Keep the server running by sleeping until shutdown is signaled
            while self.app_running_event.is_set():
                await asyncio.sleep(1) # Periodically check running state

        except OSError as e:
            import errno
            if e.errno == errno.EADDRINUSE:
                # Handle port conflict gracefully
                err_msg = f"Stream Err: Port {listen_port} already in use."
                self.put_update("stream_status", err_msg)
                self.put_update("error", f"HTTP Server Error: Port {listen_port} in use. Streaming disabled.")
                print(f"ERROR: {err_msg} Streaming disabled.")
                self.stream_enabled = False # Disable streaming for this run
            else:
                # Handle other OS errors during server start
                err_msg = f"Stream Err: Server start failed ({e.strerror})"
                self.put_update("stream_status", err_msg)
                self.put_update("error", f"HTTP Server OS Error: {e}")
                print(f"ERROR: Failed to start stream server: {e}. Streaming disabled.")
                self.stream_enabled = False # Disable streaming on other errors too
            # Don't re-raise here; let the main controller loop handle the failed task
        except asyncio.CancelledError:
            # print("AsyncioController: Streaming server task cancelled.")
            # Cleanup happens in finally block
            pass
        except Exception as e:
            # Catch any other unexpected errors during server run
            self.put_update("stream_status", "Stream Err: Server failed")
            self.put_update("error", f"HTTP Server Error: {e}")
            print(f"ERROR: Unhandled exception in streaming server: {e}")
            traceback.print_exc()
            self.stream_enabled = False # Disable streaming on unexpected errors
        finally:
            # --- Server Cleanup ---
            # print("AsyncioController: Cleaning up streaming server...")
            # Stop site first, then runner
            if self.http_site:
                try: await self.http_site.stop()
                except Exception as e_stop: print(f"AsyncioController: Error stopping HTTP site: {e_stop}")
                self.http_site = None
            if self.http_runner:
                try: await self.http_runner.cleanup()
                except Exception as e_clean: print(f"AsyncioController: Error cleaning up HTTP runner: {e_clean}")
                self.http_runner = None

            # Update status one last time
            self.put_update("stream_status", "Stream: Stopped")
            # print("AsyncioController: Streaming server task finished.")

    async def _handle_stream_request(self, request):
        """Handles an incoming HTTP request for the AAC stream."""
        # Prepare a streaming response
        response = web.StreamResponse(
            status=200, reason='OK', headers={'Content-Type': STREAM_CONTENT_TYPE}
        )
        # Attempt to disable Nagle's algorithm for lower latency (best effort)
        if hasattr(request.transport, 'set_write_buffer_limits'):
            try: request.transport.set_write_buffer_limits(0)
            except Exception: pass
        elif hasattr(request.transport, 'get_extra_info'):
            sock = request.transport.get_extra_info('socket')
            if sock and hasattr(sock, 'setsockopt'):
                try:
                    import socket
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception: pass

        # Prepare the response writer coroutine
        writer = await response.prepare(request)

        # Create a queue for this specific client to receive AAC data
        client_queue = asyncio.Queue(maxsize=10) # Limit buffer per client
        self.aac_clients.add(client_queue)
        self._update_client_count() # Update UI with new client count
        client_ip = request.remote
        # print(f"Stream Client Connected: {client_ip}")

        try:
            # Loop to send data chunks to this client
            while self.app_running_event.is_set():
                try:
                    # Wait for an AAC chunk from the relay task (with timeout)
                    chunk = await asyncio.wait_for(client_queue.get(), timeout=30.0)

                    if chunk is None: # None signifies end-of-stream from relay
                        break # Exit loop, close connection

                    # Write the chunk to the client
                    await writer.write(chunk)
                    # await writer.drain() # Usually handled by aiohttp automatically
                    client_queue.task_done() # Mark item as processed

                except asyncio.TimeoutError:
                    # print(f"Stream Client {client_ip}: Timeout waiting for data. Closing.")
                    break
                except asyncio.CancelledError:
                    break # Task cancelled, likely shutdown
                except ConnectionResetError:
                    # print(f"Stream Client {client_ip}: Connection reset by peer.")
                    break # Client disconnected abruptly
                except Exception as e:
                    # Handle other errors during write
                    print(f"Error writing to stream client {client_ip}: {type(e).__name__}: {e}")
                    break

        finally:
            # --- Client Cleanup ---
            # Remove client queue from the active set
            if client_queue in self.aac_clients:
                self.aac_clients.remove(client_queue)
            self._update_client_count() # Update UI
            # print(f"Stream Client Disconnected: {client_ip}")
            # Ensure queue is emptied to prevent blocking relay task later
            while not client_queue.empty():
                try: client_queue.get_nowait(); client_queue.task_done()
                except queue.Empty: break
                except Exception: break # Should not happen

        return response

    async def _relay_aac_data(self):
        """Task to read AAC data from ffmpeg's stdout and relay it to connected HTTP clients."""
        if not self.stream_enabled:
            # print("AsyncioController: AAC relay task exiting (streaming disabled).")
            return

        # print("AsyncioController: AAC relay task started.")
        try:
            # Wait until ffmpeg process is started and stdout is available
            while self.ffmpeg_proc is None or self.ffmpeg_proc.stdout is None:
                if not self.app_running_event.is_set() or not self.stream_enabled:
                    # print("AsyncioController: AAC relay exiting (ffmpeg not ready or shutdown/disabled).")
                    return
                await asyncio.sleep(0.2)

            # print("AsyncioController: AAC relay reading from ffmpeg stdout...")
            while self.app_running_event.is_set() and self.stream_enabled:
                 # Read a chunk of AAC data from ffmpeg
                 chunk = await self.ffmpeg_proc.stdout.read(1024) # Adjust chunk size if needed

                 if not chunk:
                     # EOF from ffmpeg means it exited
                     # print("AsyncioController: AAC relay received EOF from ffmpeg.")
                     if self.app_running_event.is_set(): # Log error only if not during normal shutdown
                          print("Warning: ffmpeg process exited unexpectedly while relaying.")
                          self.put_update("error", "ffmpeg exited unexpectedly during relay.")
                          # Assume streaming should stop if encoder dies
                          self.stream_enabled = False
                          self.ffmpeg_proc = None # Mark as stopped
                     break # Exit relay loop

                 # --- Distribute chunk to connected HTTP clients ---
                 # Iterate over a copy in case the set changes during iteration
                 current_clients = list(self.aac_clients)
                 if not current_clients: continue # Skip if no clients

                 for q in current_clients:
                     try:
                         # Try putting the chunk into the client's queue without blocking
                         q.put_nowait(chunk)
                     except asyncio.QueueFull:
                         # Client queue is full (slow client). Drop oldest data and try again.
                         try:
                             q.get_nowait() # Remove oldest chunk
                             q.task_done()
                             q.put_nowait(chunk) # Put the new chunk
                         except asyncio.QueueFull:
                              # Still full, drop the current chunk for this client
                              pass
                         except queue.Empty: pass # Queue emptied between checks
                         except Exception as e_drop: print(f"Error managing full client queue: {e_drop}")
                     except Exception as e_put:
                         # Should not happen with asyncio.Queue unless invalid state
                         print(f"Error putting data into client queue: {e_put}")

        except asyncio.CancelledError:
             # print("AsyncioController: AAC relay task cancelled.")
             pass
        except AttributeError:
             # ffmpeg_proc or its stdout became None unexpectedly
             if self.app_running_event.is_set():
                 print("AsyncioController: AAC relay error: ffmpeg process became invalid.")
                 self.put_update("error", "AAC relay failed: ffmpeg process invalid.")
             pass
        except Exception as e:
             # Catch other unexpected errors during read/relay
             if self.app_running_event.is_set():
                 print(f"Error reading/relaying AAC data: {e}")
                 traceback.print_exc()
                 self.put_update("error", f"AAC relay error: {e}")
        finally:
             # --- Relay Cleanup ---
             # print("AsyncioController: AAC relay task signalling EOF to clients.")
             # Send None (EOF marker) to all connected clients so they disconnect cleanly
             current_clients = list(self.aac_clients)
             for q in current_clients:
                 try:
                     # Clear queue first if full to make space for None
                     while q.full(): q.get_nowait(); q.task_done()
                     q.put_nowait(None) # Signal EOF
                 except Exception: pass # Ignore errors putting EOF during shutdown
             # print("AsyncioController: AAC relay task finished.")

    def _update_client_count(self):
        """Updates the stream status message with the current AAC client count."""
        # This can be called from different contexts, UI update is thread-safe via queue
        if self.stream_enabled and self.http_runner: # Only update if server is running
            count = len(self.aac_clients)
            # Update status message - show port and path
            stream_url_display = f":{self.stream_port}{STREAM_PATH}"
            self.put_update("stream_status", f"Stream: AAC @ {stream_url_display} | Clients: {count}")


# =============================================================================
# Tkinter GUI Application Class
# =============================================================================
if tkinter_available:
    class RadioApp(tk.Tk):
        """
        The main Tkinter application window for the radio client.
        Manages UI elements, interacts with AsyncioController via queues.
        """
        def __init__(self, initial_address=None, stream_enabled=False,
                     is_restream_only=False, cmd_queue=None, upd_queue=None, cli_args=None):
            super().__init__()
            self.title("FM-DX Client - antonioag95 - v1.0")
            if is_restream_only:
                self.title(self.title() + " (Restream Only)") # Indicate mode

            self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
            self.resizable(False, False) # Prevent resizing which breaks layout
            self.protocol("WM_DELETE_WINDOW", self.on_close) # Handle window close button

            # Store command-line args for reference (e.g., stream port)
            self.cli_args = cli_args

            # Set application icon (best effort)
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                icon_path = os.path.join(script_dir, "icon.png")
                if os.path.exists(icon_path):
                    photo = tk.PhotoImage(file=icon_path)
                    self.iconphoto(True, photo) # Use iconphoto for better PNG support
                    # print(f"Info: Loaded icon from {icon_path}")
                # else: print(f"Warning: Icon file not found: {icon_path}")
            except Exception as e:
                # print(f"Warning: Could not set application icon: {e}")
                pass # Non-critical

            # Use provided queues or create new ones if running standalone
            self.command_queue = cmd_queue if cmd_queue else queue.Queue()
            self.update_queue = upd_queue if upd_queue else queue.Queue()

            # Store operational mode flags
            self.is_restream_only = is_restream_only
            self.stream_enabled = stream_enabled # Store initial requested stream setting

            # --- Theme Colors (Light Theme) ---
            self.LT_BG_COLOR = "#f0f0f7"       # Light background
            self.LT_BG_ALT_COLOR = "#e4e4ec"   # Slightly darker alt background
            self.LT_FG_COLOR = "#1c1c1f"       # Dark text
            self.LT_FG_LABEL_COLOR = "#505060" # Slightly lighter label text
            self.LT_ACCENT_COLOR = "#0052cc"   # Standard blue accent
            self.LT_ACCENT_ACTIVE = "#0069ff"  # Brighter blue on active/hover
            self.LT_DISABLED_FG = "#90909c"    # Gray for disabled text/elements

            self.configure(bg=self.LT_BG_COLOR) # Set root window background

            # --- Internal State ---
            self.connection_state = "disconnected" # "disconnected", "connecting", "connected", "disconnecting", "error"
            self.current_freq_khz = 0
            self.last_data = {}
            self.stream_status_str = "" # Displayed stream status

            # --- Initial Dependency Checks (GUI Context) ---
            # Check ffplay only if local playback might be used
            if not self.is_restream_only:
                if not check_ffplay(show_error_popup=True):
                     messagebox.showwarning("Dependency Warning",
                                            "'ffplay' not found in PATH.\n"
                                            "Local audio playback will not work.")
            # Check streaming dependencies if streaming is requested
            if self.stream_enabled:
                if not aiohttp_available:
                    messagebox.showerror("Dependency Error",
                                         "AAC Restreaming requires the 'aiohttp' library.\n"
                                         "Install using: pip install aiohttp\n\n"
                                         "Streaming will be disabled.")
                    self.stream_enabled = False # Disable if dependency missing
                elif not check_ffmpeg(show_error_popup=True):
                     messagebox.showerror("Dependency Error",
                                          "'ffmpeg' not found in PATH.\n"
                                          "Streaming will be disabled.")
                     self.stream_enabled = False # Disable if dependency missing

            # --- Fonts ---
            try:
                self.font_large_bold = tkFont.Font(family="Segoe UI", size=24, weight="bold")
                self.font_medium_bold = tkFont.Font(family="Segoe UI", size=18, weight="bold")
                self.font_standard = tkFont.Font(family="Segoe UI", size=10)
                self.font_label = tkFont.Font(family="Segoe UI", size=9, weight="bold")
                self.font_small = tkFont.Font(family="Segoe UI", size=9)
                self.font_mono = tkFont.Font(family="Consolas", size=10) # Monospaced for RT
                self.font_rds_pty = tkFont.Font(family="Segoe UI", size=11, weight="bold")
                self.font_rds_flag = tkFont.Font(family="Segoe UI", size=10, weight="bold")
            except tk.TclError: # Fallback if specific fonts aren't available
                print("Warning: Using default fonts as Segoe UI/Consolas might be unavailable.")
                self.font_large_bold = tkFont.Font(size=24, weight="bold")
                self.font_medium_bold = tkFont.Font(size=18, weight="bold")
                self.font_standard = tkFont.Font(size=10)
                self.font_label = tkFont.Font(size=9, weight="bold")
                self.font_small = tkFont.Font(size=9)
                self.font_mono = tkFont.Font(family="monospace", size=10)
                self.font_rds_pty = tkFont.Font(size=11, weight="bold")
                self.font_rds_flag = tkFont.Font(size=10, weight="bold")


            # --- UI Style Configuration (using ttk for better look & feel) ---
            style = ttk.Style(self)
            style.theme_use('clam') # Use a modern theme if available

            # General style settings
            style.configure('.', background=self.LT_BG_COLOR, foreground=self.LT_FG_COLOR,
                            font=self.font_standard, borderwidth=0)
            style.configure('TLabel', background=self.LT_BG_COLOR, foreground=self.LT_FG_COLOR)
            style.configure('TFrame', background=self.LT_BG_COLOR)
            style.configure('Alt.TFrame', background=self.LT_BG_ALT_COLOR) # For status bar etc.

            # Specific widget styles
            style.configure('LargeBold.TLabel', font=self.font_large_bold)
            style.configure('MediumBold.TLabel', font=self.font_medium_bold)
            style.configure('Small.TLabel', font=self.font_small)
            style.configure('Label.TLabel', font=self.font_label, foreground=self.LT_FG_LABEL_COLOR)
            style.configure('Mono.TLabel', font=self.font_mono)
            style.configure('RDSDisplay.TFrame', background=self.LT_BG_COLOR, borderwidth=1,
                            relief='groove') # Maybe 'flat' with padding?
            style.configure('RDS.PTY.TLabel', font=self.font_rds_pty)
            style.configure('RDS.Flag.TLabel', font=self.font_rds_flag, foreground=self.LT_DISABLED_FG)
            style.configure('TLabelframe', background=self.LT_BG_COLOR, borderwidth=1)
            style.configure('TLabelframe.Label', background=self.LT_BG_COLOR,
                            foreground=self.LT_FG_LABEL_COLOR, font=self.font_label)
            style.configure('TButton', background=self.LT_ACCENT_COLOR, foreground='white',
                            font=self.font_standard, padding=(8, 4), relief='raised', borderwidth=1)
            style.configure('Seek.TButton', font=self.font_standard, width=2, padding=(5, 3))
            style.configure('TEntry', fieldbackground='white', foreground=self.LT_FG_COLOR,
                            insertcolor=self.LT_FG_COLOR, bordercolor=self.LT_FG_LABEL_COLOR,
                            borderwidth=1, relief='solid', padding=(5,3))

            # Style states (active, disabled)
            style.map('TLabel', foreground=[('disabled', self.LT_DISABLED_FG)])
            style.map('Small.TLabel', foreground=[('disabled', self.LT_DISABLED_FG)])
            style.map('Label.TLabel', foreground=[('disabled', self.LT_DISABLED_FG)])
            style.map('TButton',
                      background=[('active', self.LT_ACCENT_ACTIVE), ('disabled', self.LT_BG_ALT_COLOR)],
                      foreground=[('disabled', self.LT_DISABLED_FG)])
            style.map('TEntry', bordercolor=[('focus', self.LT_ACCENT_COLOR)])

            # --- UI Variables (using Tkinter StringVars for dynamic updates) ---
            default_addr = "http://example.com:8073" # Placeholder/Example
            self.server_address_var = tk.StringVar(value=initial_address if initial_address else default_addr)
            self.station_name_var = tk.StringVar(value="----") # PS Name
            self.pi_var = tk.StringVar(value="----")           # PI Code
            self.freq_mhz_var = tk.StringVar(value="---.---")  # Frequency
            self.signal_peak_var = tk.StringVar(value="")      # Peak Signal
            self.signal_current_var = tk.StringVar(value="--.-") # Current Signal
            self.signal_unit_var = tk.StringVar(value="dBf")   # Signal Unit (assumed)
            self.rt0_var = tk.StringVar(value="")              # RadioText Line 0
            self.rt1_var = tk.StringVar(value="")              # RadioText Line 1
            self.tx_name_var = tk.StringVar(value="")          # Transmitter Name
            self.tx_city_itu_var = tk.StringVar(value="")      # Transmitter City/Country
            self.tx_details_var = tk.StringVar(value="")       # Transmitter ERP/Pol/Dist/Azi
            self.status_var = tk.StringVar(value="Status: Disconnected") # Main status
            self.stream_status_var = tk.StringVar(value="")    # Streaming status
            self.manual_freq_mhz_var = tk.StringVar(value="")  # Manual tune input
            self.client_info_var = tk.StringVar(value="")      # Listener count display
            # RDS Specific Variables
            self.rds_pty_var = tk.StringVar(value="---")       # Program Type
            self.rds_tp_var = tk.StringVar(value="TP")         # Traffic Program flag text
            self.rds_ta_var = tk.StringVar(value="TA")         # Traffic Announce flag text
            self.rds_stereo_var = tk.StringVar(value="○")      # Stereo symbol (○=Mono, ◎=Stereo)
            self.rds_ms_var = tk.StringVar(value="")           # Music/Speech flag text (M/S)

            # --- Build UI Elements ---
            self._create_widgets() # Call method to construct the UI layout
            self.asyncio_controller = None # Will hold the AsyncioController instance

            # --- Keyboard Bindings ---
            self.bind("<Left>", self.tune_down_event)    # Left arrow
            self.bind("<Right>", self.tune_up_event)     # Right arrow
            self.bind("<Next>", self.tune_down_event)    # Page Down
            self.bind("<Prior>", self.tune_up_event)     # Page Up

            # --- Start processing updates from the controller queue ---
            self.after(100, self.process_update_queue) # Check queue every 100ms
            self._update_ui_for_state() # Set initial enable/disable state of widgets

            # --- Auto-connect if address provided via command line ---
            if initial_address:
                self.after(200, self.connect_to_server) # Short delay after UI setup

        def _create_widgets(self):
            """Creates and packs/grids all the UI widgets."""
            # --- Top Connection Bar ---
            self.connection_frame = self._create_connection_frame(self)
            self.connection_frame.pack(side=tk.TOP, fill=tk.X, padx=PAD_X, pady=(PAD_Y, 0))

            # --- Main Content Frame (initially hidden) ---
            self.main_display_frame = ttk.Frame(self, padding=(PAD_X, PAD_Y))
            # Configure columns to share width
            self.main_display_frame.columnconfigure(0, weight=1, minsize=300)
            self.main_display_frame.columnconfigure(1, weight=1, minsize=300)
            # Configure rows (Radiotext and TxInfo get vertical space)
            self.main_display_frame.rowconfigure(0, weight=0) # PS/PI/RDS Info
            self.main_display_frame.rowconfigure(1, weight=0) # Freq/Signal
            self.main_display_frame.rowconfigure(2, weight=1, minsize=40) # Radiotext
            self.main_display_frame.rowconfigure(3, weight=1, minsize=50) # Tx Info
            self.main_display_frame.rowconfigure(4, weight=0) # Controls

            # --- Row 0: PS / PI / RDS Info ---
            # Left side: PS and PI
            left_top_frame = ttk.Frame(self.main_display_frame)
            left_top_frame.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_X//2), pady=(0, PAD_Y))
            left_top_frame.grid_propagate(False) # Prevent resizing based on content
            self._create_ps_pi_widgets(left_top_frame)
            # Right side: RDS Flags
            self.rds_labelframe = ttk.LabelFrame(self.main_display_frame, text="RDS INFO")
            self.rds_labelframe.grid(row=0, column=1, sticky="nsew", padx=(PAD_X//2, 0), pady=(0, PAD_Y))
            rds_content_frame = ttk.Frame(self.rds_labelframe, padding=(PAD_X, PAD_Y // 2))
            rds_content_frame.pack(fill=tk.BOTH, expand=True)
            self._create_rds_display_widgets(rds_content_frame)

            # --- Row 1: Frequency / Signal ---
            # Left side: Frequency
            left_mid_frame = ttk.Frame(self.main_display_frame)
            left_mid_frame.grid(row=1, column=0, sticky="ew", padx=(0, PAD_X//2), pady=PAD_Y)
            left_mid_frame.grid_propagate(False)
            self._create_frequency_widgets(left_mid_frame)
            # Right side: Signal Strength
            right_mid_frame = ttk.Frame(self.main_display_frame)
            right_mid_frame.grid(row=1, column=1, sticky="ew", padx=(PAD_X//2, 0), pady=PAD_Y)
            right_mid_frame.grid_propagate(False)
            self._create_signal_widgets(right_mid_frame)

            # --- Row 2: Radiotext ---
            rt_labelframe = ttk.LabelFrame(self.main_display_frame, text="RADIOTEXT")
            rt_labelframe.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=PAD_Y)
            rt_labelframe.grid_propagate(False) # Prevent resize
            rt_content_frame = ttk.Frame(rt_labelframe, padding=(PAD_X, PAD_Y))
            rt_content_frame.pack(fill=tk.BOTH, expand=True)
            rt_content_frame.pack_propagate(False) # Prevent resize
            self._create_radiotext_widgets(rt_content_frame)

            # --- Row 3: Transmitter Info ---
            tx_labelframe = ttk.LabelFrame(self.main_display_frame, text="TRANSMITTER")
            tx_labelframe.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=PAD_Y)
            tx_labelframe.grid_propagate(False) # Prevent resize
            tx_content_frame = ttk.Frame(tx_labelframe, padding=(PAD_X, PAD_Y))
            tx_content_frame.pack(fill=tk.BOTH, expand=True)
            tx_content_frame.pack_propagate(False) # Prevent resize
            self._create_txinfo_widgets(tx_content_frame)

            # --- Row 4: Controls ---
            controls_frame = ttk.Frame(self.main_display_frame)
            controls_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(PAD_Y*2, 0))
            self._create_controls_widgets(controls_frame)

            # --- Status Bar (Bottom) ---
            status_bar_frame = ttk.Frame(self, style='Alt.TFrame') # Use alternate background
            status_bar_frame.pack(side=tk.BOTTOM, fill=tk.X)

            # Listener count (left side)
            self.client_info_label = ttk.Label(status_bar_frame, textvariable=self.client_info_var, anchor=tk.W, style='Small.TLabel')
            self.client_info_label.pack(side=tk.LEFT, padx=(PAD_X, PAD_X // 2), pady=2)

            # Main status message (center, expands)
            status_label = ttk.Label(status_bar_frame, textvariable=self.status_var, anchor=tk.W, style='Small.TLabel')
            status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, PAD_X), pady=2)

            # Streaming status (right side, only if aiohttp available)
            if aiohttp_available:
                self.stream_status_label = ttk.Label(status_bar_frame, textvariable=self.stream_status_var, anchor=tk.E, style='Small.TLabel')
                self.stream_status_label.pack(side=tk.RIGHT, padx=PAD_X, pady=2)

            # Initial UI State: Hide main display until connected
            self._show_main_ui(False)

        # --- Sub-methods for creating widget groups ---
        def _create_connection_frame(self, parent):
            """Creates the top frame with address entry and connect button."""
            frame = ttk.Frame(parent, style='Alt.TFrame', padding=(PAD_X, PAD_Y//2))
            frame.columnconfigure(0, weight=1) # Address entry expands
            self.address_entry = ttk.Entry(frame, textvariable=self.server_address_var, width=40)
            self.address_entry.grid(row=0, column=0, sticky="ew", padx=(0, PAD_X))
            self.connect_button = ttk.Button(frame, text="Connect", command=self.connect_or_disconnect, width=12)
            self.connect_button.grid(row=0, column=1)
            # Bind Enter key in address entry to connect/disconnect action
            self.address_entry.bind("<Return>", lambda event: self.connect_or_disconnect())
            return frame

        def _create_ps_pi_widgets(self, parent):
            """Creates labels for Program Service name (PS) and PI code."""
            parent.columnconfigure(0, weight=1) # Allow PS label to use width
            self.ps_label = ttk.Label(parent, textvariable=self.station_name_var, style='LargeBold.TLabel', anchor='w', wraplength=PS_WRAP_LENGTH)
            self.ps_label.pack(fill=tk.X, pady=(0, PAD_Y))
            # Frame for PI code label + value
            pi_frame = ttk.Frame(parent)
            pi_frame.pack(fill=tk.X)
            ttk.Label(pi_frame, text="PI:", style='Label.TLabel', anchor='w').pack(side=tk.LEFT, padx=(0, PAD_X//2))
            ttk.Label(pi_frame, textvariable=self.pi_var, style='MediumBold.TLabel', anchor='w').pack(side=tk.LEFT)

        def _create_rds_display_widgets(self, parent):
            """Creates labels for PTY and RDS flags (TP, TA, Stereo, M/S)."""
            parent.columnconfigure(0, weight=1) # Center content horizontally
            parent.rowconfigure(0, weight=0)    # PTY row
            parent.rowconfigure(1, weight=0)    # Flags row
            # PTY Label (centered)
            self.rds_pty_label = ttk.Label(parent, textvariable=self.rds_pty_var, style='RDS.PTY.TLabel', anchor=tk.CENTER)
            self.rds_pty_label.grid(row=0, column=0, sticky="ew", pady=(0, PAD_Y))
            # Inner frame to group flags horizontally (centered)
            flags_inner_frame = ttk.Frame(parent)
            flags_inner_frame.grid(row=1, column=0, sticky="")
            pad_flags = PAD_X # Padding between flags
            # Flag labels
            self.rds_tp_label = ttk.Label(flags_inner_frame, textvariable=self.rds_tp_var, style='RDS.Flag.TLabel', anchor=tk.CENTER)
            self.rds_tp_label.pack(side=tk.LEFT, padx=(0, pad_flags // 2))
            self.rds_ta_label = ttk.Label(flags_inner_frame, textvariable=self.rds_ta_var, style='RDS.Flag.TLabel', anchor=tk.CENTER)
            self.rds_ta_label.pack(side=tk.LEFT, padx=(0, pad_flags))
            self.rds_stereo_label = ttk.Label(flags_inner_frame, textvariable=self.rds_stereo_var, style='RDS.Flag.TLabel', anchor=tk.CENTER)
            self.rds_stereo_label.pack(side=tk.LEFT, padx=(0, pad_flags // 2))
            self.rds_ms_label = ttk.Label(flags_inner_frame, textvariable=self.rds_ms_var, style='RDS.Flag.TLabel', anchor=tk.CENTER)
            self.rds_ms_label.pack(side=tk.LEFT, padx=(0, 0))

        def _create_frequency_widgets(self, parent):
            """Creates labels for the frequency display."""
            parent.columnconfigure(0, weight=1) # Center content
            parent.rowconfigure(1, weight=1)    # Allow vertical centering if needed
            ttk.Label(parent, text="FREQUENCY", style='Label.TLabel', anchor='center').pack(fill=tk.X, pady=(0, PAD_Y))
            ttk.Label(parent, textvariable=self.freq_mhz_var, style='LargeBold.TLabel', anchor='center').pack(fill=tk.NONE, expand=False)

        def _create_signal_widgets(self, parent):
            """Creates labels for signal strength (current and peak)."""
            parent.columnconfigure(0, weight=1) # Center content
            parent.rowconfigure(1, weight=1)    # Allow vertical centering
            ttk.Label(parent, text="SIGNAL", style='Label.TLabel', anchor='center').pack(fill=tk.X, pady=(0, PAD_Y))
            # Frame to group current value and unit, centered horizontally
            center_frame = ttk.Frame(parent)
            center_frame.pack(fill=tk.NONE, expand=False)
            inner_frame = ttk.Frame(center_frame) # Inner frame for precise positioning
            inner_frame.pack()
            # Current signal value
            ttk.Label(inner_frame, textvariable=self.signal_current_var, style='MediumBold.TLabel').pack(side=tk.LEFT)
            # Signal unit (dBf assumed)
            ttk.Label(inner_frame, textvariable=self.signal_unit_var, style='Label.TLabel', padding=(3,0,0,0)).pack(side=tk.LEFT, anchor='s') # Align unit baseline
            # Peak signal value (below current)
            ttk.Label(parent, textvariable=self.signal_peak_var, style='Small.TLabel', anchor='center').pack(fill=tk.X, pady=(PAD_Y // 2, 0))

        def _create_radiotext_widgets(self, parent_frame):
            """Creates labels for the two lines of RadioText."""
            # Use Mono font for better alignment if RT uses fixed spacing
            self.rt0_label = ttk.Label(parent_frame, textvariable=self.rt0_var, style='Mono.TLabel', anchor="nw", justify=tk.LEFT, wraplength=RT_WRAP_LENGTH)
            self.rt0_label.pack(fill=tk.X, anchor='w', pady=(0, PAD_Y//2))
            self.rt1_label = ttk.Label(parent_frame, textvariable=self.rt1_var, style='Mono.TLabel', anchor="nw", justify=tk.LEFT, wraplength=RT_WRAP_LENGTH)
            self.rt1_label.pack(fill=tk.X, anchor='w')

        def _create_txinfo_widgets(self, parent_frame):
            """Creates labels for the transmitter information."""
            self.tx_name_label = ttk.Label(parent_frame, textvariable=self.tx_name_var, style='Label.TLabel', anchor="w", wraplength=TX_WRAP_LENGTH)
            self.tx_name_label.pack(fill=tk.X, anchor="w", pady=(0, PAD_Y//2))
            self.tx_city_label = ttk.Label(parent_frame, textvariable=self.tx_city_itu_var, style='Small.TLabel', anchor="w", wraplength=TX_WRAP_LENGTH)
            self.tx_city_label.pack(fill=tk.X, anchor="w", pady=(0, PAD_Y//2))
            self.tx_details_label = ttk.Label(parent_frame, textvariable=self.tx_details_var, style='Small.TLabel', anchor="w", wraplength=TX_WRAP_LENGTH)
            self.tx_details_label.pack(fill=tk.X, anchor="w")

        def _create_controls_widgets(self, parent):
            """Creates the tuning controls (buttons, entry field)."""
            parent.columnconfigure(0, weight=1) # Center the inner frame
            inner_controls_frame = ttk.Frame(parent)
            inner_controls_frame.grid(row=0, column=0, sticky="") # Center horizontally
            # Tune Down Button
            self.tune_seek_down_button = ttk.Button(inner_controls_frame, text="<", command=self.tune_down, style='Seek.TButton')
            self.tune_seek_down_button.pack(side=tk.LEFT, padx=(0, PAD_X))
            # Manual Frequency Entry
            self.manual_freq_entry = ttk.Entry(inner_controls_frame, textvariable=self.manual_freq_mhz_var, width=7, justify=tk.RIGHT)
            self.manual_freq_entry.pack(side=tk.LEFT, padx=(0, PAD_X // 2))
            self.manual_freq_entry.bind("<Return>", self.manual_tune) # Bind Enter key
            # MHz Label
            ttk.Label(inner_controls_frame, text="MHz", style='Small.TLabel').pack(side=tk.LEFT, padx=(0, PAD_X))
            # Manual Tune Button
            self.manual_tune_button = ttk.Button(inner_controls_frame, text="Tune", command=self.manual_tune, width=6)
            self.manual_tune_button.pack(side=tk.LEFT, padx=(0, PAD_X))
            # Tune Up Button
            self.tune_seek_up_button = ttk.Button(inner_controls_frame, text=">", command=self.tune_up, style='Seek.TButton')
            self.tune_seek_up_button.pack(side=tk.LEFT, padx=(0, 0))

        # --- Connection Logic ---

        def connect_or_disconnect(self):
            """Handles the Connect/Disconnect button press."""
            if self.connection_state == "connected":
                self.disconnect_server()
            elif self.connection_state in ["disconnected", "error"]:
                self.connect_to_server()
            # else: ignore if connecting/disconnecting

        def connect_to_server(self):
            """Initiates connection to the server specified in the address entry."""
            if self.connection_state not in ["disconnected", "error"]:
                return # Already connected or connecting/disconnecting

            # --- Re-check Dependencies Before Connecting ---
            # This prevents attempting connection if requirements aren't met.
            if not self.is_restream_only:
                if not check_ffplay(show_error_popup=True):
                    self.set_status("Cannot connect: ffplay not found.")
                    self.set_connection_state("error")
                    return
            if self.stream_enabled: # Check only if streaming was requested and not disabled earlier
                if not aiohttp_available:
                    self.set_status("Cannot connect: aiohttp missing for streaming.")
                    self.set_connection_state("error")
                    return
                if not check_ffmpeg(show_error_popup=True):
                    self.set_status("Cannot connect: ffmpeg not found for streaming.")
                    self.set_connection_state("error")
                    return

            # --- Parse Address and Generate URIs ---
            addr_input = self.server_address_var.get().strip()
            if not addr_input:
                messagebox.showerror("Input Error", "Server address cannot be empty.")
                return
            # Default to http/ws if scheme is missing
            if "://" not in addr_input:
                addr_input = "http://" + addr_input

            try:
                parsed = urlparse(addr_input)
                host = parsed.hostname
                input_scheme = parsed.scheme.lower()
                if not host: raise ValueError("Could not determine hostname from address.")

                # Determine WebSocket scheme (ws/wss) and port
                target_ws_scheme = "wss" if input_scheme in ["https", "wss"] else "ws"
                # Use provided port or default based on scheme
                target_port = parsed.port or (443 if target_ws_scheme == "wss" else 80)
                netloc = f"{host}:{target_port}" # Combine host and port for URIs

                # Construct full WebSocket URIs
                audio_uri = urlunparse((target_ws_scheme, netloc, WEBSOCKET_AUDIO_PATH, "", "", ""))
                text_uri = urlunparse((target_ws_scheme, netloc, WEBSOCKET_TEXT_PATH, "", "", ""))
            except ValueError as e:
                messagebox.showerror("Address Error", f"Invalid server address format:\n{addr_input}\n\nError: {e}")
                self.set_connection_state("error")
                return

            # --- Update UI and Start Controller ---
            self.set_connection_state("connecting")
            self.set_status(f"Connecting to {netloc}...")
            if self.stream_enabled: self.set_stream_status("Stream: Starting...")
            if self.is_restream_only: self.set_status(self.status_var.get() + " (Restream Only)")

            # Stop existing controller if somehow still running
            if self.asyncio_controller and self.asyncio_controller.is_running():
                # print("GUI: Stopping existing AsyncioController before reconnecting...")
                self.asyncio_controller.stop()
                self.asyncio_controller = None
                time.sleep(0.5) # Give previous thread a moment to exit

            # Create and start the new controller instance
            # print("GUI: Creating and starting new AsyncioController...")
            # Get stream port from CLI args if available, else use default
            stream_port_to_use = self.cli_args.port if self.cli_args else STREAM_PORT
            self.asyncio_controller = AsyncioController(
                audio_uri, text_uri, self.command_queue, self.update_queue,
                stream_enabled=self.stream_enabled,
                is_restream_only=self.is_restream_only,
                stream_port=stream_port_to_use
            )
            self.asyncio_controller.start()

            # Show the main data display area now that we are connecting
            self._show_main_ui(True)

        def disconnect_server(self):
            """Initiates disconnection and stops the backend controller."""
            if self.asyncio_controller and self.asyncio_controller.is_running():
                self.set_connection_state("disconnecting")
                self.set_status("Disconnecting...")
                if self.stream_enabled: self.set_stream_status("Stream: Stopping...")
                # print("GUI: Stopping AsyncioController...")
                self.asyncio_controller.stop() # This signals the controller thread
                # The controller will put a 'closed' message on the queue when fully stopped.
            else:
                # If controller wasn't running, just update state immediately
                self.set_connection_state("disconnected")
                self.set_status("Disconnected.")
                self.set_stream_status("")
                self.asyncio_controller = None # Ensure reference is clear

        def set_connection_state(self, new_state):
            """Updates the internal connection state and refreshes the UI."""
            if self.connection_state != new_state:
                self.connection_state = new_state
                self._update_ui_for_state() # Update widget enable/disable states
                # Clear stream status if fully disconnected or error
                if new_state in ["disconnected", "error"]:
                    self.set_stream_status("")

        def _update_ui_for_state(self):
            """Enables/disables UI elements based on the current connection state."""
            state = self.connection_state
            can_edit_connection = (state == "disconnected" or state == "error")
            is_connected_or_connecting = state in ["connected", "connecting", "disconnecting"]
            is_connected = (state == "connected")

            # Connection bar elements
            self.address_entry.config(state=tk.NORMAL if can_edit_connection else tk.DISABLED)
            if state == "connected":
                self.connect_button.config(text="Disconnect", state=tk.NORMAL)
            elif state in ["disconnected", "error"]:
                self.connect_button.config(text="Connect", state=tk.NORMAL)
            else: # connecting or disconnecting
                self.connect_button.config(text="...", state=tk.DISABLED)

            # Main display visibility (show when connecting/connected/disconnecting)
            self._show_main_ui(is_connected_or_connecting)

            # Control buttons and frequency entry state (only enable when fully connected)
            tune_state = tk.NORMAL if is_connected else tk.DISABLED
            # Check if widgets exist before configuring (might be called early)
            if hasattr(self, 'tune_seek_down_button'):
                self.tune_seek_down_button.config(state=tune_state)
            if hasattr(self, 'tune_seek_up_button'):
                self.tune_seek_up_button.config(state=tune_state)
            if hasattr(self, 'manual_freq_entry'):
                self.manual_freq_entry.config(state=tune_state)
            if hasattr(self, 'manual_tune_button'):
                self.manual_tune_button.config(state=tune_state)

            # Clear display variables and manual frequency entry on disconnect/error
            if not is_connected_or_connecting:
                self._clear_display_vars()
                if hasattr(self, 'manual_freq_mhz_var'): self.manual_freq_mhz_var.set("")

        def _show_main_ui(self, show=True):
            """Shows or hides the main data display frame."""
            if hasattr(self, 'main_display_frame'):
                # Check if already in desired state to avoid unnecessary packing/unpacking
                is_mapped = self.main_display_frame.winfo_ismapped()
                if show and not is_mapped:
                    self.main_display_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
                elif not show and is_mapped:
                    self.main_display_frame.pack_forget()

        def _clear_display_vars(self):
            """Resets all data display StringVars to their default/empty states."""
            self.station_name_var.set("----")
            self.pi_var.set("----")
            self.freq_mhz_var.set("---.---")
            self.signal_peak_var.set("")
            self.signal_current_var.set("--.-")
            self.signal_unit_var.set("dBf") # Reset to default unit
            self.rt0_var.set("")
            self.rt1_var.set("")
            self.tx_name_var.set("")
            self.tx_city_itu_var.set("")
            self.tx_details_var.set("")
            self.client_info_var.set("") # Clear listener count
            self.current_freq_khz = 0    # Reset internal frequency state
            # Reset RDS Display Variables
            self.rds_pty_var.set("---")
            self.rds_tp_var.set("TP")
            self.rds_ta_var.set("TA")
            self.rds_stereo_var.set("○") # Mono symbol
            self.rds_ms_var.set("")
            # Reset RDS flag colors to default (inactive)
            inactive_color = self.LT_DISABLED_FG
            # Check widgets exist before configuring colors
            if hasattr(self, 'rds_tp_label'): self.rds_tp_label.config(foreground=inactive_color)
            if hasattr(self, 'rds_ta_label'): self.rds_ta_label.config(foreground=inactive_color)
            # Keep stereo symbol visible, but maybe indicate mono state if needed? Color is handled in update_display.
            if hasattr(self, 'rds_stereo_label'): self.rds_stereo_label.config(foreground=self.LT_FG_COLOR)
            if hasattr(self, 'rds_ms_label'): self.rds_ms_label.config(foreground=inactive_color)

        # --- Event Handling & Updates ---

        def process_update_queue(self):
            """Periodically called method to process messages from the controller's update queue."""
            try:
                # Process all messages currently in the queue without blocking
                while True:
                    message_type, data = self.update_queue.get_nowait()

                    if message_type == "data":
                        # Only update display if we are in a connected state
                        if self.connection_state == "connected":
                            self.update_display(data)
                    elif message_type == "status":
                        self.set_status(data) # Update main status bar text
                        # Update connection state based on status messages from controller
                        if self.connection_state == "connecting":
                            # Consider connection successful if key WS connections reported
                            if "connected." in data.lower() and ("Text WS" in data or "Audio WS" in data):
                                # Check if it's the "Skipping local playback" message in restream-only mode
                                if not (self.is_restream_only and "Skipping local playback" in data):
                                     # If not that specific message, assume connection is up
                                     self.set_connection_state("connected")
                            # If connection fails during 'connecting' state
                            elif ("failed" in data.lower() or "refused" in data.lower() or
                                  "timeout" in data.lower() or "invalid" in data.lower() or
                                  "error" in data.lower()): # Catch generic errors too
                                self.set_connection_state("error")
                        elif self.connection_state == "connected":
                            # If we get a disconnect/error message while connected, move to error state
                            if ("disconnected" in data.lower() or "closed" in data.lower() or
                                "timeout" in data.lower() or "error" in data.lower()):
                                # Avoid overwriting critical error messages with simple "disconnected"
                                if "error" not in self.status_var.get().lower():
                                    self.set_status(f"Connection lost: {data}.")
                                self.set_connection_state("error") # Trigger reconnect possibility

                    elif message_type == "stream_status":
                        # Update the streaming status part of the status bar
                        self.set_stream_status(data)

                    elif message_type == "current_freq":
                        # Update frequency display immediately based on controller confirmation
                        if self.connection_state == "connected":
                            new_khz = data
                            self.current_freq_khz = new_khz
                            self.freq_mhz_var.set(khz_to_mhz_str(new_khz))

                    elif message_type == "error":
                        # Display error messages in the status bar
                        error_msg = f"Error: {data}"
                        self.set_status(error_msg[:150]) # Limit length
                        # Treat certain errors as fatal for the connection attempt/run
                        is_fatal_error = False
                        # ffplay missing is fatal only if needed
                        if "'ffplay' not found" in data and not self.is_restream_only: is_fatal_error = True
                        # ffmpeg missing is fatal only if streaming enabled
                        if "'ffmpeg' not found" in data and self.stream_enabled: is_fatal_error = True
                        # Other explicitly fatal conditions
                        if ("Invalid URI" in data or "Fatal" in data or
                            "aiohttp required" in data or ("Port" in data and "in use" in data)):
                            is_fatal_error = True

                        if is_fatal_error:
                             # Set error state to allow reconnect if possible, but show popup for truly fatal ones
                             self.set_connection_state("error")
                             if "Fatal" in data or "Invalid URI" in data or "Port" in data:
                                 messagebox.showerror("Connection Error", f"Fatal connection error:\n{data}\n\nPlease check the address/configuration and try again.")
                             # Consider if app should exit on fatal error? Currently allows retry.

                    elif message_type == "closed":
                        # AsyncioController has fully stopped and cleaned up
                        # print("GUI: Received 'closed' signal from AsyncioController.")
                        # Update state only if not already manually disconnected
                        if self.connection_state != "disconnected":
                            if self.connection_state == "disconnecting":
                                 # Normal disconnect finished
                                 self.set_connection_state("disconnected")
                                 self.set_status("Disconnected.")
                            else:
                                 # Controller stopped unexpectedly (e.g., crash, fatal error)
                                 self.set_connection_state("error")
                                 if "error" not in self.status_var.get().lower(): # Avoid overwriting specific error
                                     self.set_status("Connection closed unexpectedly.")
                        self.set_stream_status("") # Clear stream status on closure
                        self.asyncio_controller = None # Clear controller reference

                    # Mark the message as processed in the queue
                    self.update_queue.task_done()

            except queue.Empty:
                # No more messages in the queue for now
                pass
            except Exception as e:
                # Catch errors during UI update itself
                print(f"Error processing update queue: {e}")
                traceback.print_exc()
            finally:
                # Reschedule the next check only if the window still exists
                # This prevents errors after the window is closed
                if self.winfo_exists():
                    self.after(100, self.process_update_queue)

        def update_display(self, data):
            """Updates the UI StringVars based on the received data dictionary."""
            if not data: return
            self.last_data = data # Store last received data

            # --- Extract data points (with defaults for missing keys) ---
            # Listener count
            client_value = data.get("users")
            display_text = f"Listeners: {client_value}" if client_value is not None else ""
            self.client_info_var.set(display_text)

            # Station Info
            pi = data.get("pi", "----") # Provide default if key missing
            station_ps = data.get("ps", "").strip() or "----" # Use PS, fallback to ----

            # Frequency (already updated by 'current_freq' message, but keep internal state consistent)
            data_freq_khz = mhz_to_khz(data.get("freq"))
            if data_freq_khz is not None:
                self.current_freq_khz = data_freq_khz
            # Note: self.freq_mhz_var is updated by the 'current_freq' handler for responsiveness

            # Signal Strength (Assume dBf units from source, adjust if needed)
            sig_db = data.get("sig") # Current signal
            sig_top_db_str = data.get("sigTop") # Peak signal (can be string/float/int)
            sig_top_db = None
            # Safely convert peak signal to float
            if isinstance(sig_top_db_str, (str, int, float)):
                try: sig_top_db = float(sig_top_db_str)
                except (ValueError, TypeError): pass
            # Format for display
            sig_curr_str = f"{sig_db:.1f}" if isinstance(sig_db, (int, float)) else "--.-"
            sig_peak_str = f"Peak: {sig_top_db:.1f} dBf" if sig_top_db is not None else ""
            self.signal_unit_var.set("dBf") # Explicitly set unit display

            # RDS Flags
            pty_code = data.get("pty")
            pty_str = PTY_CODES.get(pty_code, f"PTY {pty_code}") if isinstance(pty_code, int) else "---"
            tp_flag = data.get("tp", 0) == 1 # Traffic Program
            ta_flag = data.get("ta", 0) == 1 # Traffic Announcement
            ms_code = data.get("ms", -1)     # Music(1)/Speech(0)
            stereo_flag = data.get("st", 0) == 1 # Stereo(1)/Mono(0)

            # Radiotext (RT/RT+)
            rt0 = data.get("rt0", "").strip()
            rt1 = data.get("rt1", "").strip()

            # Transmitter Info
            tx_info = data.get("txInfo", {}) # Default to empty dict
            tx_name = tx_info.get("tx", "")
            city = tx_info.get("city", "")
            itu = tx_info.get("itu", "") # Often country code
            erp = tx_info.get("erp")     # Effective Radiated Power (kW)
            pol = tx_info.get("pol", "") # Polarization
            dist = tx_info.get("dist")   # Distance (km)
            azi = tx_info.get("azi")     # Azimuth (degrees)
            # Format combined City/ITU string
            tx_city_itu_display = f"{city} [{itu}]" if city and itu else city or (f"[{itu}]" if itu else "")
            # Format details string
            tx_detail_parts = []
            if isinstance(erp, (int, float)) and erp > 0: tx_detail_parts.append(f"{erp:.1f}kW")
            if pol: tx_detail_parts.append(f"Pol:{pol}")
            if dist is not None and str(dist).strip(): tx_detail_parts.append(f"{dist}km")
            if azi is not None and str(azi).strip(): tx_detail_parts.append(f"{azi}°")
            tx_details_display = " ▪ ".join(filter(None, tx_detail_parts)) # Join with separator

            # --- Determine RDS Flag States and Colors for UI ---
            pty_display = pty_str # Use the looked-up name

            # Active/Inactive colors for flags
            active_color = self.LT_FG_COLOR
            inactive_color = self.LT_DISABLED_FG

            tp_color = active_color if tp_flag else inactive_color
            ta_color = active_color if ta_flag else inactive_color

            # Stereo symbol and color (always visible, symbol changes)
            stereo_symbol = "◎" if stereo_flag else "○" # Ring vs Circle
            stereo_color = active_color # Keep symbol visible

            # Music/Speech text and color
            if ms_code == 1: ms_text, ms_color = "M", active_color # Music
            elif ms_code == 0: ms_text, ms_color = "S", active_color # Speech
            else: ms_text, ms_color = "", inactive_color           # Undefined/Off

            # --- Update Tkinter StringVars (this triggers UI redraw) ---
            self.station_name_var.set(station_ps)
            self.pi_var.set(pi)
            # self.freq_mhz_var is updated by 'current_freq' message handler
            self.signal_current_var.set(sig_curr_str)
            self.signal_peak_var.set(sig_peak_str)
            self.rt0_var.set(rt0)
            self.rt1_var.set(rt1)
            self.tx_name_var.set(tx_name if tx_name else "N/A")
            self.tx_city_itu_var.set(tx_city_itu_display if tx_city_itu_display else "N/A")
            self.tx_details_var.set(tx_details_display if tx_details_display else "N/A")

            # --- Update RDS Display Section Variables ---
            self.rds_pty_var.set(pty_display)
            self.rds_tp_var.set("TP") # Text is constant
            self.rds_ta_var.set("TA") # Text is constant
            self.rds_stereo_var.set(stereo_symbol) # Symbol changes
            self.rds_ms_var.set(ms_text) # Text changes (M/S/'')

            # --- Update RDS Flag Label Colors Directly ---
            # (Check widgets exist in case called before fully initialized)
            if hasattr(self, 'rds_tp_label'): self.rds_tp_label.config(foreground=tp_color)
            if hasattr(self, 'rds_ta_label'): self.rds_ta_label.config(foreground=ta_color)
            if hasattr(self, 'rds_stereo_label'): self.rds_stereo_label.config(foreground=stereo_color)
            if hasattr(self, 'rds_ms_label'): self.rds_ms_label.config(foreground=ms_color)

        def set_status(self, message):
            """Updates the main status message in the status bar."""
            # Limit length to prevent excessively long messages
            self.status_var.set(f"Status: {message[:150]}")

        def set_stream_status(self, message):
            """Updates the streaming status message in the status bar."""
            # Check if the label exists (it's created conditionally)
            if hasattr(self, 'stream_status_var'):
                self.stream_status_var.set(message)

        # --- Commands & Tuning ---
        def send_command(self, command):
            """Puts a command (e.g., tune request) onto the shared command queue."""
            if self.connection_state == "connected" and self.asyncio_controller and self.asyncio_controller.is_running():
                # Send command to the backend controller via the queue
                self.command_queue.put(command)
            elif self.connection_state != "connected":
                self.set_status("Cannot send command: Not connected.")
            # else: Controller might be stopping/starting, ignore command

        def tune_up_event(self, event=None):
            """Handles the tune up keyboard event."""
            self.tune_up()

        def tune_down_event(self, event=None):
            """Handles the tune down keyboard event."""
            self.tune_down()

        def tune_up(self):
            """Sends a command to tune the frequency up by one step."""
            if self.connection_state != "connected" or self.current_freq_khz <= 0: return
            target_khz = self.current_freq_khz + FREQ_STEP_KHZ
            max_khz = int(MAX_FREQ_MHZ * 1000)
            target_khz = min(target_khz, max_khz) # Clamp to maximum frequency
            if target_khz != self.current_freq_khz:
                freq_display_str = khz_to_mhz_str(target_khz)
                self.set_status(f"Tuning up to {freq_display_str} MHz...")
                self.send_command(f"T{target_khz}") # Send tune command "T<freq_khz>"

        def tune_down(self):
            """Sends a command to tune the frequency down by one step."""
            if self.connection_state != "connected" or self.current_freq_khz <= 0: return
            target_khz = self.current_freq_khz - FREQ_STEP_KHZ
            min_khz = int(MIN_FREQ_MHZ * 1000)
            target_khz = max(target_khz, min_khz) # Clamp to minimum frequency
            if target_khz != self.current_freq_khz:
                freq_display_str = khz_to_mhz_str(target_khz)
                self.set_status(f"Tuning down to {freq_display_str} MHz...")
                self.send_command(f"T{target_khz}") # Send tune command "T<freq_khz>"

        def manual_tune(self, event=None):
            """Sends a command to tune to the frequency entered manually."""
            if self.connection_state != "connected":
                self.set_status("Cannot tune: Not connected.")
                return
            freq_mhz_str = self.manual_freq_mhz_var.get().strip()
            if not freq_mhz_str:
                self.set_status("Manual Tune Error: Frequency cannot be empty.")
                return

            # Validate and convert manual frequency input
            target_khz = mhz_to_khz(freq_mhz_str)
            if target_khz is None:
                self.set_status(f"Manual Tune Error: Invalid frequency '{freq_mhz_str}'. Use {MIN_FREQ_MHZ}-{MAX_FREQ_MHZ} MHz.")
                return

            # Send command only if frequency is different from current
            if target_khz != self.current_freq_khz:
                freq_display_str = khz_to_mhz_str(target_khz)
                self.set_status(f"Tuning manually to {freq_display_str} MHz...")
                self.send_command(f"T{target_khz}")
                self.manual_freq_mhz_var.set("") # Clear entry after sending
            else:
                # Already on frequency, just clear input
                self.set_status(f"Already tuned to {khz_to_mhz_str(target_khz)} MHz.")
                self.manual_freq_mhz_var.set("") # Clear entry

        def on_close(self):
            """Handles the window close event (WM_DELETE_WINDOW)."""
            # print("GUI: Close button pressed.")
            self.set_status("Exiting...")
            # Initiate disconnection and controller shutdown
            self.disconnect_server()
            # Explicitly destroy the Tkinter window if it still exists
            if self.winfo_exists():
                # print("GUI: Destroying window.")
                self.destroy()
            # Ensure the global app running flag is cleared to stop background threads/loops
            app_running.clear()

# =============================================================================
# CLI Mode Functions
# =============================================================================

def format_and_display_data(data):
    """Formats the received data and prints it to the CLI screen."""
    global cli_display_lines_printed, cli_current_freq_khz, cli_last_data, cli_input_line_row

    # Use last received data if no new data provided (for refresh)
    if data:
        cli_last_data = data
    elif not cli_last_data:
        # No data available yet, maybe print placeholder?
        # For now, just return if no data ever received.
        return
    current_data = cli_last_data

    # --- Extract data (similar to GUI update_display) ---
    pi = current_data.get("pi", "----")
    freq_display = khz_to_mhz_str(cli_current_freq_khz) if cli_current_freq_khz else "---.---"
    station_ps = current_data.get("ps", "").strip() or "----"
    sig_db = current_data.get("sig")
    sig_str = f"{sig_db:.1f} dBf" if isinstance(sig_db, (int, float)) else "N/A"
    stereo = "Stereo" if current_data.get("st", 0) == 1 else "Mono"
    pty_code = current_data.get("pty")
    pty_str = PTY_CODES.get(pty_code, f"PTY {pty_code}") if isinstance(pty_code, int) else "N/A"
    tp_flag = current_data.get("tp", 0) == 1
    ta_flag = current_data.get("ta", 0) == 1
    ms_code = current_data.get("ms", -1)
    ms_str = "Music" if ms_code == 1 else ("Speech" if ms_code == 0 else "N/A")
    rt0 = current_data.get("rt0", "").strip()
    rt1 = current_data.get("rt1", "").strip()
    users = current_data.get("users", "N/A")
    tx_info = current_data.get("txInfo", {})
    tx_name = tx_info.get("tx", "")
    city = tx_info.get("city", "")
    itu = tx_info.get("itu", "")
    dist = current_data.get("dist")
    dist_display = f"{dist} km" if dist is not None and str(dist).strip() else "N/A"
    loc_parts = filter(None, [p.strip() for p in [city, itu] if isinstance(p, str)])
    loc_str = ", ".join(loc_parts) or "N/A"

    # Combine PS and TX name if available
    station_display = f"{station_ps:<8} (PI:{pi})"
    if tx_name and isinstance(tx_name, str) and tx_name.strip():
        station_display += f" [{tx_name.strip()}]"

    # --- Format lines for display ---
    lines = [
        "=" * 70,
        f" Station : {station_display}",
        f" Freq    : {freq_display} MHz",
        f" Signal  : {sig_str:<12} Mode : {stereo}",
        f" PTY     : {pty_str}",
        f" Flags   : TP: {'*' if tp_flag else '-'}",
        f"           TA: {'*' if ta_flag else '-'}",
        f"           MS: {ms_str}",
        f" Location: {loc_str}",
        f" Distance: {dist_display}",
        f" Users   : {users}",
        f" RT 0    : {rt0}",
        f" RT 1    : {rt1}",
        "=" * 70,
    ]

    # --- Print using ANSI sequences for screen clearing and positioning ---
    term_width = shutil.get_terminal_size((80, 24)).columns
    print(SAVE_CURSOR, end="")   # Save current cursor position
    print("\033[1;1H", end="") # Move cursor to top-left (row 1, col 1)

    # Print each line, clearing the rest of the line first
    for i, line in enumerate(lines):
        # Truncate line if wider than terminal
        print(f"{CLEAR_LINE}{line[:term_width]}")

    lines_printed_now = len(lines)

    # Clear any leftover lines from previous, longer displays
    if cli_display_lines_printed > lines_printed_now:
        for i in range(lines_printed_now, cli_display_lines_printed):
             print(f"\033[{i+1};1H{CLEAR_LINE}", end="") # Move to start of line and clear

    cli_display_lines_printed = lines_printed_now
    # Calculate where the input/status lines should go
    cli_input_line_row = cli_display_lines_printed + 1

    # Update the status and input prompt lines below the data
    update_cli_input_and_status()

    print(RESTORE_CURSOR, end="", flush=True) # Restore cursor to saved position (usually after input prompt)

def update_cli_input_and_status(temp_message=None):
    """Updates the status and input prompt lines at the bottom of the CLI screen."""
    global cli_input_buffer, cli_status_message, cli_input_line_row
    # Define row numbers relative to the data display
    status_row = cli_input_line_row
    input_row = status_row + 1
    temp_msg_row = input_row + 1
    term_width = shutil.get_terminal_size((80, 24)).columns

    # --- Update Status Line ---
    # Move to status line, clear it, print status message (truncated)
    print(f"\033[{status_row};1H{CLEAR_LINE}", end="")
    print(cli_status_message[:term_width-1], end="")

    # --- Update Input Line ---
    # Move to input line, clear it, print prompt and current buffer
    print(f"\033[{input_row};1H{CLEAR_LINE}", end="")
    prompt = "Tune [MHz] (<>^V Tune, Enter Refresh, Esc Clear): "
    # Display with a blinking cursor placeholder (underscore)
    input_display = f"{prompt}{cli_input_buffer}_"
    print(input_display[:term_width-1], end="")

    # --- Update Temporary Message Line ---
    # Move to temp message line, clear it, print message if provided
    print(f"\033[{temp_msg_row};1H{CLEAR_LINE}", end="")
    if temp_message:
        print(temp_message[:term_width-1], end="")

    # --- Reposition Cursor ---
    # Place cursor at the end of the input buffer for typing
    cursor_col = len(prompt) + len(cli_input_buffer) + 1
    print(f"\033[{input_row};{cursor_col}H", end="", flush=True) # Flush ensures changes are visible

def _blocking_keyboard_listener():
    """
    Runs in a separate thread to listen for keyboard input using 'readchar'.
    Handles key presses for tuning, input buffer, refresh, and exit.
    """
    global cli_input_buffer, cli_current_freq_khz, app_running, cli_command_queue
    if not readchar_available:
        print("Error: readchar library not available for keyboard input.")
        return

    last_temp_message = "" # Store temporary messages (like "Invalid Freq")

    while app_running.is_set():
        try:
            # Read a single keypress (blocking)
            char = readchar.readkey()

            # Clear any temporary message from the previous keypress
            if last_temp_message:
                 update_cli_input_and_status(temp_message="")
                 last_temp_message = ""

            # --- Handle Specific Keys ---
            if char == KEY_CTRL_C:
                print(f"\n{CLEAR_LINE}Ctrl+C detected, initiating shutdown...")
                app_running.clear() # Signal shutdown
                if cli_command_queue: cli_command_queue.put(None) # Wake up controller command listener
                break # Exit listener thread

            elif char == KEY_ESC:
                # Clear the frequency input buffer
                if cli_input_buffer:
                    cli_input_buffer = ""
                    update_cli_input_and_status() # Redraw input line

            elif char in KEY_BACKSPACE:
                # Remove last character from input buffer
                if cli_input_buffer:
                    cli_input_buffer = cli_input_buffer[:-1]
                    update_cli_input_and_status() # Redraw input line

            elif char in KEY_ENTER:
                # Process input buffer if not empty, otherwise refresh display
                if cli_input_buffer:
                    # Try to parse and validate frequency
                    target_khz = mhz_to_khz(cli_input_buffer)
                    if target_khz is not None:
                        # Valid frequency, send tune command
                        cmd = f"T{target_khz}"
                        if cli_command_queue: cli_command_queue.put(cmd)
                        last_temp_message = f"Queued tune to {cli_input_buffer} MHz..."
                    else:
                        # Invalid frequency format or range
                        last_temp_message = f"Invalid Freq ({MIN_FREQ_MHZ}-{MAX_FREQ_MHZ} MHz)."
                    # Clear buffer and update display (showing temp message)
                    cli_input_buffer = ""
                    update_cli_input_and_status(temp_message=last_temp_message)
                else:
                    # No input, treat Enter as refresh request (redraw last data)
                    print(SAVE_CURSOR, end="")
                    format_and_display_data(None) # Use last stored data
                    print(RESTORE_CURSOR, end="", flush=True)

            elif char in KEY_LEFT_SEQ or char in KEY_DOWN_SEQ:
                 # Tune Down
                 if cli_current_freq_khz > 0: # Need current freq to calculate next step
                    target = cli_current_freq_khz - FREQ_STEP_KHZ
                    min_khz = int(MIN_FREQ_MHZ * 1000)
                    target = max(target, min_khz) # Clamp to min freq
                    if target != cli_current_freq_khz:
                         if cli_command_queue: cli_command_queue.put(f"T{target}")
                         # Clear input buffer if user was typing
                         if cli_input_buffer: cli_input_buffer = ""; update_cli_input_and_status()
                 else:
                    # Cannot tune down if current frequency is unknown
                    last_temp_message = "Waiting for frequency info..."
                    update_cli_input_and_status(temp_message=last_temp_message)

            elif char in KEY_RIGHT_SEQ or char in KEY_UP_SEQ:
                 # Tune Up
                 if cli_current_freq_khz > 0: # Need current freq
                    target = cli_current_freq_khz + FREQ_STEP_KHZ
                    max_khz = int(MAX_FREQ_MHZ * 1000)
                    target = min(target, max_khz) # Clamp to max freq
                    if target != cli_current_freq_khz:
                         if cli_command_queue: cli_command_queue.put(f"T{target}")
                         # Clear input buffer if user was typing
                         if cli_input_buffer: cli_input_buffer = ""; update_cli_input_and_status()
                 else:
                    # Cannot tune up if current frequency is unknown
                    last_temp_message = "Waiting for frequency info..."
                    update_cli_input_and_status(temp_message=last_temp_message)

            elif char.isprintable() and (char.isdigit() or char in (".", ",")):
                 # Append valid frequency characters to input buffer
                 if len(cli_input_buffer) < 7: # Limit input length
                     cli_input_buffer += char.replace(",", ".") # Allow comma or dot
                     update_cli_input_and_status() # Redraw input line

        except KeyboardInterrupt:
            # Should be caught by Ctrl+C handler, but handle here just in case
            print(f"\n{CLEAR_LINE}KeyboardInterrupt in listener thread, shutting down...")
            app_running.clear()
            if cli_command_queue: cli_command_queue.put(None)
            break
        except Exception as e:
            # Catch unexpected errors in the listener thread
            # Avoid crashing the whole app if possible, but likely indicates a problem
            if app_running.is_set(): # Only print if not already shutting down
                 print(f"\n{CLEAR_LINE}CLI Keyboard listener error: {e}", flush=True)
                 traceback.print_exc()
                 # Signal shutdown on unexpected listener error
                 app_running.clear()
                 if cli_command_queue: cli_command_queue.put(None)
            break # Exit thread on error
    # print("CLI Keyboard listener thread finished.")

def cli_update_loop(args):
    """
    Runs in the main CLI thread, processing updates from the controller queue
    and updating the CLI display accordingly. Exits when app_running is False.
    """
    global cli_status_message, cli_current_freq_khz, cli_last_data

    while app_running.is_set():
        try:
            # Wait for an update message from the controller (with timeout)
            message_type, data = cli_update_queue.get(block=True, timeout=0.2)

            if message_type == "data":
                # New data received, store it and redraw the display
                cli_last_data = data
                format_and_display_data(None) # Redraw using the new data

            elif message_type == "status":
                # Update the status message line
                # Filter out repetitive "Skipping local playback" in restream-only mode
                if not (args.restream_only and "Skipping local playback" in data):
                    cli_status_message = f"Status: {data}"
                update_cli_input_and_status() # Redraw status/input lines

                # Update state based on status messages (e.g., connected, disconnected)
                if "connected." in data.lower() and ("Text WS" in data or "Audio WS" in data):
                     if "Connecting" in cli_status_message: # If we were connecting, now we are connected
                          cli_status_message = "Status: Connected."
                          update_cli_input_and_status()
                elif ("disconnected" in data.lower() or "closed" in data.lower() or
                      "refused" in data.lower() or "timeout" in data.lower()):
                     # Connection lost or failed, update status to indicate retry
                     if "fully stopped" not in data.lower(): # Avoid "Retrying..." if controller stopped
                        cli_status_message = f"Status: {data}. Retrying..."
                        update_cli_input_and_status()
                     # Clear data display if connection fully lost and not retrying soon
                     # The 'closed' message handles the final state better.

            elif message_type == "stream_status":
                # Append streaming status to the main status line
                # Re-parse main status to avoid appending multiple times
                base_status = cli_status_message.split(" | ")[0]
                cli_status_message = f"{base_status} | {data}"
                update_cli_input_and_status()

            elif message_type == "current_freq":
                # Update frequency immediately and redraw data display
                new_khz = data
                if new_khz != cli_current_freq_khz:
                    cli_current_freq_khz = new_khz
                    format_and_display_data(None) # Redraw with new frequency

            elif message_type == "error":
                # Display error message in status line
                cli_status_message = f"ERROR: {data}"
                update_cli_input_and_status()
                # Controller signals shutdown via app_running for fatal errors

            elif message_type == "closed":
                # Controller has fully stopped
                cli_status_message = "Status: Controller stopped."
                update_cli_input_and_status()
                app_running.clear() # Ensure main loop exits
                break # Exit update loop

            # Mark message as processed
            cli_update_queue.task_done()

        except queue.Empty:
            # Timeout occurred, no message received. Loop continues to check app_running.
            continue
        except Exception as e:
            # Catch unexpected errors in the update loop itself
            print(f"\n{CLEAR_LINE}Error in CLI update loop: {e}", flush=True)
            traceback.print_exc()
            app_running.clear() # Signal shutdown on error
            break # Exit loop
    # print("CLI update loop finished.")


# =============================================================================
# CLI Mode Runner
# =============================================================================

def run_cli(args):
    """Sets up and runs the application in Command Line Interface mode."""
    global cli_command_queue, cli_update_queue, cli_asyncio_controller
    global cli_status_message, app_running

    mode_string = "Restream-Only " if args.restream_only else ""
    print(f"Starting {mode_string}CLI Mode...")

    # --- Dependency Check Specific to CLI ---
    if not readchar_available:
        print("Fatal Error: 'readchar' library is required for CLI mode (--cli).")
        print("Install using: pip install readchar")
        sys.exit(1)

    # Note: ffplay/ffmpeg checks are primarily handled by AsyncioController at runtime.
    # Informational checks can be done here if desired, but FileNotFoundError is handled.
    # if not args.restream_only: check_ffplay()
    # if args.stream: check_ffmpeg()

    # --- Setup Communication Queues ---
    cli_command_queue = queue.Queue() # UI -> Controller
    cli_update_queue = queue.Queue()  # Controller -> UI

    # --- Parse Server Address and Determine WebSocket URIs ---
    addr_input = args.server_address
    # Address is mandatory for CLI mode (unlike GUI which has an entry field)
    if not addr_input:
        print("Error: Server address is required for CLI mode.")
        print("Usage: python fm-dx-client.py --cli <server_address> [options]")
        sys.exit(1)

    # Default scheme if missing
    if "://" not in addr_input: addr_input = "http://" + addr_input
    try:
        parsed = urlparse(addr_input)
        host = parsed.hostname
        input_scheme = parsed.scheme.lower()
        if not host: raise ValueError("Could not determine hostname.")

        target_ws_scheme = "wss" if input_scheme in ["https", "wss"] else "ws"
        target_port = parsed.port or (443 if target_ws_scheme == "wss" else 80)
        netloc = f"{host}:{target_port}"
        audio_uri = urlunparse((target_ws_scheme, netloc, WEBSOCKET_AUDIO_PATH, "", "", ""))
        text_uri = urlunparse((target_ws_scheme, netloc, WEBSOCKET_TEXT_PATH, "", "", ""))
        print(f"Connecting to: {netloc}")
        # print(f"(Audio: {audio_uri}, Text: {text_uri})") # Debug
    except ValueError as e:
        print(f"Address Error: Invalid server address '{args.server_address}'. {e}")
        sys.exit(1)


    # --- Setup Signal Handling (Ctrl+C, Terminate) ---
    def signal_handler(sig, frame):
        """Handles SIGINT/SIGTERM to initiate graceful shutdown."""
        if app_running.is_set(): # Check if already shutting down
            # Use print with flush and clear line to avoid display corruption
            print(f"\n{CLEAR_LINE}SIGNAL {signal.Signals(sig).name} received. Initiating shutdown...", flush=True)
            app_running.clear() # Signal all loops/threads to stop
            # Wake up command queue listener if blocked
            if cli_command_queue:
                try: cli_command_queue.put_nowait(None)
                except queue.Full: pass
            # Request controller stop (non-blocking)
            if cli_asyncio_controller:
                cli_asyncio_controller.stop()

    # Store original handlers to restore on exit
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    # Register the custom handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


    # --- Setup Terminal for CLI Display ---
    # Hide cursor, Clear screen, Move cursor to top-left
    print(f"{HIDE_CURSOR}\033[2J\033[H", end="", flush=True)

    # --- Start Asyncio Controller ---
    cli_status_message = "Status: Initializing..."
    update_cli_input_and_status() # Show initial status
    cli_asyncio_controller = AsyncioController(
        audio_uri, text_uri, cli_command_queue, cli_update_queue,
        stream_enabled=args.stream,
        is_restream_only=args.restream_only,
        stream_port=args.port
    )
    cli_asyncio_controller.start()

    # --- Start Keyboard Listener Thread ---
    keyboard_thread = threading.Thread(target=_blocking_keyboard_listener, daemon=True, name="CLIKeyboardThread")
    keyboard_thread.start()

    # --- Run Update Loop (blocks in main thread until shutdown) ---
    try:
        cli_update_loop(args) # This function handles updates and checks app_running
    except Exception as e:
         # Catch unexpected errors in the main CLI loop
         print(f"\n{CLEAR_LINE}Fatal error in main CLI execution: {e}", flush=True)
         traceback.print_exc()
    finally:
        # --- Cleanup ---
        print(f"\n{CLEAR_LINE}CLI Mode Shutting Down...", flush=True)
        # Ensure app_running is clear, might already be cleared by signal handler or error
        app_running.clear()
        # Ensure controller is stopped if it was running
        if cli_asyncio_controller and cli_asyncio_controller.is_running():
            # print("CLI Cleanup: Stopping AsyncioController...")
            cli_asyncio_controller.stop() # Request stop
            # Optionally join controller thread? Stop is non-blocking here.
            # Main thread will exit soon anyway.

        # Restore terminal state
        print(f"{SHOW_CURSOR}", end="", flush=True) # Show cursor again
        # Move cursor below the display area to avoid overwriting output on exit
        print(f"\033[{cli_input_line_row + 3};1H", end="")

        # Restore original signal handlers (best effort)
        try: signal.signal(signal.SIGINT, original_sigint)
        except Exception: pass
        try: signal.signal(signal.SIGTERM, original_sigterm)
        except Exception: pass

        print(f"{CLEAR_LINE}CLI Exit.", flush=True)


# =============================================================================
# GUI Mode Runner
# =============================================================================

def run_gui(args):
    """Sets up and runs the application in Graphical User Interface mode."""
    # Ensure Tkinter is available before proceeding
    if not tkinter_available:
        print("Fatal Error: Tkinter is required for GUI mode, but it's not available.")
        print("Please ensure Tkinter is installed for your Python environment.")
        print("(e.g., 'sudo apt-get install python3-tk' on Debian/Ubuntu)")
        print("Alternatively, run with --cli for the command-line mode.")
        sys.exit(1)

    mode_string = "Restream-Only " if args.restream_only else ""
    print(f"Starting {mode_string}GUI Mode...")

    # Setup shared queues for communication between GUI and Controller
    gui_command_queue = queue.Queue()
    gui_update_queue = queue.Queue()

    app = None # Hold reference to the Tkinter app instance
    try:
        # Create the main application window instance
        app = RadioApp(
            initial_address=args.server_address, # Pre-fill address if provided
            stream_enabled=args.stream,          # Pass streaming flag
            is_restream_only=args.restream_only, # Pass restream-only flag
            cmd_queue=gui_command_queue,         # Pass command queue
            upd_queue=gui_update_queue,          # Pass update queue
            cli_args=args                        # Pass all args for reference
        )
        # Start the Tkinter main event loop (blocks until window closed)
        app.mainloop()
        # print("GUI mainloop finished.") # Executes after window is destroyed

    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully if running GUI from console
        print("\nKeyboardInterrupt received during GUI execution.")
        if app and app.winfo_exists():
            app.on_close() # Trigger the GUI's shutdown procedure
    except Exception as e:
        # Catch any other unexpected errors at the GUI level
        print(f"\nFatal GUI-level error: {e}")
        traceback.print_exc()
        # Attempt to clean up GUI if an error occurred
        if app and app.winfo_exists():
             app.on_close()
    finally:
        # Ensure the global shutdown flag is cleared when GUI exits
        app_running.clear()
        print("Exiting GUI application.")


# =============================================================================
# Main Execution Block
# =============================================================================

def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="WebSocket Radio Client with RDS Display, optional ffplay Audio Output, and optional AAC Restreaming (GUI or CLI).",
        epilog="Connects to FM-DX WebSocket sources. Developed by antonioag95. Version 1.0.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Show defaults in help
    )
    parser.add_argument(
        "server_address",
        nargs='?', # Make address optional for GUI mode
        default=None,
        help="Required. Server address (e.g., 'example.com:8080' or 'http://host:port'). "
             "Scheme (http/https) determines WebSocket protocol (ws/wss)."
    )
    parser.add_argument(
        "-s", "--stream",
        action="store_true",
        default=STREAM_ENABLED_DEFAULT,
        help=f"Enable AAC ({STREAM_AAC_BITRATE}) restreaming over HTTP. "
             f"Requires 'ffmpeg' and 'aiohttp'. Stream available at path '{STREAM_PATH}'."
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=STREAM_PORT,
        metavar="PORT",
        help="Port number for the AAC restreaming HTTP server."
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in Command Line Interface (CLI) mode instead of the default GUI mode. "
             "Requires the 'readchar' library."
    )
    parser.add_argument(
        "--restream-only",
        action="store_true",
        help="Run in restream-only mode (disables local ffplay audio output). "
             "Automatically enables AAC streaming (-s if not already specified). "
             "Requires 'ffmpeg' and 'aiohttp'."
    )
    args = parser.parse_args()

    # --- Mode Logic ---
    # If restream-only is specified, implicitly enable streaming
    if args.restream_only:
        if not args.stream: # Only print info if -s wasn't explicitly given
            # print("Info: --restream-only specified, automatically enabling AAC streaming (-s).")
            pass
        args.stream = True # Ensure streaming is active in this mode

    # Address is mandatory for CLI mode
    if args.cli and args.server_address is None:
        parser.error("the following arguments are required for --cli mode: server_address")

    # --- Initial Dependency Checks (Informational / Early Exit) ---
    # These provide immediate feedback but the core logic handles missing deps at runtime too.
    # Check ffplay only if local audio might be used
    if not args.restream_only:
        check_ffplay(show_error_popup=(not args.cli)) # Show popup only if GUI mode might run
    # Check streaming deps only if streaming is enabled
    if args.stream:
        check_ffmpeg(show_error_popup=(not args.cli))
        if not aiohttp_available:
             print("Info: 'aiohttp' not found. Streaming (-s/--restream-only) will be disabled.")
             # Update args state to reflect disabled streaming if dep missing
             args.stream = False
             if args.restream_only:
                 print("Warning: --restream-only requires aiohttp. Running without streaming.")
                 # Restream-only without streaming doesn't make much sense, but let it run.



    # --- Select and Run Mode ---
    if args.cli:
        run_cli(args)
    else:
        # Run GUI (default mode)
        # run_gui handles the check for tkinter_available internally
        run_gui(args)

    # --- End of Script ---
    # print("Main script execution finished.") # Usually indicates clean exit