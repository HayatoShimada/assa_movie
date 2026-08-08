// Windowsのリリースビルドで余計なコンソールウィンドウを出さない
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    kirinuki_studio_lib::run()
}
