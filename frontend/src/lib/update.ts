/**
 * 新しい版のお知らせを「あとで」にした記録。
 *
 * 版ごとに覚える(v2.1.0 を閉じても、v2.2.0 が出たらまた知らせる)。
 * 設定(サーバー側)ではなく画面の記憶に置く。消えても「もう一度出る」だけで害が無い。
 */
const KEY = 'ks.update.dismissed'

type Store = Pick<Storage, 'getItem' | 'setItem'>

export function isDismissed(latest: string | null | undefined, store: Store = localStorage): boolean {
  if (!latest) return false
  try {
    return store.getItem(KEY) === latest
  } catch {
    return false // 保存領域が使えない環境では毎回出す
  }
}

export function dismiss(latest: string, store: Store = localStorage): void {
  try {
    store.setItem(KEY, latest)
  } catch {
    // 覚えられなくても動作は変えない
  }
}

/** 更新の手順(OSごと)。自動更新は無いので、入れ直し方を必ず添える */
export const UPDATE_STEPS: { os: string; step: string }[] = [
  {
    os: 'Windows',
    step: 'ダウンロードした .exe(または .msi)を実行します。今の版に上書きされます。',
  },
  {
    os: 'macOS',
    step: '.dmg を開き、KirinukiStudio を「アプリケーション」へドラッグして置き換えます。',
  },
  {
    os: 'Ubuntu / Debian',
    step: 'ダウンロードした .deb を sudo apt install ./KirinukiStudio_*.deb で入れ直します。',
  },
]

export const UPDATE_KEEPS_DATA =
  '更新しても、プロジェクト・文字起こし・設定・書き出した動画はそのまま残ります。先にアプリを閉じてから入れてください。'
