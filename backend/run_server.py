"""Kirana Manager — single-file EXE entry point (built by build_windows.bat).

On startup:
  * frozen (PyInstaller): data lives in a `data/` folder next to the .exe,
    and the built React frontend is bundled inside the executable.
  * dev: plain `python run_server.py` also works from the backend folder.

Then serves API + frontend at http://127.0.0.1:8000 and opens the browser.
"""
import os
import sys
import threading
import webbrowser


def main() -> None:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        os.environ["KARYANA_DATA_DIR"] = os.path.join(base, "data")
    import uvicorn
    from app.main import app

    url = "http://127.0.0.1:8000"
    print(f"Kirana Manager starting at {url}  (close this window to stop)")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
