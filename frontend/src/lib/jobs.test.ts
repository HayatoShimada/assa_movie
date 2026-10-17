import { describe, expect, it } from 'vitest'
import type { Job } from '../api/client'
import { isJobBusy, jobResultMessage, jobSlots, jobStatusText, pickJobId } from './jobs'

function job(
  id: number,
  type: string,
  mediaId: number | null,
  params: Record<string, unknown> = {},
) {
  return {
    id,
    type,
    media_id: mediaId,
    params,
    status: 'running',
    progress: 0.3,
    created_at: '2026-10-17 00:00:00',
  } satisfies Job
}

describe('jobSlots(どの操作のジョブかの見分け)', () => {
  // 実行中のジョブは GET /api/jobs/active から取り直す。種別だけでは見分けられない
  // ものがあるので、メディア・パラメータまで見て「その画面のジョブ」だけを拾う
  it.each([
    // [説明, 枠, ジョブ, 拾うか]
    ['質問のスキャン', jobSlots.scanTerms(1), job(1, 'extract_terms', 1), true],
    ['別メディアのスキャンは拾わない', jobSlots.scanTerms(1), job(1, 'extract_terms', 2), false],
    ['レビューの指示語解決', jobSlots.resolve(1), job(1, 'resolve', 1, { scope: 'all' }), true],
    // クリップの自己完結化も resolve。レビュータブに出すとどちらの進捗か分からない
    [
      'クリップの自己完結化はレビューに出さない',
      jobSlots.resolve(1),
      job(1, 'resolve', 1, { scope: 'segment_ids', clip_id: 5 }),
      false,
    ],
    [
      'クリップの自己完結化',
      jobSlots.clipResolve(1, 5),
      job(1, 'resolve', 1, { scope: 'segment_ids', clip_id: 5 }),
      true,
    ],
    [
      '別クリップの自己完結化は拾わない',
      jobSlots.clipResolve(1, 6),
      job(1, 'resolve', 1, { clip_id: 5 }),
      false,
    ],
    ['切り抜き候補の探索', jobSlots.suggestClips(1), job(1, 'attention', 1), true],
    ['タイトル・メタ生成', jobSlots.clipMeta(1, 5), job(1, 'clip_meta', 1, { clip_id: 5 }), true],
    // 書き出しは範囲指定(書き出しタブ)とクリップの2つがあり、どちらも export
    [
      '範囲指定の書き出し',
      jobSlots.exportRange(1),
      job(1, 'export', 1, { start: 0, end: 60 }),
      true,
    ],
    [
      'クリップの書き出しは書き出しタブに出さない',
      jobSlots.exportRange(1),
      job(1, 'export', 1, { clip_id: 5 }),
      false,
    ],
    ['クリップの書き出し', jobSlots.clipExport(1, 5), job(1, 'export', 1, { clip_id: 5 }), true],
    ['フィラー検出', jobSlots.mediaJob(1, 'filler'), job(1, 'filler', 1), true],
    [
      '字幕ジャッジはフィラーと別',
      jobSlots.mediaJob(1, 'filler'),
      job(1, 'judge_subtitles', 1),
      false,
    ],
    ['文字起こし', jobSlots.transcribe(1), job(1, 'transcribe', 1, { language: 'ja' }), true],
    // モデル取得はメディアに紐づかない
    ['モデル取得', jobSlots.setup('diarization'), job(1, 'setup_diarization', null), true],
    [
      '別のモデル取得は拾わない',
      jobSlots.setup('diarization'),
      job(1, 'setup_whispercpp', null),
      false,
    ],
  ])('%s', (_, slot, j, expected) => {
    expect(slot.matches(j)).toBe(expected)
  })

  it('枠の名前はメディア・クリップごとに分かれる(別の動画の進捗を出さない)', () => {
    const keys = [
      jobSlots.scanTerms(1).key,
      jobSlots.scanTerms(2).key,
      jobSlots.resolve(1).key,
      jobSlots.clipResolve(1, 5).key,
      jobSlots.clipResolve(1, 6).key,
      jobSlots.mediaJob(1, 'filler').key,
      jobSlots.mediaJob(1, 'judge_subtitles').key,
      jobSlots.exportRange(1).key,
      jobSlots.clipExport(1, 5).key,
      jobSlots.setup('diarization').key,
      jobSlots.setup('whispercpp').key,
    ]
    expect(new Set(keys).size).toBe(keys.length)
  })
})

