//! KirinukiStudio のデスクトップシェル。
//!
//! やることは3つだけ:
//!   1. Pythonバックエンドを空きポートで起動する
//!   2. 応答するまで待つ
//!   3. そのURLをwebviewに注入して画面を出す
//!
//! 画面そのものは frontend/(React)で、シェルはロジックを持たない。

pub mod backend;

use std::path::PathBuf;

use backend::Backend;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

const WINDOW_TITLE: &str = "KirinukiStudio";
const WINDOW_SIZE: (f64, f64) = (1280.0, 860.0);
const WINDOW_MIN_SIZE: (f64, f64) = (900.0, 600.0);

/// 開発中にPythonを動かす作業ディレクトリ(= リポジトリ直下)。
/// 配布版は同梱バイナリを使うのでこの値は参照されない。
fn dev_repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent() // frontend/
        .and_then(|p| p.parent()) // リポジトリ直下
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn exe_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// webviewに最初に流し込むスクリプト。
///
/// 画面のどのコードより先に走るので、client.ts が読む時点で値が入っている。
/// JSONとして埋め込むのは、URLに引用符が混ざってもスクリプトが壊れないようにするため。
pub fn injection_script(api_base: &str) -> String {
    format!("window.__KS_API_BASE__ = {:?};", api_base)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(move |app| {
            // 同梱物(whisper.cpp)の置き場所はパッケージ形式で変わる。
            // .debなら /usr/lib/KirinukiStudio、AppImageなら展開先。
            // 自分で組み立てず、Tauriに聞いてバックエンドへ渡す
            let resource_dir = app.path().resource_dir().ok();
            backend::start_log_session();
            let mut server = match Backend::spawn(&exe_dir(), &dev_repo_root(), resource_dir) {
                Ok(server) => server,
                Err(e) => {
                    backend::report_fatal(&format!("バックエンドを起動できませんでした: {e}"));
                    std::process::exit(1);
                }
            };
            if !server.wait_until_ready() {
                backend::report_fatal("バックエンドが応答しません(ログを確認してください)");
                std::process::exit(1);
            }
            let api_base = server.api_base();
            // verify_windows.ps1 がこの行からポートを読む。書式を変えるときは向こうも直す
            backend::log_line(&format!("バックエンド起動: {api_base}"));

            // Backendを保持させることで、アプリ終了時のDropでPythonも確実に止まる
            app.manage(server);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title(WINDOW_TITLE)
                .inner_size(WINDOW_SIZE.0, WINDOW_SIZE.1)
                .min_inner_size(WINDOW_MIN_SIZE.0, WINDOW_MIN_SIZE.1)
                .initialization_script(&injection_script(&api_base))
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Tauriアプリの起動に失敗しました");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn 注入スクリプトはURLをJSONとして埋め込む() {
        assert_eq!(
            injection_script("http://127.0.0.1:49321"),
            r#"window.__KS_API_BASE__ = "http://127.0.0.1:49321";"#
        );
    }

    #[test]
    fn 引用符が混ざってもスクリプトが壊れない() {
        let script = injection_script(r#"http://x"; alert(1); //"#);
        assert!(script.contains(r#"\""#), "引用符はエスケープされる: {script}");
    }
}
