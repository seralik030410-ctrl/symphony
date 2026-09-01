fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "has_openai_key", "set_openai_key", "delete_openai_key", "consume_dropped_file"
        ]),
    )).expect("failed to generate desktop command permissions");
}
