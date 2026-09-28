# Building the desktop installer

This folder contains a complete Tauri 2 shell (config, Rust source, capabilities).
The current development sandbox has **no Rust toolchain**, so the final `.exe` /
`.deb` compile cannot happen here — it is one command on any build machine:

```bash
# prerequisites: Rust (rustup.rs), Node 20+, platform webkit deps on Linux
# (Debian/Ubuntu: libwebkit2gtk-4.1-dev build-essential curl wget file libssl-dev)
cd frontend
npm install                # installs @tauri-apps/cli
npx tauri build            # or: npm run desktop:build
```

Output installers appear in `src-tauri/target/release/bundle/`:
Windows NSIS `.exe`, Linux `.deb` / `.rpm` / `.AppImage`.

What the shell does at runtime (`src/lib.rs`):
1. Launches the bundled FastAPI backend (`backend/` shipped as a Tauri resource;
   create its venv with `python -m venv .venv && pip install -r requirements.txt`
   before packaging, or let it fall back to system Python / an already-running
   server).
2. Opens the WebView on the built React UI (`dist/`).
3. Kills the backend process when the window closes.

Icons: run `npx tauri icon path/to/logo.png` once to generate `src-tauri/icons/`.
