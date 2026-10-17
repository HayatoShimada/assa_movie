import { describe, expect, it } from 'vitest'
import { clipStatusLabel, mediaDisplayName, mediaState, splitPath } from './media'

describe('mediaDisplayName(一覧に出す動画名)', () => {
  it.each([
    // [パス, 期待する表示名]
    ['/home/user/対談.mov', '対談.mov'],
    // Windowsのパスは区切りが「\」。'/'だけで切るとフルパスがそのまま出ていた
    ['C:\\Users\\hayato\\Videos\\対談 第1回.mp4', '対談 第1回.mp4'],
    ['D:/動画/混在\\ゲスト回.mkv', 'ゲスト回.mkv'],
    // アップロードした動画は保存時に衝突よけの32桁hexが前に付く。利用者には見せない
    [
      '/data/uploads/project_3/d0422babc57446fbaaa44609807ae8f3_2026-10-11 19-38-13.mov',
      '2026-10-11 19-38-13.mov',
    ],
    // 32桁hex以外の接頭辞は元のファイル名の一部なので残す
    ['/v/abc_対談.mov', 'abc_対談.mov'],
    ['/v/0123456789abcdef_short.mov', '0123456789abcdef_short.mov'],
    // 名前がhexだけ(拡張子付き)のファイルは削らない
    ['/v/d0422babc57446fbaaa44609807ae8f3.mov', 'd0422babc57446fbaaa44609807ae8f3.mov'],
    ['対談.mov', '対談.mov'],
  ])('%s → %s', (path, expected) => {
    expect(mediaDisplayName(path)).toBe(expected)
  })
})

describe('mediaState(動画の状態バッジ)', () => {
  it.each([
    // [DBの状態, ジョブの状態, 表示, 色]
    ['registered', 'idle', '文字起こし前', 'neutral'],
    ['transcribed', 'idle', '文字起こし済み', 'done'],
    // 画面から始めたジョブはDBより新しいのでジョブ側を優先する
    ['registered', 'queued', '順番待ち', 'busy'],
    ['registered', 'running', '文字起こし中', 'busy'],
    ['transcribed', 'running', '文字起こし中', 'busy'],
    ['registered', 'failed', '失敗', 'error'],
    ['registered', 'cancelled', '中止', 'neutral'],
    // 再文字起こしを中止しても前の結果は残っている
    ['transcribed', 'cancelled', '文字起こし済み', 'done'],
    ['registered', 'completed', '文字起こし済み', 'done'],
    // 知らない状態はそのまま見せる(隠すと原因を追えない)
    ['converting', 'idle', 'converting', 'neutral'],
  ] as const)('%s + ジョブ%s → %s', (status, job, label, tone) => {
    expect(mediaState(status, job)).toEqual({ label, tone })
  })
})

describe('clipStatusLabel(クリップの状態)', () => {
  it.each([
    ['suggested', 'AI候補'],
    ['draft', '自分で作成'],
    ['exporting', '書き出し中'],
    ['exported', '書き出し済み'],
    ['unknown_status', 'unknown_status'],
  ])('%s → %s', (status, label) => {
    expect(clipStatusLabel(status)).toBe(label)
  })
})

describe('splitPath(書き出し先の表示)', () => {
  it.each([
    // [パス, フォルダ, ファイル名]
    ['/home/user/Videos/exports/対談_0s-10s_clip1.mp4', '/home/user/Videos/exports', '対談_0s-10s_clip1.mp4'],
    // Windowsの区切り「\」でもフォルダとファイル名に分ける
    [
      'C:\\Users\\山田\\AppData\\Roaming\\kirinuki-studio\\uploads\\project_3\\exports\\対談 1_0s-10s.mp4',
      'C:\\Users\\山田\\AppData\\Roaming\\kirinuki-studio\\uploads\\project_3\\exports',
      '対談 1_0s-10s.mp4',
    ],
    ['a.mp4', '', 'a.mp4'],
  ])('%s', (path, folder, name) => {
    expect(splitPath(path)).toEqual({ folder, name })
  })
})
