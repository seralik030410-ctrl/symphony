mod drops;
use drops::{DropStore, DroppedFile};
use std::{
    fs,
    path::PathBuf,
    sync::{Mutex, atomic::{AtomicBool, Ordering}},
    thread,
    time::{Duration, Instant},
};
use tauri::{DragDropEvent, Emitter, Manager};
use tauri_plugin_shell::{process::{CommandChild, CommandEvent}, ShellExt};

const SERVICE_NAME: &str = "Symphony 2.0";
const OPENAI_KEY_ACCOUNT: &str = "openai-compatible-api-key";
const API_ADDRESS: &str = "http://127.0.0.1:8765";
#[derive(Default)]
struct DroppedFiles(Mutex<DropStore>);

struct BackendProcess(Mutex<Option<CommandChild>>);

#[derive(Default)]
struct Lifecycle { ready: AtomicBool, stopped: AtomicBool, exiting: AtomicBool }

#[derive(Default)]
struct StartupMessage(Mutex<Option<String>>);

fn require_main(window: &tauri::WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|_| "Окно недоступно")?;
    if window.label() != "main" || url.as_str() != format!("{API_ADDRESS}/") {
        return Err("Desktop-команды разрешены только главному окну Symphony".into());
    }
    Ok(())
}

fn secret_entry(account: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(SERVICE_NAME, account).map_err(|error| error.to_string())
}

#[tauri::command]
fn has_openai_key(window: tauri::WebviewWindow) -> Result<bool, String> {
    require_main(&window)?;
    match secret_entry(OPENAI_KEY_ACCOUNT)?.get_password() {
        Ok(value) => Ok(!value.is_empty()),
        Err(keyring::Error::NoEntry) => Ok(false),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
fn set_openai_key(window: tauri::WebviewWindow, value: String) -> Result<(), String> {
    require_main(&window)?;
    let value = value.trim();
    if value.is_empty() || value.len() > 4096 {
        return Err("Ключ должен содержать от 1 до 4096 символов".into());
    }
    secret_entry(OPENAI_KEY_ACCOUNT)?
        .set_password(value)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn delete_openai_key(window: tauri::WebviewWindow) -> Result<(), String> {
    require_main(&window)?;
    match secret_entry(OPENAI_KEY_ACCOUNT)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
fn consume_dropped_file(window: tauri::WebviewWindow, token: String, state: tauri::State<'_, DroppedFiles>) -> Result<DroppedFile, String> {
    require_main(&window)?;
    state.0.lock().map_err(|_| "Хранилище drag-and-drop недоступно".to_string())?.consume(&token)
}

fn show_startup_error(app: &tauri::AppHandle, message: &str) {
    if let Ok(mut slot) = app.state::<StartupMessage>().0.lock() { *slot = Some(message.to_owned()); }
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(windows)]
        let url = "http://tauri.localhost/desktop-error.html";
        #[cfg(not(windows))]
        let url = "tauri://localhost/desktop-error.html";
        let _ = window.navigate(url.parse().unwrap());
        let _ = window.show();
    }
}

fn data_paths(app: &tauri::App) -> Result<(PathBuf, PathBuf, PathBuf), Box<dyn std::error::Error>> {
    let root = app.path().app_data_dir()?;
    fs::create_dir_all(&root)?;
    Ok((root.join("symphony.db"), root.join("workspaces"), root.join("skills")))
}

fn start_backend(app: &tauri::App) -> Result<CommandChild, Box<dyn std::error::Error>> {
    let (database, workspaces, skills) = data_paths(app)?;
    let mut command = app
        .shell()
        .sidecar("symphony-backend")?
        .env("SYMPHONY_HOST", "127.0.0.1")
        .env("SYMPHONY_PORT", "8765")
        .env("SYMPHONY_DESKTOP", "1")
        .env("SYMPHONY_DATABASE_PATH", database)
        .env("SYMPHONY_WORKSPACE_ROOT", workspaces)
        .env("SYMPHONY_SKILLS_ROOT", skills)
        .env("SYMPHONY_OPENAI_API_KEY", "");
    // Finder does not inherit the user's interactive shell PATH.
    let inherited = std::env::var_os("PATH").unwrap_or_default();
    let mut paths: Vec<PathBuf> = std::env::split_paths(&inherited).collect();
    #[cfg(target_os = "macos")]
    paths.extend(["/opt/homebrew/bin", "/usr/local/bin", "/Applications/Docker.app/Contents/Resources/bin"].map(PathBuf::from));
    command = command.env("PATH", std::env::join_paths(paths)?);
    let key = match secret_entry(OPENAI_KEY_ACCOUNT)?.get_password() {
        Ok(value) => value,
        Err(keyring::Error::NoEntry) => String::new(),
        Err(_) => return Err("System secret store is locked or unavailable".into()),
    };
    let (mut events, mut child) = command.spawn()?;
    let bootstrap = serde_json::json!({"protocol": 1, "openai_api_key": key});
    if let Err(error) = child.write(format!("{bootstrap}\n").as_bytes()) {
        let _ = child.kill();
        return Err(error.into());
    }
    let handle = app.handle().clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&line) {
                        if value["event"] == "symphony.ready" && value["protocol"] == 1 && value["port"] == 8765
                            && !handle.state::<Lifecycle>().exiting.load(Ordering::SeqCst)
                            && !handle.state::<Lifecycle>().stopped.load(Ordering::SeqCst) {
                            handle.state::<Lifecycle>().ready.store(true, Ordering::SeqCst);
                            if let Some(window) = handle.get_webview_window("main") {
                                let _ = window.navigate(API_ADDRESS.parse().unwrap());
                            }
                        }
                    }
                }
                CommandEvent::Terminated(_) => {
                    handle.state::<Lifecycle>().stopped.store(true, Ordering::SeqCst);
                    if !handle.state::<Lifecycle>().exiting.load(Ordering::SeqCst) {
                        show_startup_error(&handle, "Локальный runtime остановлен. Перезапустите Symphony; проверьте, свободен ли порт 8765.");
                    }
                }
                _ => {} // Raw process output may contain sensitive data; do not forward it.
            }
        }
    });
    Ok(child)
}