describe('pickJobId(表示するジョブの選び方)', () => {
  const slot = jobSlots.scanTerms(1)
  it.each([
    // [説明, 覚えているID, 実行中のジョブ, 選ぶID]
    ['何も無ければ無し', undefined, [], null],
    // 再読み込み後: 覚えていないので実行中から拾う
    ['覚えていなければ実行中から拾う', undefined, [job(4, 'extract_terms', 1)], 4],
    // タブ切替後: 終わったジョブでも覚えていれば完了を出せる
    ['終わったジョブも覚えていれば出す', 3, [], 3],
    ['覚えているものより新しい実行中があればそちら', 3, [job(4, 'extract_terms', 1)], 4],
    ['実行中が古ければ覚えている方', 5, [job(4, 'extract_terms', 1)], 5],
    ['関係ないジョブは拾わない', undefined, [job(4, 'attention', 1)], null],
    ['複数あれば新しい方', undefined, [job(4, 'extract_terms', 1), job(7, 'extract_terms', 1)], 7],
  ])('%s', (_, stored, active, expected) => {
    expect(pickJobId(stored, active, slot)).toBe(expected)
  })
})

describe('isJobBusy(ボタンを押せなくするか)', () => {
  it.each([
    // [説明, SSEの状態, ジョブID, 実行中の一覧, 押せないか]
    ['ジョブ無し', 'idle', null, [], false],
    ['実行中', 'running', 1, [], true],
    ['順番待ち', 'queued', 1, [], true],
    ['完了', 'completed', 1, [], false],
    ['失敗', 'failed', 1, [], false],
    ['中止', 'cancelled', 1, [], false],
    // 取り直した直後はSSEの最初の通知が来る前。一覧で実行中なら押させない
    ['SSE待ちでも実行中の一覧にあれば押せない', 'idle', 1, [job(1, 'extract_terms', 1)], true],
    ['SSE待ちで一覧に無ければ押せる', 'idle', 1, [job(2, 'extract_terms', 1)], false],
  ] as const)('%s', (_, status, jobId, active, expected) => {
    expect(isJobBusy(status, jobId, [...active])).toBe(expected)
  })
})

describe('jobStatusText(進捗の文言)', () => {
  const labels = { running: '候補を探索中', done: '候補生成完了' }
  const p = (
    status: 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled',
    extra: { progress?: number; phase?: string | null; error?: string | null } = {},
  ) => ({ status, progress: 0, phase: null, error: null, result: null, ...extra })

  it.each([
    // [説明, 状態, 文言]
    ['始めていなければ出さない', p('idle'), null],
    // 別の処理の後ろで待っている間「〜中 0%」のままだと、固まったように見えた(約19分)
    ['順番待ちは実行中と分ける', p('queued'), '順番待ち(前の処理が終わると始まります)'],
    ['実行中は割合を出す', p('running', { progress: 0.42 }), '候補を探索中... 42%'],
    ['工程名があればそれを出す', p('running', { phase: '話者分離中' }), '話者分離中... 0%'],
    ['完了', p('completed', { progress: 1 }), '候補生成完了'],
    // 失敗しても「探索中...」のまま2分以上変わらなかった。バックエンドの文言を出す
    [
      '失敗はバックエンドの文言(1行目)を出す',
      p('failed', { error: 'Ollama呼び出しに3回失敗: 404\nTraceback (most recent call last):' }),
      '失敗: Ollama呼び出しに3回失敗: 404',
    ],
    // バックエンドは「例外の型名: 文言」で保存する。型名は利用者には意味が無い
    [
      '例外の型名は外す',
      p('failed', { error: 'RuntimeError: Ollama呼び出しに3回失敗: 404\n  File ...' }),
      '失敗: Ollama呼び出しに3回失敗: 404',
    ],
    [
      '型名でないコロンは残す',
      p('failed', { error: '書き出し: ffmpegが見つかりません' }),
      '失敗: 書き出し: ffmpegが見つかりません',
    ],
    ['失敗の文言が無くても失敗と分かる', p('failed'), '失敗しました'],
    ['中止', p('cancelled'), '中止しました'],
  ] as const)('%s', (_, progress, expected) => {
    expect(jobStatusText(progress, labels)).toBe(expected)
  })
})

describe('jobResultMessage(完了時の結果の説明)', () => {
  // 0件で「完了」とだけ出ると、動いたのか・何を探したのかが分からない(評価での指摘)。
  // バックエンドが result.message に説明を入れる(backend/pipeline/job_summary.py)
  const base = { progress: 1, phase: null, error: null }
  it.each([
    [
      '完了して説明があれば出す',
      { ...base, status: 'completed', result: { found: 0, message: '見つかりませんでした' } },
      '見つかりませんでした',
    ],
    ['説明が無い結果(書き出しの出力先等)は出さない', { ...base, status: 'completed', result: { path: '/x.mp4' } }, null],
    ['結果が無ければ出さない', { ...base, status: 'completed', result: null }, null],
    ['完了前は出さない', { ...base, status: 'running', result: { message: '途中' } }, null],
    ['空文字は出さない', { ...base, status: 'completed', result: { message: '' } }, null],
  ] as const)('%s', (_, progress, expected) => {
    expect(jobResultMessage(progress)).toBe(expected)
  })
})
