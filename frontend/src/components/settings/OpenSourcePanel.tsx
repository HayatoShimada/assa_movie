/**
 * オープンソースソフトウェアの表記(設定タブ)。
 *
 * 配布物にバイナリのまま同梱しているものを挙げる。とくにFFmpegはLGPLなので、
 * 「使っていること」「ライセンス」「ソースの入手先」を利用者から見える場所に
 * 置く必要がある。全文はインストール先の licenses/ フォルダに入っている。
 *
 * URLはリンクにしない。webview内で遷移するとアプリの画面から戻れなくなるため、
 * 選択してコピーできる文字列として出す。
 */

type Bundled = {
  name: string
  license: string
  /** どのOS版に同梱しているか */
  platform: string
  purpose: string
  source: string
}

const BUNDLED: Bundled[] = [
  {
    name: 'FFmpeg',
    license: 'LGPL v2.1',
    platform: 'Windows版に同梱',
    purpose: '動画の書き出し・メディア情報の取得',
    source: 'https://ffmpeg.org/releases/',
  },
  {
    name: 'whisper.cpp',
    license: 'MIT',
    platform: 'Linux版・macOS版に同梱',
    purpose: '高速な文字起こし',
    source: 'https://github.com/ggml-org/whisper.cpp',
  },
]

export function OpenSourcePanel() {
  return (
    <section
      data-testid="oss-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-2 text-sm font-semibold">オープンソースソフトウェア</h3>
      <p className="mb-2 text-xs text-neutral-500">
        本アプリはMITライセンスです。次のソフトウェアを同梱し、それぞれのライセンスに従います。
      </p>

      <ul className="space-y-2">
        {BUNDLED.map((item) => (
          <li key={item.name} data-testid={`oss-${item.name.toLowerCase()}`} className="text-sm">
            <div className="flex justify-between gap-3">
              <span className="font-medium">{item.name}</span>
              <span className="text-neutral-500">{item.license}</span>
            </div>
            <p className="text-xs text-neutral-500">
              {item.platform} / {item.purpose}
            </p>
            <p className="select-all break-all text-xs text-neutral-400">ソース: {item.source}</p>
          </li>
        ))}
      </ul>

      <p className="mt-2 text-xs text-neutral-500">
        ライセンス全文と、同梱しているビルドに対応するソースコードの入手先は、
        インストール先の <code className="select-all">licenses/</code> フォルダにあります。
      </p>
    </section>
  )
}
