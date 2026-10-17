import { describe, expect, it } from 'vitest'
import { isInstalled, ollamaModelOptions, pickOllamaModel } from './llm'

// 評価機(24GB)に実際に入っていたモデル
const INSTALLED = [
  { name: 'gemma4:26b', vram_mb: 20402, fits: true },
  { name: 'qwen2.5:32b', vram_mb: 21771, fits: true },
  { name: 'qwen2.5-coder:32b', vram_mb: 21771, fits: true },
]

describe('isInstalled', () => {
  it.each([
    ['入っている', 'qwen2.5:32b', true],
    ['入っていない(既定のqwen3:32b)', 'qwen3:32b', false],
    // タグ省略は :latest と同じ(Ollamaの表記)
    ['タグ省略は:latestと同じ', 'llama3', false],
  ] as const)('%s', (_, name, expected) => {
    expect(isInstalled(name, INSTALLED)).toBe(expected)
  })

  it('タグ省略と:latestを同一視する', () => {
    expect(isInstalled('llama3', [{ name: 'llama3:latest' }])).toBe(true)
  })
})

describe('pickOllamaModel(初回セットアップで既定にするモデル)', () => {
  it.each([
    // [説明, 今の設定, おすすめ, 選ぶもの]
    ['今の設定が入っていればそのまま', 'gemma4:26b', 'qwen2.5:32b', 'gemma4:26b'],
    ['入っていなければおすすめ', 'qwen3:32b', 'qwen2.5:32b', 'qwen2.5:32b'],
    // GPUに収まるものが無い・GPUなしの機体。入っているものなら動く(遅いだけ)
    ['おすすめが無ければいちばん小さいもの', 'qwen3:32b', null, 'gemma4:26b'],
  ] as const)('%s', (_, current, recommended, expected) => {
    expect(pickOllamaModel(current, INSTALLED, recommended)).toBe(expected)
  })

  it('何も入っていなければ選ばない(ollama pull を案内する)', () => {
    expect(pickOllamaModel('qwen3:32b', [], null)).toBeNull()
  })
})

describe('ollamaModelOptions(モデルの選択肢)', () => {
  const options = ollamaModelOptions({
    current: 'qwen3:32b',
    installed: [...INSTALLED, { name: 'huge:70b', vram_mb: 50000, fits: false }],
    suggested: ['qwen3:32b', 'qwen3:14b'],
    recommended: 'qwen2.5:32b',
  })

  it('インストール済みを先に並べ、おすすめに印を付ける', () => {
    expect(options[0].name).toBe('gemma4:26b')
    expect(options.find((o) => o.name === 'qwen2.5:32b')?.label).toContain('おすすめ')
  })

  it('必要メモリの目安を出し、収まらないものは遅くなると書く', () => {
    expect(options.find((o) => o.name === 'gemma4:26b')?.label).toContain('19.9GB')
    expect(options.find((o) => o.name === 'huge:70b')?.label).toContain('遅くなります')
  })

  it('未インストールのものは未インストールと書く(選んだままの設定値も消さない)', () => {
    const missing = options.filter((o) => o.label.includes('未インストール')).map((o) => o.name)
    expect(missing).toEqual(['qwen3:32b', 'qwen3:14b'])
  })

  it('同じモデルを二重に並べない', () => {
    const names = options.map((o) => o.name)
    expect(new Set(names).size).toBe(names.length)
  })
})
