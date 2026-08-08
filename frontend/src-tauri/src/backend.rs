//! Pythonバックエンド(FastAPI)を子プロセスとして起動し、応答するまで待つ。
//!
//! ポートは起動のたびに空きを取り直す。固定にすると、別のアプリや
//! 開発中の `./dev.sh`(8000番)とぶつかって起動できなくなるため。
//! 確保したポートはwebviewに注入する(frontend/src/api/client.ts の resolveApiBase)。

use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

/// 配布物に同梱するバックエンドの実行ファイル名(M28でPyInstallerが作る)
const SIDECAR_NAME: &str = "kirinuki-studio-backend";
/// 起動を待つ上限。初回はDBの作成とマイグレーションが走るので長めに取る
const READY_TIMEOUT: Duration = Duration::from_secs(90);
const POLL_INTERVAL: Duration = Duration::from_millis(200);

/// 空きポートを1つ確保する。
///
/// OSに0番を頼んで割り当てさせ、すぐ閉じて同じ番号をバックエンドに渡す。
/// 閉じてから渡すまでの隙間で他プロセスに取られる可能性は残るが、
/// 実用上は無視できる(取られたらバックエンドが起動に失敗して検知できる)。
pub fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
    listener.local_addr().map(|addr| addr.port())
}

/// HTTPの応答が成功かどうか(純関数)
pub fn is_ok_response(response: &str) -> bool {
    response
        .lines()
        .next()
        .is_some_and(|line| line.starts_with("HTTP/1.") && line.contains(" 200 "))
}

/// 同梱のバックエンド実行ファイル。無ければNone(開発中はuv経由で動かす)
fn sidecar_path(exe_dir: &Path) -> Option<PathBuf> {
    let path = exe_dir.join(SIDECAR_NAME);
    path.is_file().then_some(path)
}

/// 開発中に使うPythonインタプリタ。`uv run` を挟むと中間プロセスが1つ増え、
/// 親の死を伝える PR_SET_PDEATHSIG が uv にしか効かずPythonが生き残ってしまう
fn venv_python(repo_root: &Path) -> Option<PathBuf> {
    let python = repo_root.join(".venv/bin/python");
    python.is_file().then_some(python)
}

/// バックエンドを起動するコマンドを組み立てる。
///
/// 配布版は同梱の実行ファイル、開発中はリポジトリ直下の .venv で動かす。
/// この分岐をここに閉じ込めておくと、M28で同梱方式が変わっても呼び出し側は無傷。
pub fn build_command(exe_dir: &Path, repo_root: &Path, port: u16) -> Command {
    let port = port.to_string();
    if let Some(bin) = sidecar_path(exe_dir) {
        let mut cmd = Command::new(bin);
        cmd.arg("--port").arg(port);
        return cmd;
    }
    let mut cmd = match venv_python(repo_root) {
        Some(python) => {
            let mut cmd = Command::new(python);
            cmd.args(["-m", "uvicorn"]);
            cmd
        }
        // .venvが無い環境向けの保険。中間プロセスが増えるので普段は使わない
        None => {
            let mut cmd = Command::new("uv");
            cmd.args(["run", "--no-sync", "python", "-m", "uvicorn"]);
            cmd
        }
    };
    cmd.current_dir(repo_root)
        .arg("backend.app:app")
        // 外部に開かない。ローカルアプリなので待ち受けはループバックだけ
        .args(["--host", "127.0.0.1", "--port", &port]);
    cmd
}

/// 親プロセスが死んだらこの子も終了するよう仕込む(Linux)。
///
/// Dropはウィンドウを閉じたときには走るが、SIGTERM・SIGKILL・panicでは走らない。
/// その場合にPythonが残るとポートとGPUを掴み続けるので、カーネルに面倒を見てもらう。
#[cfg(target_os = "linux")]
fn kill_with_parent(cmd: &mut Command) {
    use std::os::unix::process::CommandExt;
    unsafe {
        cmd.pre_exec(|| {
            libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
            Ok(())
        });
    }
}

#[cfg(not(target_os = "linux"))]
fn kill_with_parent(_cmd: &mut Command) {}

/// 起動したバックエンド。アプリ終了時に確実に止める。
pub struct Backend {
    child: Child,
    pub port: u16,
}

impl Backend {
    pub fn spawn(exe_dir: &Path, repo_root: &Path) -> std::io::Result<Self> {
        let port = free_port()?;
        let mut cmd = build_command(exe_dir, repo_root, port);
        // ログはシェルの標準出力にそのまま流す(起動失敗の原因が見えるように)
        cmd.stdout(Stdio::inherit()).stderr(Stdio::inherit());
        kill_with_parent(&mut cmd);
        let child = cmd.spawn()?;
        Ok(Self { child, port })
    }

