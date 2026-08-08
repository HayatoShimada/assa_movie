//! Pythonバックエンド(FastAPI)を子プロセスとして起動し、応答するまで待つ。
//!
//! ポートは起動のたびに空きを取り直す。固定にすると、別のアプリや
//! 開発中の `./dev.sh`(8000番)とぶつかって起動できなくなるため。
//! 確保したポートはwebviewに注入する(frontend/src/api/client.ts の resolveApiBase)。

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

/// 配布物に同梱するバックエンドの実行ファイル名(M28でPyInstallerが作る)。
///
/// Windowsでは `.exe` が付く。ここを拡張子なしのままにしていたため、v0.9.2の
/// Windows版は同梱バックエンドを見つけられず、開発用のuvフォールバックに落ちて
/// 「program not found」で即終了していた(M32)
#[cfg(windows)]
const SIDECAR_NAME: &str = "kirinuki-studio-backend.exe";
#[cfg(not(windows))]
const SIDECAR_NAME: &str = "kirinuki-studio-backend";

/// 開発中に使う仮想環境のPython。Windowsは bin/ ではなく Scripts/ に入る
#[cfg(windows)]
const VENV_PYTHON: &str = ".venv/Scripts/python.exe";
#[cfg(not(windows))]
const VENV_PYTHON: &str = ".venv/bin/python";
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
    let python = repo_root.join(VENV_PYTHON);
    python.is_file().then_some(python)
}

// ---- ログ ---------------------------------------------------------------
//
// GUIアプリの標準出力・標準エラーはどこにも出ない(Windowsでは端末に繋がらない)。
// v0.9.2のWindows版は起動に失敗しても理由が誰にも見えず、利用者からは
// 「ダブルクリックしても何も起きない」だけだった。だからファイルにも残す。

/// データの置き場所。backend/core/paths.py と同じ規則にする
fn data_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        std::env::var_os("APPDATA").map(|p| PathBuf::from(p).join("kirinuki-studio"))
    }
    #[cfg(target_os = "macos")]
    {
        std::env::var_os("HOME")
            .map(|h| PathBuf::from(h).join("Library/Application Support/kirinuki-studio"))
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/share")))
            .map(|p| p.join("kirinuki-studio"))
    }
}

pub fn log_dir() -> Option<PathBuf> {
    data_dir().map(|d| d.join("logs"))
}

fn open_log(name: &str, truncate: bool) -> Option<File> {
    let dir = log_dir()?;
    fs::create_dir_all(&dir).ok()?;
    OpenOptions::new()
        .create(true)
        .append(!truncate)
        .write(true)
        .truncate(truncate)
        .open(dir.join(name))
        .ok()
}

/// 起動のたびにログを空にする。
///
/// 追記のままだと際限なく育つうえ、障害報告のときに前回の失敗と混ざって読みにくい。
/// 見たいのはいつも「今回の起動で何が起きたか」だけ。
pub fn start_log_session() {
    for name in ["shell.log", "backend.log"] {
        let _ = open_log(name, true);
    }
}

/// シェル自身のログ。端末にもファイルにも出す
pub fn log_line(msg: &str) {
    eprintln!("{msg}");
    if let Some(mut file) = open_log("shell.log", false) {
        let _ = writeln!(file, "{msg}");
    }
}

/// バックエンドの出力を、端末とログファイルの両方へ流す
fn tee<R: Read + Send + 'static>(reader: Option<R>, is_err: bool) {
    let Some(reader) = reader else { return };
    thread::spawn(move || {
        let mut file = open_log("backend.log", false);
        for line in BufReader::new(reader).lines() {
            // 文字化けした行があっても読み続ける(そこで止めると以降が全部消える)
            let Ok(line) = line else { continue };
            if is_err {
                eprintln!("{line}");
            } else {
                println!("{line}");
            }
            if let Some(file) = file.as_mut() {
                let _ = writeln!(file, "{line}");
            }
        }
    });
}

/// 起動できなかったことを利用者に伝える。
///
/// 黙って終了すると「ダブルクリックしても何も起きない」ようにしか見えない。
/// ログの場所まで含めて出す(そのまま障害報告に貼れる)
pub fn report_fatal(msg: &str) {
    log_line(msg);
    let detail = match log_dir() {
        Some(dir) => format!("{msg}\n\nログ: {}", dir.display()),
        None => msg.to_string(),
    };
    show_dialog(&detail);
}

#[cfg(windows)]
fn show_dialog(msg: &str) {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};

    let wide = |s: &str| -> Vec<u16> { OsStr::new(s).encode_wide().chain([0]).collect() };
    let text = wide(msg);
    let title = wide("KirinukiStudio");
    unsafe {
        MessageBoxW(std::ptr::null_mut(), text.as_ptr(), title.as_ptr(), MB_OK | MB_ICONERROR);
    }
}

