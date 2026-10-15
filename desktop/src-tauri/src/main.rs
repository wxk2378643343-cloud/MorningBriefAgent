use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct LocalApiProcess(Mutex<Option<Child>>);

fn start_local_api() -> Result<Child, String> {
    let python = std::env::var("MORNINGBRIEF_PYTHON")
        .unwrap_or_else(|_| "python".to_string());
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("scripts")
        .join("run_local_api.py");
    Command::new(python)
        .arg(script)
        .arg("--port")
        .arg("8765")
        .spawn()
        .map_err(|error| format!("failed to start local api: {error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let child = start_local_api()?;
            app.manage(LocalApiProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building MorningBrief")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<LocalApiProcess>() {
                    if let Ok(mut child) = state.0.lock() {
                        if let Some(process) = child.as_mut() {
                            let _ = process.kill();
                        }
                    }
                }
            }
        });
}

fn main() {
    run();
}
