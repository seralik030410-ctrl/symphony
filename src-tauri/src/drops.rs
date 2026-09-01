use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use std::{collections::HashMap, fs::{File, OpenOptions}, io::Read, path::Path, time::{Duration, Instant}};

const ALLOWED: &[&str] = &["txt", "md", "xlsx", "csv", "json", "pdf", "docx", "pptx", "png", "jpg", "jpeg", "webp"];
const EXPIRY: Duration = Duration::from_secs(120);

struct SelectedFile { file: File, filename: String, limit: u64, selected: Instant }

#[derive(Default)]
pub struct DropStore { files: HashMap<String, SelectedFile> }

#[derive(Clone, Serialize)]
pub struct NativeDrop { token: String, name: String }

#[derive(Serialize)]
pub struct DroppedFile { filename: String, content_base64: String }

impl DropStore {
    pub fn register(&mut self, path: &Path) -> Result<NativeDrop, String> {
        self.files.retain(|_, item| item.selected.elapsed() < EXPIRY);
        if self.files.len() >= 64 { return Err("Слишком много ожидающих файлов; повторите через две минуты".into()); }
        let metadata = path.symlink_metadata().map_err(|_| "Файл недоступен")?;
        if !metadata.is_file() || metadata.file_type().is_symlink() { return Err("Выберите обычный файл, не папку или ссылку".into()); }
        let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase();
        if !ALLOWED.contains(&ext.as_str()) { return Err("Этот тип файла не поддерживается".into()); }
        let limit = if matches!(ext.as_str(), "png" | "jpg" | "jpeg" | "webp") { 10_000_000 } else { 25_000_000 };
        let mut options = OpenOptions::new();
        options.read(true);
        #[cfg(unix)]
        { use std::os::unix::fs::OpenOptionsExt; options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK); }
        #[cfg(windows)]
        { use std::os::windows::fs::OpenOptionsExt; options.custom_flags(0x00200000); } // OPEN_REPARSE_POINT
        let file = options.open(path).map_err(|_| "Не удалось открыть выбранный файл")?;
        let opened = file.metadata().map_err(|_| "Не удалось прочитать сведения о файле")?;
        if !opened.is_file() || opened.file_type().is_symlink() { return Err("Разрешены только обычные файлы".into()); }
        if opened.len() > limit { return Err(format!("Максимальный размер файла — {} МБ", limit / 1_000_000)); }
        let name = path.file_name().and_then(|s| s.to_str()).ok_or("Некорректное имя файла")?.to_owned();
        let token = uuid::Uuid::new_v4().to_string();
        // Keep the OS-selected handle, not a path that JavaScript could replace.
        self.files.insert(token.clone(), SelectedFile { file, filename: name.clone(), limit, selected: Instant::now() });
        Ok(NativeDrop { token, name })
    }

    pub fn consume(&mut self, token: &str) -> Result<DroppedFile, String> {
        let selected = self.files.remove(token).ok_or("Ссылка на перетащенный файл истекла")?;
        if selected.selected.elapsed() >= EXPIRY { return Err("Перетащите файл ещё раз: ссылка истекла".into()); }
        let mut bytes = Vec::new();
        selected.file.take(selected.limit + 1).read_to_end(&mut bytes).map_err(|_| "Не удалось прочитать файл")?;
        if bytes.len() as u64 > selected.limit { return Err("Файл вырос сверх допустимого размера".into()); }
        Ok(DroppedFile { filename: selected.filename, content_base64: STANDARD.encode(bytes) })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tokens_are_one_use_and_unknown_paths_are_not_accepted() {
        let path = std::env::temp_dir().join(format!("symphony-{}.txt", uuid::Uuid::new_v4()));
        std::fs::write(&path, b"selected bytes").unwrap();
        let mut store = DropStore::default();
        let item = store.register(&path).unwrap();
        assert!(store.consume(path.to_str().unwrap()).is_err());
        assert_eq!(store.consume(&item.token).unwrap().content_base64, STANDARD.encode(b"selected bytes"));
        assert!(store.consume(&item.token).is_err());
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn growth_and_expiry_are_checked_when_consuming() {
        let path = std::env::temp_dir().join(format!("symphony-{}.txt", uuid::Uuid::new_v4()));
        std::fs::write(&path, b"selected").unwrap();
        let mut store = DropStore::default();
        let item = store.register(&path).unwrap();
        store.files.get_mut(&item.token).unwrap().limit = 3;
        assert!(store.consume(&item.token).is_err());
        let item = store.register(&path).unwrap();
        store.files.get_mut(&item.token).unwrap().selected = Instant::now() - EXPIRY;
        assert!(store.consume(&item.token).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