#[cfg(not(windows))]
fn show_dialog(_msg: &str) {
    // Linux/macOSは端末から起動されることが多く、標準エラーで足りている
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

/// 親が死んだら子も道連れにする(Windows)。
///
/// WindowsにはPR_SET_PDEATHSIGに相当するものが無い。ジョブオブジェクトに入れると
/// ハンドルが閉じた時点で中のプロセスがまとめて終了する。プロセスが強制終了されても
/// カーネルがハンドルを閉じるので、Dropが走らない経路(releaseプロファイルは
/// panic="abort")でも効く。
///
/// PyInstallerのonefileは自分の子として本体を起動するため、実測ではバックエンドが
/// 2プロセスになる。ジョブは子孫にも及ぶので両方まとめて片付く。
#[cfg(windows)]
mod job {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    pub struct Job(HANDLE);

    // ハンドルはこのプロセスのもので、閉じる以外の操作はしない
    unsafe impl Send for Job {}
    unsafe impl Sync for Job {}

    impl Job {
        /// 子プロセスをジョブに入れる。失敗してもアプリは動かす(後始末が甘くなるだけ)
        pub fn capture(child: &Child) -> Option<Self> {
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return None;
                }
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let ok = SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const std::ffi::c_void,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if ok == 0 {
                    CloseHandle(handle);
                    return None;
                }
                if AssignProcessToJobObject(handle, child.as_raw_handle() as HANDLE) == 0 {
                    CloseHandle(handle);
                    return None;
                }
                Some(Self(handle))
            }
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            // 閉じた瞬間に中のプロセスが終了する
            unsafe { CloseHandle(self.0) };
        }
    }
}

/// 起動したバックエンド。アプリ終了時に確実に止める。
pub struct Backend {
    child: Child,
    pub port: u16,
    /// 保持しているだけ。落ちた時にバックエンドを道連れにするのが役目
    #[cfg(windows)]
    _job: Option<job::Job>,
}

impl Backend {
    pub fn spawn(
        exe_dir: &Path,
        repo_root: &Path,
        resource_dir: Option<PathBuf>,
    ) -> std::io::Result<Self> {
        let port = free_port()?;
        let mut cmd = build_command(exe_dir, repo_root, port);
        // 同梱したwhisper.cppの探索先(backend/engines/asr/whispercpp.py が読む)
        if let Some(dir) = resource_dir {
            cmd.env("KS_RESOURCE_DIR", dir);
        }
        // 受け取ってから端末とログファイルの両方へ流す。
        // inheritのままだとGUIアプリでは出力が消え、起動失敗の原因が追えない
        cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
        kill_with_parent(&mut cmd);
        let mut child = cmd.spawn()?;
        #[cfg(windows)]
        let job = job::Job::capture(&child);
        tee(child.stdout.take(), false);
        tee(child.stderr.take(), true);
        Ok(Self {
            child,
            port,
            #[cfg(windows)]
            _job: job,
        })
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
        let python = repo.join(VENV_PYTHON);
        std::fs::create_dir_all(python.parent().unwrap()).unwrap();
        std::fs::write(&python, b"#!/bin/sh\n").unwrap();
        let empty = std::env::temp_dir().join("ks-no-sidecar");
        std::fs::create_dir_all(&empty).unwrap();

        let cmd = build_command(&empty, &repo, 49152);
        // uvを挟むと中間プロセスが増え、親の死がPythonまで伝わらない
        assert_eq!(cmd.get_program(), python.as_os_str());
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

    #[cfg(windows)]
    #[test]
    fn windowsのサイドカーは拡張子付きで探す() {
        // Tauriが配置するのは kirinuki-studio-backend.exe。拡張子なしで探すと
        // is_file()がfalseになり、uvフォールバックに落ちて起動できなかった(v0.9.2)
        assert!(SIDECAR_NAME.ends_with(".exe"), "実際に配置される名前と一致させる");

        let dir = std::env::temp_dir().join("ks-win-sidecar");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("kirinuki-studio-backend.exe"), b"").unwrap();

        // repo_root には .venv を置かない。拾えていなければuvに落ちるので違いが出る
        let cmd = build_command(&dir, &std::env::temp_dir().join("ks-win-norepo"), 49155);
        assert!(
            cmd.get_program().to_string_lossy().ends_with("kirinuki-studio-backend.exe"),
            "同梱バックエンドではなく {:?} を起動しようとしている",
            cmd.get_program()
        );
    }

    #[cfg(windows)]
    #[test]
    fn windowsのvenvはScripts配下を見る() {
        // Windowsのvenvは bin/ ではなく Scripts/ で、実行ファイルに .exe が付く
        assert_eq!(VENV_PYTHON, ".venv/Scripts/python.exe");
    }

    #[test]
    fn 応答しないポートはreadyにならない() {
        // 誰も待ち受けていないポートを作る(束縛して即座に閉じる)
        let port = free_port().unwrap();
        assert!(!health_check(port));
    }
}