    /// `/api/health` が200を返すまで待つ。時間内に応答しなければfalse
    pub fn wait_until_ready(&mut self) -> bool {
        let deadline = Instant::now() + READY_TIMEOUT;
        while Instant::now() < deadline {
            // 先に死んでいたら待つだけ無駄。原因はinheritした標準エラーに出ている
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                return false;
            }
            if health_check(self.port) {
                return true;
            }
            std::thread::sleep(POLL_INTERVAL);
        }
        false
    }

    pub fn api_base(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        // ウィンドウを閉じてもPythonが残るとポートとGPUを掴んだままになる
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// `/api/health` を叩く。HTTPクライアントを足すほどの用途ではないので自前で書く
fn health_check(port: u16) -> bool {
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, POLL_INTERVAL) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let request = "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = [0u8; 128]; // ステータス行が読めれば足りる
    match stream.read(&mut response) {
        Ok(n) => is_ok_response(&String::from_utf8_lossy(&response[..n])),
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn 空きポートは毎回使える番号を返す() {
        let port = free_port().unwrap();
        assert!(port > 1024, "特権ポートは割り当てられない");
        // 返ってきた番号が実際に使えること(閉じた後なので再バインドできる)
        TcpListener::bind((Ipv4Addr::LOCALHOST, port)).unwrap();
    }

    #[test]
    fn ステータス行が200かどうかを見る() {
        assert!(is_ok_response("HTTP/1.1 200 OK\r\ncontent-type: application/json"));
        assert!(is_ok_response("HTTP/1.0 200 OK\r\n"));
        assert!(!is_ok_response("HTTP/1.1 404 Not Found\r\n"));
        assert!(!is_ok_response("HTTP/1.1 500 Internal Server Error\r\n"));
        assert!(!is_ok_response(""));
        // 本文にたまたま200が含まれていても、ステータス行を見ているので誤判定しない
        assert!(!is_ok_response("HTTP/1.1 503 Unavailable\r\n\r\n{\"retry\": 200}"));
    }

    fn args_of(cmd: &Command) -> Vec<String> {
        cmd.get_args().map(|a| a.to_string_lossy().into_owned()).collect()
    }

    #[test]
    fn 同梱バイナリが無ければリポジトリのvenvで起動する() {
        let repo = std::env::temp_dir().join("ks-venv-repo");
        std::fs::create_dir_all(repo.join(".venv/bin")).unwrap();
        std::fs::write(repo.join(".venv/bin/python"), b"#!/bin/sh\n").unwrap();
        let empty = std::env::temp_dir().join("ks-no-sidecar");
        std::fs::create_dir_all(&empty).unwrap();

        let cmd = build_command(&empty, &repo, 49152);
        // uvを挟むと中間プロセスが増え、親の死がPythonまで伝わらない
        assert!(cmd.get_program().to_string_lossy().ends_with(".venv/bin/python"));
        let args = args_of(&cmd);
        assert!(args.contains(&"49152".to_string()));
        assert!(args.contains(&"127.0.0.1".to_string()), "外部には開かない");
        assert_eq!(cmd.get_current_dir(), Some(repo.as_path()));
    }

    #[test]
    fn venvが無ければuvにフォールバックする() {
        let empty = std::env::temp_dir().join("ks-no-venv");
        std::fs::create_dir_all(&empty).unwrap();
        let cmd = build_command(&empty, &empty, 49154);
        assert_eq!(cmd.get_program(), "uv");
        assert!(args_of(&cmd).contains(&"49154".to_string()));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn 親が死ぬと子も終了する() {
        // 親役のsleepを起動し、その子として長いsleepをPDEATHSIG付きで起動する。
        // 親をkillしたあと子が消えることを確認する(Dropの走らない経路の担保)
        let mut cmd = Command::new("sh");
        cmd.args(["-c", "sleep 30 & echo $!; wait"]);
        kill_with_parent(&mut cmd);
        let mut child = cmd.stdout(Stdio::piped()).spawn().unwrap();
        std::thread::sleep(Duration::from_millis(300));

        let pid = child.id();
        child.kill().unwrap();
        child.wait().unwrap();
        std::thread::sleep(Duration::from_millis(500));

        // 子プロセスが残っていないこと(/proc から消えている)
        assert!(
            !Path::new(&format!("/proc/{pid}")).exists(),
            "親を殺したのに子が残っている"
        );
    }

    #[test]
    fn 同梱バイナリがあればそれを使う() {
        let dir = std::env::temp_dir().join("ks-with-sidecar");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join(SIDECAR_NAME), b"#!/bin/sh\n").unwrap();
        let cmd = build_command(&dir, Path::new("/repo"), 49153);
        assert!(cmd.get_program().to_string_lossy().ends_with(SIDECAR_NAME));
    }

    #[test]
    fn 応答しないポートはreadyにならない() {
        // 誰も待ち受けていないポートを作る(束縛して即座に閉じる)
        let port = free_port().unwrap();
        assert!(!health_check(port));
    }
}
