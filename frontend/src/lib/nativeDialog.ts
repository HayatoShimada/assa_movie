/**
 * OSのフォルダ選択ダイアログ(Finder / エクスプローラー)。
 *
 * ブラウザの画面からは、選んだフォルダの絶対パスを取れない(取れるのは名前だけ)。
 * デスクトップ版はTauriシェルのダイアログを借りる(src-tauri の tauri-plugin-dialog。
 * 許可は capabilities/default.json)。ブラウザで動かす開発版には無いので、
 * 呼び出し側はパスの入力欄に切り替える。
 */

/** Tauriがwebviewに用意する呼び出し口(@tauri-apps/api を入れずに直接使う) */
interface TauriInternals {
  invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
}

type MaybeTauriWindow = { __TAURI_INTERNALS__?: Partial<TauriInternals> }

function internals(w: MaybeTauriWindow): TauriInternals | null {
  const t = w.__TAURI_INTERNALS__
  return t && typeof t.invoke === 'function' ? (t as TauriInternals) : null
}

/** フォルダ選択ダイアログを出せるか(デスクトップ版だけ) */
export function canPickFolder(w: MaybeTauriWindow = window as MaybeTauriWindow): boolean {
  return internals(w) !== null
}

/**
 * フォルダを選ばせる。選んだフォルダの絶対パス、キャンセルなら null。
 * defaultPath: 最初に開いておく場所(今の書き出し先)。
 */
export async function pickFolder(
  options: { title?: string; defaultPath?: string } = {},
  w: MaybeTauriWindow = window as MaybeTauriWindow,
): Promise<string | null> {
  const tauri = internals(w)
  if (!tauri) throw new Error('この環境ではフォルダ選択ダイアログを開けません')
  const picked = await tauri.invoke('plugin:dialog|open', {
    options: {
      directory: true,
      multiple: false,
      // macOSで「新規フォルダ」ボタンを出す(書き出し用のフォルダをその場で作れる)
      canCreateDirectories: true,
      title: options.title,
      defaultPath: options.defaultPath,
    },
  })
  return typeof picked === 'string' && picked ? picked : null
}
