use std::io::{Read, Write};
use std::net::{Shutdown, TcpStream};
use std::path::PathBuf;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct LocalApiProcess(Mutex<Option<CommandChild>>);

fn owner_token() -> String {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("{}-{timestamp}", std::process::id())
}

fn health_belongs_to(token: &str) -> bool {
    let Ok(address) = "127.0.0.1:8765".parse() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    if stream
        .write_all(b"GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let _ = stream.shutdown(Shutdown::Write);
    let mut response = String::new();
    stream.read_to_string(&mut response).is_ok()
        && response.contains("\"service\": \"morningbrief-local-api\"")
        && response.contains(&format!("\"owner_token\": \"{token}\""))
}

fn desktop_database_path(app: &tauri::App) -> Result<PathBuf, String> {
    if let Some(path) = std::env::var_os("MORNINGBRIEF_DATABASE") {
        return Ok(PathBuf::from(path));
    }
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("failed to resolve desktop data directory: {error}"))?;
    std::fs::create_dir_all(&data_dir)
        .map_err(|error| format!("failed to create desktop data directory: {error}"))?;
    let database = data_dir.join("app.sqlite3");

    #[cfg(debug_assertions)]
    if !database.exists() {
        let legacy = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("data")
            .join("app.sqlite3");
        if legacy.is_file() {
            std::fs::copy(&legacy, &database)
                .map_err(|error| format!("failed to migrate development database: {error}"))?;
            for suffix in ["-wal", "-shm"] {
                let legacy_companion = PathBuf::from(format!("{}{suffix}", legacy.display()));
                if legacy_companion.is_file() {
                    let database_companion =
                        PathBuf::from(format!("{}{suffix}", database.display()));
                    std::fs::copy(&legacy_companion, &database_companion).map_err(|error| {
                        format!("failed to migrate development database companion: {error}")
                    })?;
                }
            }
        }
    }
    Ok(database)
}

fn start_local_api(app: &tauri::App) -> Result<CommandChild, String> {
    let token = owner_token();
    let database = desktop_database_path(app)?;
    let database_arg = database.to_string_lossy().into_owned();
    let (_events, child) = app
        .shell()
        .sidecar("morningbrief-local-api")
        .map_err(|error| format!("failed to resolve bundled local API: {error}"))?
        .args([
            "--port",
            "8765",
            "--database",
            &database_arg,
            "--owner-token",
            &token,
        ])
        .env("SQLITE_DATABASE_PATH", &database_arg)
        .set_process_group(true)
        .spawn()
        .map_err(|error| format!("failed to start bundled local API: {error}"))?;

    for _ in 0..30 {
        if health_belongs_to(&token) {
            return Ok(child);
        }
        thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    Err("bundled local API did not acquire port 8765; close any stale MorningBrief backend and retry".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let child = start_local_api(app)?;
            app.manage(LocalApiProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building MorningBrief")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<LocalApiProcess>() {
                    if let Ok(mut child) = state.0.lock() {
                        if let Some(process) = child.take() {
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
