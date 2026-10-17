/**
 * AI(Ollama)モデルの選択肢と既定の選び方(純関数)。
 *
 * 評価で、既定の qwen3:32b がインストールされていない機体だと AI機能が
 * 全部失敗した。選択肢ではインストール済みを先に並べておすすめに印を付け、
 * 初回セットアップでは入っているモデルを既定にする。
 */

export interface OllamaModel {
  name: string
  /** 必要なGPUメモリの目安(MB) */
  vram_mb: number
  /** このPCのGPUメモリに収まるか */
  fits: boolean
}

/** タグ省略は :latest と同じ(Ollamaの表記) */
function normalize(name: string): string {
  return name.includes(':') ? name : `${name}:latest`
}

export function isInstalled(name: string, installed: readonly Pick<OllamaModel, 'name'>[]): boolean {
  return installed.some((m) => normalize(m.name) === normalize(name))
}

/**
 * 初回セットアップで既定にするモデル。
 * 今の設定が入っていればそれ、無ければおすすめ、おすすめも無ければ
 * いちばん小さいもの(GPUに収まらなくても入っていれば動く)。何も無ければ null。
 */
export function pickOllamaModel(
  current: string,
  installed: readonly OllamaModel[],
  recommended: string | null,
): string | null {
  if (installed.length === 0) return null
  if (current && isInstalled(current, installed)) return current
  if (recommended && isInstalled(recommended, installed)) return recommended
  return [...installed].sort((a, b) => a.vram_mb - b.vram_mb)[0].name
}

const GB = (mb: number) => `${(mb / 1024).toFixed(1)}GB`

/** 設定画面・ウィザードのモデルの選択肢 */
export function ollamaModelOptions({
  current,
  installed,
  suggested,
  recommended,
}: {
  current: string
  installed: readonly OllamaModel[]
  /** よく使われるモデル(未インストールでも候補に出す) */
  suggested: readonly string[]
  recommended: string | null
}): { name: string; label: string }[] {
  const options = installed.map((m) => ({
    name: m.name,
    label: [
      m.name,
      m.name === recommended ? '(おすすめ)' : '',
      `(必要メモリ目安 ${GB(m.vram_mb)}`,
      m.fits ? ')' : '・GPUに収まらないため遅くなります)',
    ].join(''),
  }))
  const missing = [current, ...suggested].filter(
    (name, i, all) => name && all.indexOf(name) === i && !isInstalled(name, installed),
  )
  return [...options, ...missing.map((name) => ({ name, label: `${name}(未インストール)` }))]
}
