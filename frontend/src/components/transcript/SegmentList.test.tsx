import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Segment } from '../../api/client'
import { usePlayback } from '../../stores/playback'
import { SegmentList } from './SegmentList'

function seg(idx: number, over: Partial<Segment> = {}): Segment {
  return {
    id: idx + 1,
    media_id: 1,
    idx,
    start: idx * 2,
    end: idx * 2 + 1.8,
    text: `話者A: セグメント${idx}`,
    original_text: `話者A: セグメント${idx}`,
    speaker: '話者A',
    is_aizuchi: false,
    edited_by_user: false,
    asr_confidence: null,
    subtitle_show: 'auto_show',
    words: [],
    ...over,
  }
}

// jsdomにはelementの実寸が無いため、仮想リストに全行を描画させる
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getTotalSize: () => count * 56,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({ index: i, start: i * 56, size: 56 })),
    scrollToIndex: vi.fn(),
    measureElement: () => {},
  }),
}))

describe('SegmentList', () => {
  beforeEach(() => {
    usePlayback.setState({ currentTime: 0, selectedSegmentId: null, seeker: null })
  })

  it('話者ラベルを外して本文を表示する', () => {
    render(<SegmentList segments={[seg(0)]} />)
    expect(screen.getByTestId('segment-0')).toHaveTextContent('セグメント0')
    expect(screen.getByTestId('segment-0')).not.toHaveTextContent('話者A: セグメント0')
  })

  it('相槌セグメントはグレー表示になる', () => {
    render(<SegmentList segments={[seg(0), seg(1, { is_aizuchi: true })]} />)
    expect(screen.getByTestId('segment-1').className).toContain('opacity-40')
    expect(screen.getByTestId('segment-0').className).not.toContain('opacity-40')
  })

  it('クリックでシークと選択が行われる', () => {
    const seeker = vi.fn()
    usePlayback.setState({ seeker })
    render(<SegmentList segments={[seg(0), seg(1)]} />)

    fireEvent.click(screen.getByTestId('segment-1'))
    expect(seeker).toHaveBeenCalledWith(2)
    expect(usePlayback.getState().selectedSegmentId).toBe(2)
  })

  it('再生位置のセグメントがハイライトされる', () => {
    usePlayback.setState({ currentTime: 2.5 }) // セグメント1の区間 [2, 3.8)
    render(<SegmentList segments={[seg(0), seg(1), seg(2)]} />)
    expect(screen.getByTestId('segment-1')).toHaveAttribute('data-active')
    expect(screen.getByTestId('segment-0')).not.toHaveAttribute('data-active')
  })

  it('ユーザー編集済みの印を表示する', () => {
    render(<SegmentList segments={[seg(0, { edited_by_user: true })]} />)
    expect(screen.getByTestId('segment-0')).toHaveTextContent('(編集済)')
  })

  // ---- 手直し(誤認識を手で直す・話者名を変える) ----
  it('鉛筆ボタンで編集欄が出て、保存すると前置きを付け直した本文で呼ばれる', async () => {
    const onSaveText = vi.fn().mockResolvedValue(undefined)
    render(<SegmentList segments={[seg(0, { text: '話者A: 腕駒の話' })]} onSaveText={onSaveText} />)

    fireEvent.click(screen.getByTestId('segment-edit-0'))
    const input = screen.getByTestId('segment-edit-input-0')
    expect(input).toHaveValue('腕駒の話')
    fireEvent.change(input, { target: { value: '腕前の話' } })
    fireEvent.click(screen.getByTestId('segment-edit-save-0'))

    await waitFor(() => expect(onSaveText).toHaveBeenCalledTimes(1))
    expect(onSaveText.mock.calls[0][1]).toBe('話者A: 腕前の話')
    await waitFor(() => expect(screen.queryByTestId('segment-editor-0')).toBeNull())
  })

  it('行のダブルクリックでも編集欄が出る。Escでやめると保存しない', () => {
    const onSaveText = vi.fn()
    render(<SegmentList segments={[seg(0)]} onSaveText={onSaveText} />)
    fireEvent.doubleClick(screen.getByTestId('segment-0'))
    const input = screen.getByTestId('segment-edit-input-0')
    fireEvent.change(input, { target: { value: '別の文' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByTestId('segment-editor-0')).toBeNull()
    expect(onSaveText).not.toHaveBeenCalled()
  })

  it('編集欄の中をクリックしても、行の選択・シークは起きない', () => {
    const seeker = vi.fn()
    usePlayback.setState({ seeker })
    render(<SegmentList segments={[seg(0), seg(1)]} onSaveText={vi.fn()} />)
    fireEvent.click(screen.getByTestId('segment-edit-1'))
    fireEvent.click(screen.getByTestId('segment-edit-input-1'))
    expect(seeker).not.toHaveBeenCalled()
  })

  it('空にはできない', () => {
    const onSaveText = vi.fn()
    render(<SegmentList segments={[seg(0)]} onSaveText={onSaveText} />)
    fireEvent.click(screen.getByTestId('segment-edit-0'))
    fireEvent.change(screen.getByTestId('segment-edit-input-0'), { target: { value: '  ' } })
    expect(screen.getByTestId('segment-edit-save-0')).toBeDisabled()
    expect(screen.getByText('空にはできません')).toBeInTheDocument()
  })

  it('手で直した行は「手直しを取り消す」で戻せる。原文も見える', async () => {
    const onRestore = vi.fn().mockResolvedValue(undefined)
    render(
      <SegmentList
        segments={[
          seg(0, {
            text: '話者A: 腕前の話',
            original_text: '話者A: 腕駒の話',
            edited_by_user: true,
          }),
        ]}
        onSaveText={vi.fn()}
        onRestore={onRestore}
      />,
    )
    fireEvent.click(screen.getByTestId('segment-edit-0'))
    expect(screen.getByTestId('segment-editor-0')).toHaveTextContent('原文: 腕駒の話')
    fireEvent.click(screen.getByTestId('segment-restore-0'))
    await waitFor(() => expect(onRestore).toHaveBeenCalledTimes(1))
  })

  it('保存に失敗したら理由を出し、編集欄は閉じない', async () => {
    const onSaveText = vi.fn().mockRejectedValue(new Error('保存できませんでした'))
    render(<SegmentList segments={[seg(0)]} onSaveText={onSaveText} />)
    fireEvent.click(screen.getByTestId('segment-edit-0'))
    fireEvent.change(screen.getByTestId('segment-edit-input-0'), { target: { value: '直した' } })
    fireEvent.click(screen.getByTestId('segment-edit-save-0'))
    expect(await screen.findByText('保存できませんでした')).toBeInTheDocument()
    expect(screen.getByTestId('segment-editor-0')).toBeInTheDocument()
  })

  it('話者名を押すとメニューが開き(行の選択は起きない)、名前を変えられる', async () => {
    const seeker = vi.fn()
    usePlayback.setState({ seeker })
    const onRenameSpeaker = vi.fn().mockResolvedValue(undefined)
    render(<SegmentList segments={[seg(0)]} onRenameSpeaker={onRenameSpeaker} />)

    fireEvent.click(screen.getByTestId('speaker-0'))
    expect(seeker).not.toHaveBeenCalled()
    fireEvent.change(screen.getByTestId('speaker-rename-input-0'), { target: { value: '山田' } })
    fireEvent.click(screen.getByTestId('speaker-rename-save-0'))
    await waitFor(() => expect(onRenameSpeaker).toHaveBeenCalledWith('話者A', '山田'))
  })

  it('この行だけ別の話者に付け替えられる', async () => {
    const onSetSpeaker = vi.fn().mockResolvedValue(undefined)
    render(
      <SegmentList
        segments={[seg(0), seg(1, { speaker: '話者B', text: '話者B: こんにちは' })]}
        onSetSpeaker={onSetSpeaker}
      />,
    )
    fireEvent.click(screen.getByTestId('speaker-0'))
    fireEvent.click(screen.getByTestId('speaker-assign-0-話者B'))
    await waitFor(() => expect(onSetSpeaker).toHaveBeenCalledTimes(1))
    expect(onSetSpeaker.mock.calls[0][1]).toBe('話者B')
  })
})
