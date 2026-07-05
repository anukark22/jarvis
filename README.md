# Jarvis

A small always-on-top floating desktop widget: a glowing orb that sits in the
corner of your screen, expands into a chat panel when you click it (or say
its wake word), and talks back. Built with PySide6 — this is a real native
app, not a browser page.

## What it actually does

- Floating, frameless, always-on-top orb (idle / standby / listening /
  thinking / speaking states, each with its own color and animation)
- Click the orb to expand into a chat panel; drag it anywhere on screen
- Text or voice input (mic button, or continuous wake-word mode — say
  "Jarvis" and it starts listening automatically)
- Spoken replies via offline TTS (pyttsx3)
- Lives in the system tray when the window is closed — right-click the tray
  icon to reopen it, set your API key, or quit
- Talks to Claude via your own Anthropic API key

## What it does NOT do (yet)

This is the chat-companion layer only. It does **not** control your OS,
open apps, manage files, browse the web, or see your screen — that's a
meaningfully bigger and riskier scope (safe execution, permission prompts,
sandboxing, audit logging) that's worth building deliberately and
incrementally on top of this, not bolted on all at once. `claude_client.py`
is the one place you'd wire in real tools/function-calling later.

## Setup

```bash
pip install -r requirements.txt
```

**Linux only** — SpeechRecognition's microphone support needs PortAudio's
dev headers before `pyaudio` will build:
```bash
sudo apt install portaudio19-dev   # Debian/Ubuntu
pip install pyaudio
```
On macOS: `brew install portaudio` first. On Windows, `pip install pyaudio`
usually works directly (or grab a prebuilt wheel if it doesn't).

## Run

```bash
python main.py
```

On first launch you'll be asked for your Anthropic API key (get one at
https://console.anthropic.com). It's saved to `~/.jarvis/config.json` so
you won't be asked again. You can also set it via the `ANTHROPIC_API_KEY`
environment variable instead, or change it later from the tray icon menu.

## Notes / known limitations

- **Wake word** uses Google's free web speech recognition in a background
  loop while the app is running — it needs an internet connection, and
  isn't a true low-power always-on wake engine like Porcupine/openWakeWord.
  Swapping in one of those later is a reasonable upgrade if you want it
  running 24/7 without the network round-trip per phrase.
- **No native acrylic/blur effect** — the "glass" look is a semi-transparent
  fill, not a real OS-level blur (that requires platform-specific code per
  OS). Looks good regardless; just flagging what's simulated vs. native.
- **System tray behavior** (hide-on-close, no taskbar entry) works most
  reliably on Windows and macOS; Linux behavior varies by desktop
  environment/compositor.
- Voice recognition (`recognize_google`) is free but rate-limited and needs
  internet. For fully offline STT, swap in `faster-whisper` in
  `voice_worker.py`.

## File layout

```
main.py            entry point
jarvis_window.py    the floating window: layout, state, event wiring
orb_graphic.py       the custom-painted animated orb
voice_worker.py      background threads for STT / wake-word / TTS
api_worker.py        background thread for the Claude API call
claude_client.py     the actual HTTP call to the Anthropic API
config.py            API key / settings storage (~/.jarvis/config.json)
```
