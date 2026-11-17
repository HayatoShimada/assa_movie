import { describe, expect, it, vi } from 'vitest'
import { canPickFolder, pickFolder } from './nativeDialog'

describe('フォルダ選択ダイアログ', () => {
  it('ブラウザ(開発版)では出せない', () => {
    expect(canPickFolder({})).toBe(false)
    expect(canPickFolder({ __TAURI_INTERNALS__: {} })).toBe(false)
  })

  it('デスクトップ版では出せる', () => {
    expect(canPickFolder({ __TAURI_INTERNALS__: { invoke: vi.fn() } })).toBe(true)
  })

  it('フォルダ選択としてダイアログを開き、選んだパスを返す', async () => {
    const invoke = vi.fn().mockResolvedValue('/Users/yamada/Movies/切り抜き')
    const picked = await pickFolder(
      { title: '書き出し先を選ぶ', defaultPath: '/Users/yamada/Movies/KirinukiStudio' },
      { __TAURI_INTERNALS__: { invoke } },
    )
    expect(picked).toBe('/Users/yamada/Movies/切り抜き')
    expect(invoke).toHaveBeenCalledWith('plugin:dialog|open', {
      options: {
        directory: true,
        multiple: false,
        canCreateDirectories: true,
        title: '書き出し先を選ぶ',
        defaultPath: '/Users/yamada/Movies/KirinukiStudio',
      },
    })
  })

  it('キャンセルは null', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    expect(await pickFolder({}, { __TAURI_INTERNALS__: { invoke } })).toBeNull()
  })

  it('出せない環境で呼ぶとエラー(呼び出し側は canPickFolder で分ける)', async () => {
    await expect(pickFolder({}, {})).rejects.toThrow('フォルダ選択')
  })
})
