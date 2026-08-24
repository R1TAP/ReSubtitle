# LiveLocalSubtitle

[简体中文](README.md) | **English**

Desktop real-time audio-to-subtitle (CC subtitles) app.

Real-time capture of the audio your computer is playing, transcribed locally via a streaming ASR, and overlaid on a **fully customizable, transparent, draggable, always-on-top** subtitle window.

Simple, lightweight, and fluid — just like CC subtitles, but for everything you play.

```
Audio being played
      │
      │  WASAPI Loopback
      ▼
  Capture ────▶ Bounded Queue ────▶ ASR
      │                │
      │                │ partial/final
      ▼                ▼
   Live Subtitles    Optional ────▶ Transcript Recording (timeline + auto-fix + SRT/TXT export)
```

## ✨ Features

- **Live Subtitles**: Toggle on/off anytime with a single hotkey. Always ready when you need it.
- **Local Streaming ASR**: Powered by X-ASR 160ms Zipformer Transducer — lightweight, fluid, and runs unnoticed.
- **Auto-Fix (Beta)**: Local small-model-based real-time correction — reliable and accurate.
- **Stable Architecture**:
  - Bounded queue scheduling
  - Pure-Python threading
  - Partial backpressure
  - Final sync callbacks
  - **Watchdog** for capture auto-recovery
- **Transcript Recording**: Generate subtitle files for videos with one keystroke — precise per-sentence timestamps, auto-fix via local small model.
- **System Tray Resident**: Starts quietly in the background, lightweight architecture, ready when you need it.
- **Full Customization**: From fonts to colors — make the CC window truly yours, fresh and always by your side.

## 🔧 Setup

### Requirements

- Windows **10/11** (x64)
- Python **3**

### ⚙️ Install

```
:: 1. Create environment and install deps
python -m venv --without-pip .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2. Download model (~134 MB, auto-download on first run; resumable)
.venv\Scripts\python.exe scripts\download_model.py

:: 3. Run
run.bat
```

> If `ensurepip` fails, run `.venv\Scripts\python.exe get-pip.py` after `--without-pip`.

### Selftests (for troubleshooting)

```
run.bat --selftest-asr       :: offline decode of test wavs (exit 0 = OK)
run.bat --selftest-gui       :: build GUI components then exit (exit 0 = OK)
run.bat --selftest-capture   :: 5s loopback level print
.venv\Scripts\python.exe scripts\e2e_test.py   :: end-to-end: play -> loopback -> live ASR
```

## 🚀 Usage

| Key | Action |
|---|---|
| **F9** | Toggle live subtitles (core, anytime) |
| **F10** | Toggle transcript recording (auto-saves SRT+TXT) |
| Tray icon | Show/hide subtitles, start/stop recording, Options (preview editor), Quit |
| Subtitle window | Show/hide subtitles, start/stop recording, select listening device, customization, Quit |

> Hotkeys can be changed in `config.ini` (`hotkey_start` / `hotkey_stop`, Windows VK codes).

## 📦 Build EXE

The program is open-source — feel free to modify and repack.

```
:: One-click build
scripts\build_exe.bat

:: Or manually:
.venv\Scripts\python.exe -m pip install pyinstaller pillow
.venv\Scripts\python.exe scripts\make_icon.py
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed ^
    --name LiveLocalSubtitle --icon logo.ico --paths src ^
    --collect-all sherpa_onnx --collect-all sherpa_onnx_core --collect-all soundcard ^
    --add-data "logo.svg;." build_entry.py
xcopy /E /I /Y models dist\models
```

## 📁 Project Layout

```
LiveLocalSubtitle/
├── run.bat / run.ps1        launchers
├── requirements.txt
├── build_entry.py           PyInstaller entry
├── logo.svg                 app icon (replaceable)
├── scripts/
│   ├── download_model.py    model download (resumable)
│   ├── e2e_test.py          end-to-end selftest
│   ├── make_icon.py         SVG -> PNG/ICO
│   └── build_exe.bat        one-click build
└── src/livesub/
    ├── main.py              program entry
    ├── config.py            config + persistence
    ├── models.py            model discovery/download
    ├── audio.py             WASAPI capture
    ├── asr.py               streaming ASR/VAD/sentence guard
    ├── recording.py         transcript session
    ├── subtitle_window.py   subtitle window
    ├── pipeline.py          thread optimization
    ├── app.py               tray resident + state machine
    └── selftest.py          selftests
```

## 🗺️ Roadmap

- [ ] Local LLM sentence reorder/fix
- [ ] GPU (CUDA) inference
- [ ] Transcript history viewer
- [ ] Adaptive layout optimization
- [ ] MSI installer