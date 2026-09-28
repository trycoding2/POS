use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

/// Spawns the bundled FastAPI backend (the `backend/` folder shipped next to
/// the app via Tauri resources) and keeps its handle so it is terminated when
/// the main window closes. The React UI connects to http://127.0.0.1:8000.
struct Backend(Mutex<Option<Child>>);

fn spawn_backend(backend_dir: &std::path::Path) -> Option<Child> {
    let venv_python = if cfg!(windows) {
        backend_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        backend_dir.join(".venv").join("bin").join("python")
    };
    let python: &std::ffi::OsStr = if venv_python.exists() {
        venv_python.as_os_str()
    } else {
        // Dev machines where a venv lives elsewhere — fall back to system python.
        "python".as_ref()
    };
    Command::new(python)
        .current_dir(backend_dir)
        .args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()
}

fn start_backend(app: &tauri::AppHandle) -> Option<Child> {
    // 1) Bundled resource (production install): <resources>/backend
    if let Ok(dir) = app.path().resource_dir() {
        let bundled = dir.join("backend");
        if bundled.join("app").join("main.py").exists() {
            return spawn_backend(&bundled);
        }
    }
    // 2) Development layout: repo checkout with ../backend next to frontend/
    let dev = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../backend");
    if dev.join("app").join("main.py").exists() {
        return spawn_backend(&dev);
    }
    None // Backend already running externally — the UI will still connect.
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let child = start_backend(&app.handle());
            app.manage(Backend(Mutex::new(child)));
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<Backend>() {
                    if let Some(mut c) = state.0.lock().ok().and_then(|mut g| g.take()) {
                        let _ = c.kill();
                        let _ = c.wait();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Karyana Manager");
}