fn register_native_drop(app: &tauri::App) {
    let Some(window) = app.get_webview_window("main") else { return; };
    let emitter = window.clone();
    window.on_webview_event(move |event| {
        if let tauri::WebviewEvent::DragDrop(DragDropEvent::Drop { paths, .. }) = event {
            if require_main(&emitter).is_err() { return; }
            if paths.len() > 8 {
                let _ = emitter.emit("symphony://drop-error", "Не больше восьми файлов за одно перетаскивание");
                return;
            }
            let mut payload = Vec::new();
            if let Ok(mut pending) = emitter.state::<DroppedFiles>().0.lock() {
                for path in paths {
                    match pending.register(path) {
                        Ok(file) => payload.push(file),
                        Err(error) => { let _ = emitter.emit("symphony://drop-error", error); }
                    }
                }
            }
            let _ = emitter.emit("symphony://native-file-drop", payload);
        }
    });
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_opener::init())
        .manage(DroppedFiles::default())
        .manage(BackendProcess(Mutex::new(None)))
        .manage(Lifecycle::default())
        .manage(StartupMessage::default())
        .on_page_load(|webview, payload| {
            if payload.url().path() == "/desktop-error.html" {
                if let Ok(slot) = webview.state::<StartupMessage>().0.lock() {
                    if let Some(message) = slot.as_ref() {
                        let encoded = serde_json::to_string(message).unwrap_or_default();
                        let _ = webview.eval(&format!("{{const m=document.getElementById('runtime-message');if(m)m.textContent={encoded};}}"));
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            has_openai_key,
            set_openai_key,
            delete_openai_key,
            consume_dropped_file
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").ok_or("main window is missing")?;
            match start_backend(app) {
                Ok(child) => {
                    if let Ok(mut slot) = app.state::<BackendProcess>().0.lock() {
                        *slot = Some(child);
                    }
                }
                Err(_) => {
                    app.state::<Lifecycle>().stopped.store(true, Ordering::SeqCst);
                    show_startup_error(app.handle(), "Не удалось запустить runtime. Проверьте установку и доступ к системному хранилищу ключей.");
                }
            }
            register_native_drop(app);
            window.show()?;
            let handle = app.handle().clone();
            thread::spawn(move || {
                let start = Instant::now();
                while start.elapsed() < Duration::from_secs(45) {
                    let state = handle.state::<Lifecycle>();
                    if state.ready.load(Ordering::SeqCst) || state.stopped.load(Ordering::SeqCst) || state.exiting.load(Ordering::SeqCst) { return; }
                    thread::sleep(Duration::from_millis(200));
                }
                handle.state::<Lifecycle>().stopped.store(true, Ordering::SeqCst);
                if let Ok(mut slot) = handle.state::<BackendProcess>().0.lock() {
                    if let Some(child) = slot.take() { let _ = child.kill(); }
                }
                show_startup_error(&handle, "Runtime не запустился за 45 секунд. Проверьте установку sidecar, порт 8765 и доступ к каталогу данных.");
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Symphony 2.0")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, code, .. } = event {
                let lifecycle = app.state::<Lifecycle>();
                if lifecycle.exiting.swap(true, Ordering::SeqCst) { return; }
                api.prevent_exit();
                if let Ok(mut slot) = app.state::<BackendProcess>().0.lock() {
                    if let Some(child) = slot.as_mut() { let _ = child.write(b"{\"command\":\"shutdown\"}\n"); }
                }
                let handle = app.clone();
                let exit_code = code.unwrap_or(0);
                thread::spawn(move || {
                    let start = Instant::now();
                    while !handle.state::<Lifecycle>().stopped.load(Ordering::SeqCst) && start.elapsed() < Duration::from_secs(15) {
                        thread::sleep(Duration::from_millis(100));
                    }
                    if let Ok(mut slot) = handle.state::<BackendProcess>().0.lock() {
                        if let Some(child) = slot.take() { let _ = child.kill(); }
                    }
                    handle.exit(exit_code);
                });
            }
        });
}
