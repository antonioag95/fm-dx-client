# FM-DX Client

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A Python-based client for [FM-DX Webserver](https://github.com/NoobishSVK/fm-dx-webserver) sources. It displays FM Radio Data System (RDS) metadata, optionally plays the received MP3 audio locally using `ffplay`, and can optionally re-encode and restream the audio as AAC over HTTP using `ffmpeg` and `aiohttp`.

The client offers both a graphical user interface (GUI) using Tkinter (default) and a command-line interface (CLI) using `readchar`.

<p align="center">
  <img src="gui_screenshot.png" width="400" title="GUI Screenshot">
</p>

<p align="center">
  <img src="cli_screenshot.png" width="400" alt="CLI Screenshot">
</p>

## Features

*   **WebSocket Client:** Connects to separate text (JSON) and audio (MP3) WebSocket endpoints. Handles automatic reconnection attempts.
*   **Rich RDS Display:** Parses and displays:
    *   Program Service name (PS)
    *   Program Identification code (PI)
    *   Program Type (PTY) name
    *   RadioText (RT/RT+) messages
    *   Traffic Program (TP) and Traffic Announcement (TA) flags
    *   Music/Speech (MS) flag
    *   Stereo/Mono indicator
    *   Transmitter Information (Name, City, Country/ITU, ERP, Polarity, Distance, Azimuth)
    *   Signal Strength (Current and Peak, assumes dBf unit)
    *   Active listener count (if provided)
*   **Local Audio Playback:** Pipes the received MP3 audio stream to `ffplay` for local listening (can be disabled).
*   **AAC Restreaming:** Optionally re-encodes MP3 to AAC in real-time using `ffmpeg` and serves it via a local HTTP server (`aiohttp`), allowing other devices on the network to listen.
*   **Dual Interface:**
    *   **GUI Mode (Default):** User-friendly graphical interface using Tkinter.
    *   **CLI Mode (`--cli`):** Terminal-based interface suitable for servers or headless operation.
*   **Restream-Only Mode (`--restream-only`):** Disables local `ffplay` audio output, focusing solely on receiving data and AAC restreaming. Automatically enables the `--stream` flag.

## Requirements

### Python and Libraries

*   **Python 3.x**
*   **Core Libraries:**
    *   `websockets`: For WebSocket communication.
*   **GUI Mode Library:**
    *   `tkinter`: Usually included with standard Python installations, but might need separate installation on some systems (e.g., `sudo apt-get install python3-tk` on Debian/Ubuntu). Required only for the default GUI mode. Ensure this is installed *before* installing the client if you intend to use the GUI.
*   **CLI Mode Library:**
    *   `readchar`: For capturing keyboard input in the terminal. Required only for CLI mode (`--cli`).
*   **Streaming Libraries:**
    *   `aiohttp`: For the asynchronous HTTP server used for AAC streaming. Required only if using the `--stream` or `--restream-only` flags.

    *Note: These libraries will typically be installed automatically when following the installation instructions below (using `pipx install ./fm-dx-client`, `pip install .` or `pip install -r requirements.txt`).*

### External Programs

*   **`ffplay`:** Required for **local audio playback** (i.e., when *not* using `--restream-only`). Part of the FFmpeg suite.
*   **`ffmpeg`:** Required for **AAC restreaming** (i.e., when using `--stream` or `--restream-only`). Part of the FFmpeg suite.

You need to install FFmpeg (which includes both `ffmpeg` and `ffplay`) and ensure both commands are available in your system's PATH. Installation methods vary by OS:

*   **Debian/Ubuntu:** `sudo apt update && sudo apt install ffmpeg`
*   **macOS (Homebrew):** `brew install ffmpeg` (ensure Python 3 and optionally python-tk are also installed: `brew install python python-tk`)
*   **Windows:** Download from the [official FFmpeg website](https://ffmpeg.org/download.html), extract the archive, and add the `bin` directory to your system's PATH environment variable.

## Installation

Choose one of the following methods:

### Method 1: Install using `pipx` (Recommended)

`pipx` installs Python applications into isolated environments, making them available as commands directly in your shell without interfering with other Python projects. This is the preferred method for running the client as a standalone application.

1.  **Install pipx:** Follow the official [pipx installation guide](https://pypa.github.io/pipx/installation/).
2.  **Clone the repository:**
    ```bash
    git clone https://github.com/antonioag95/fm-dx-client.git
    ```
3.  **Install with pipx:**
    ```bash
    # Install from the cloned directory
    pipx install ./fm-dx-client
    ```
    This will create a command, likely named `fm-dx-client` (check pipx output), that you can run directly from your terminal.
4.  **(Optional but recommended for GUI):** Ensure `tkinter` is installed if needed for your OS (see Requirements).

### Method 2: Install using `pip` (System/Virtual Environment)

This method installs the package into your Python environment (system-wide or virtual environment) and makes it runnable using `python -m fm_dx_client`. It automatically handles dependencies listed in `setup.py`.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/antonioag95/fm-dx-client.git
    cd fm-dx-client
    ```
2.  **Install the package:**
    ```bash
    # Install into your current Python environment
    pip install .

    ```
3.  **(Optional but recommended for GUI):** Ensure `tkinter` is installed if needed for your OS (see Requirements).

### Method 3: Run Directly from Cloned Source

This method is suitable for testing or development without installing the package formally.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/antonioag95/fm-dx-client.git
    cd fm-dx-client
    ```
2.  **Install dependencies:**
    ```bash
    # Create a virtual environment (optional but recommended)
    # python -m venv venv
    # source venv/bin/activate  # On Windows use `venv\Scripts\activate`

    # Install required libraries
    pip install -r requirements.txt
    ```
3.  **(Optional but recommended for GUI):** Ensure `tkinter` is installed if needed for your OS (see Requirements).
4.  **Run the script:** Execute using `python fm_dx_client/fm_dx_client.py ...` or `python -m fm_dx_client ...` from the project's root directory (`fm-dx-client`).

## Usage

How you run the client depends on the installation method used.

### Server Address Format

The client needs the address of the FM-DX Webserver WebSocket source.
*   Format: `hostname:port` (e.g., `yourserver.com:8080`)
*   You can optionally prefix with `http://` or `https://`. The scheme determines the WebSocket protocol (`ws://` or `wss://`) used for the connection. If no scheme is provided, `http://` (`ws://`) is assumed.

### GUI Mode (Default)

Run the client without the `--cli` flag. You can optionally provide the server address as an argument to pre-fill the address bar.

*   **If installed via `pipx` (Method 1):**
    ```bash
    # Launch the GUI (enter address manually)
    fm-dx-client

    # Launch the GUI and pre-fill the address (will auto-connect)
    fm-dx-client yourserver.com:8080 [options]
    ```
    *(Note: The exact command might differ slightly based on `pipx` installation specifics. Check the output of `pipx install`)*

*   **If installed via `pip` (Method 2) or Running Directly (Method 3):**
    ```bash
    # Launch the GUI (enter address manually)
    python -m fm_dx_client

    # Launch the GUI and pre-fill the address (will auto-connect)
    python -m fm_dx_client yourserver.com:8080 [options]
    ```

**Interaction:**
*   Enter the server address in the top entry field.
*   Click **Connect**.
*   Use the **<** / **>** buttons or enter a frequency (in MHz) and click **Tune** (or press Enter in the frequency field) to change stations.
*   Keyboard shortcuts for tuning: Left/PageDown (tune down), Right/PageUp (tune up).
*   Click **Disconnect** to stop.
*   The status bar shows connection status, listener count, and streaming status (if enabled).

### CLI Mode (`--cli`)

Run the client with the `--cli` flag. The server address is **required** as an argument in this mode.

*   **If installed via `pipx` (Method 1):**
    ```bash
    fm-dx-client --cli yourserver.com:8080 [options]
    ```
    *(Note: The exact command might differ slightly based on `pipx` installation specifics. Check the output of `pipx install`)*

*   **If installed via `pip` (Method 2) or Running Directly (Method 3):**
    ```bash
    python -m fm_dx_client --cli yourserver.com:8080 [options]
    ```

**Interaction:**
*   The terminal will display the current station info, RDS data, signal strength, etc.
*   A prompt `Tune [MHz] (...)` appears at the bottom.
*   **Tuning:**
    *   Type a frequency (e.g., `90.2`) and press **Enter** to tune.
    *   Use **Up/Right Arrow** keys to tune up by the step (default 100 kHz).
    *   Use **Down/Left Arrow** keys to tune down.
*   **Input Control:**
    *   **Backspace:** Delete the last character in the frequency input.
    *   **Esc:** Clear the frequency input buffer.
*   **Refresh:** Press **Enter** when the input buffer is empty to refresh the display with the latest data.
*   **Exit:** Press **Ctrl+C** to quit the application.


### Command-Line Options

| Argument/Option         | Shorthand | Description                                                                                                                                                           | Default                | Required        |
| :---------------------- | :-------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------- | :-------------- |
| `server_address`        |           | Server address and port (e.g., `example.com:8080`). Scheme optional.                                                                                                | `None`                 | **Yes (for CLI)** |
| `--stream`              | `-s`      | Enable AAC (`96k`) restreaming via HTTP. Requires `ffmpeg` and `aiohttp`. Stream accessible at `http://<your-ip>:<port>/stream.aac`.                                   | Disabled               | No              |
| `--port PORT`           | `-p PORT` | Port number for the AAC restreaming HTTP server.                                                                                                                      | `8080`                 | No              |
| `--cli`                 |           | Run in Command Line Interface (CLI) mode instead of GUI. Requires `readchar`.                                                                                       | GUI Mode               | No              |
| `--restream-only`       |           | Run without local `ffplay` audio output. Focuses on data reception and restreaming. Implies `--stream`. Requires `ffmpeg` and `aiohttp`.                            | Disabled               | No              |

## AAC Restreaming (`--stream` / `--restream-only`)

When enabled, the client performs the following:
1.  Receives the MP3 audio stream from the WebSocket server.
2.  Pipes the MP3 data to an `ffmpeg` process.
3.  `ffmpeg` re-encodes the audio from MP3 to AAC (default bitrate `96k`) in ADTS format suitable for streaming.
4.  An `aiohttp` web server runs locally on the specified port (default `8080`).
5.  The server makes the real-time AAC stream available at the path `/stream.aac`.

You can listen to this AAC stream using players like VLC, foobar2000, or web browsers by opening the URL:

`http://<your-local-ip>:<port>/stream.aac`

Replace `<your-local-ip>` with the IP address of the machine running the client on your local network, and `<port>` with the chosen streaming port (default `8080`).

## How It Works Briefly

1.  **WebSocket Connections:** Two persistent WebSocket connections are established with the server:
    *   `/text`: Receives JSON-formatted RDS and metadata updates.
    *   `/audio`: Receives raw MP3 audio data chunks.
2.  **Data Processing:** Incoming JSON is parsed to update RDS fields.
3.  **Audio Handling:**
    *   **Local Playback:** If enabled, MP3 chunks are piped directly to `ffplay`'s standard input.
    *   **Restreaming:** If enabled, MP3 chunks are piped to `ffmpeg`'s standard input. `ffmpeg` outputs AAC chunks via its standard output.
4.  **AAC Server:** If restreaming, an `aiohttp` server reads AAC chunks from `ffmpeg`'s output and sends them to connected HTTP clients requesting the `/stream.aac` path.
5.  **Interface:** Either the Tkinter GUI or the CLI handles user input (tuning commands) and displays the processed RDS data and status updates received from the backend controller. Communication between the UI thread and the backend `asyncio` controller happens via thread-safe queues.

## License

This project is licensed under the **GNU General Public License v3.0**. See the `LICENSE` file for full details.

## Author

*   Original work by **antonioag95**.

## Acknowledgements

*   This client is designed to work with the [fm-dx-webserver](https://github.com/NoobishSVK/fm-dx-webserver) project.

## Contributing / Bug Reports

Feel free to open an issue on the GitHub repository for bug reports, feature requests, or questions. Pull requests are also welcome.