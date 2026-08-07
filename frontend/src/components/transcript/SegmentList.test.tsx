import { render, screen, fireEvent } from '@testing-library/react'
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
})
