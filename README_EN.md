# LiveSubtitle

[简体中文](README.md) | **English**

Desktop real-time audio-to-subtitle (CC subtitles) app.

Real-time capture of the audio your computer is playing, transcribed locally
via a streaming ASR (sherpa-onnx X-ASR bilingual zh-en with punctuation), and
overlaid on a **transparent, draggable, always-on-top** subtitle window.
Fully offline — audio never leaves your machine.

```
System audio being played
        │  WASAPI Loopback (soundcard capture, 16 kHz mono)
        ▼
  Capture thread ──bounded queue (drop-oldest)──▶ ASR thread (X-ASR 160 ms streaming)
        │                                              │ partial (backpressured) / final (sync callback)
        ▼                                              ▼
  Transparent subtitle overlay (PySide6)    ──optional──▶ Transcript recording (timeline + fix + SRT/TXT)
```

## ✨ Features

- ✅ **Real-time CC subtitles (core)**: `F9` toggles subtitles on/off anytime; transparent background,
  black outline, adjustable translucent per-line background bar
- ✅ **Local streaming ASR**: X-ASR 160 ms Zipformer Transducer (zh-en + punctuation, int8, ~134 MB),
  real-time on CPU (~3–4 cores)
- ✅ **Smart sentence breaking**: energy VAD (commit after 0.5 s silence) + sherpa endpoint rules +
  8 s max-utterance force reset (prevents stream-state growth)
- ✅ **Stability architecture**: bounded queue (no backlog), pure-Python threads, partial backpressure
  (event queue never grows; auto-recovery on timeout), final sync callbacks (no lost sentences even
  when the main thread is busy), capture watchdog (auto-restart capture if a device like a Bluetooth
  speaker degrades during long WASAPI loopback), window-resize debounce; verified with a **30-minute
  full-chain real-capture test (max 2 s subtitle gap)**
- ✅ **Narrow-window friendly**: long sentences keep the **newest lines** when wrapping past the limit
  (subtitles always show the latest content at any window width)
- ✅ **Transcript recording (optional)**: `F10` starts/stops recording; each sentence gets a
  `[mm.ss.mmm]` timeline; rule-based fix compresses streaming duplication ("所所所以以"→"所以",
  without harming real reduplications like 天天/人人); auto-saves **SRT + TXT** to the `recordings`
  folder (non-blocking notification); optional LLM fix (ollama)
- ✅ **System tray**: resident at startup (zero CPU); context menu is state-synced
  (shows "Hide subtitles" when on), with **Options… (preview editor**: shows sample sentences without
  loading the model; close the window to save) and Quit; closing the subtitle window hides to tray
- ✅ **Customization**: right-click menu — font/size (sliders), 8 color schemes + 3-color free mixing,
  window width/height, background opacity, outline width, listening-device hot switch; all settings
  persist to `config.ini`
- ✅ **Custom icon**: uses `logo.svg` (tray + exe icon; replaceable)

## 🔧 Setup

### Requirements

- Windows 10/11 (x64)
- Python **3.10 ~ 3.13** (developed on 3.13)
- No GPU required (CPU inference)

### Install

```bat
:: 1. Create venv and install deps
python -m venv --without-pip .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2. Download model (~134 MB, auto-download on first run; resumable)
.venv\Scripts\python.exe scripts\download_model.py

:: 3. Run
run.bat                          :: tray resident (F9 subtitles, F10 record)
run.bat --demo                   :: demo mode (no audio/model, simulated subtitles)
```

> If `python -m venv`'s ensurepip fails (sandboxed/corporate env), use `--without-pip`
> and bootstrap pip with `get-pip.py`.

### Selftests

```bat
run.bat --selftest-asr       :: offline decode of the model's test wavs (exit 0 = OK)
run.bat --selftest-gui       :: build menu/hotkeys/icon then exit (exit 0 = OK)
run.bat --selftest-capture   :: 5 s loopback level print
.venv\Scripts\python.exe scripts\e2e_test.py   :: end-to-end: play speech -> loopback -> live ASR
```

## 🚀 Usage

| Key | Action |
|---|---|
| **F9** | Toggle live subtitles (core, anytime) |
| **F10** | Toggle transcript recording (auto-saves SRT+TXT) |
| Tray icon | Right-click: show/hide subtitles (state-synced), start/stop record, Options… (preview editor), Quit; double-click shows the window |
| Subtitle window right-click | show/hide subtitles, record toggle, listening device, width/height/opacity/outline sliders, color schemes, font/size, exit |

Hotkeys are configurable in `config.ini` (`hotkey_start` / `hotkey_stop`, Windows VK codes).

## 📦 Build EXE

```bat
:: One-click (installs PyInstaller, builds, copies model + icon)
scripts\build_exe.bat

:: or manual:
.venv\Scripts\python.exe -m pip install pyinstaller pillow
.venv\Scripts\python.exe scripts\make_icon.py        :: generate logo.png/ico
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed ^
    --name LiveSubtitle --icon logo.ico --paths src ^
    --collect-all sherpa_onnx --collect-all sherpa_onnx_core --collect-all soundcard ^
    --add-data "logo.svg;." build_entry.py
xcopy /E /I /Y models dist\models
```

Output `dist\LiveSubtitle.exe`: single-file, no console. `dist\models` is the model
(auto-downloaded if missing).

## 📁 Project Layout

```
LiveSubtitle/
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
    ├── main.py              entry / args / exception fallback
    ├── config.py            config + color schemes + persistence
    ├── models.py            model discovery/download
    ├── audio.py             WASAPI loopback capture (bounded queue + watchdog)
    ├── asr.py               sherpa-onnx streaming + VAD + max-utterance guard + backpressure
    ├── recording.py         transcript session (timeline/fix/export)
    ├── subtitle_window.py   transparent subtitle window (wrap/colors/menu)
    ├── pipeline.py          thread assembly (backpressure/sync callbacks)
    ├── app.py               tray resident/hotkeys/state machine
    └── selftest.py          no-GUI selftests
```

## ⚠️ Known Limitations

- Loopback captures the default output device; use right-click "监听设备" or `--device <substr>` for others
- Only captures system playback (not the microphone, unless "Stereo Mix" is enabled)
- int8 streaming model: occasional recognition errors on short utterances; occasional duplication on
  long sentences (the fix rule compresses these)
- GPU acceleration requires an official CUDA-enabled wheel (current pip package is CPU-only; CPU is already real-time)

## 🗺️ Roadmap

- [ ] Local LLM sentence reorder/fix (e.g. Qwen2.5-4B via ollama)
- [ ] GPU (CUDA) inference (when official wheel lands)
- [ ] Transcript history viewer
- [ ] MSI installer
