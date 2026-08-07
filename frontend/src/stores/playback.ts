/**
 * 再生状態のストア。
 *
 * 再生位置は動画のtimeupdate(約4Hz)で更新される。将来60fps追従が必要になったら
 * ここをtransient update(購読ベース)に切り替える(FRONTEND_DESIGN.md参照)。
 */
import { create } from 'zustand'

interface PlaybackState {
  currentTime: number
  setCurrentTime: (t: number) => void
  /** VideoPlayerが登録するシーク関数。リストのクリックから呼ぶ */
  seeker: ((t: number) => void) | null
  setSeeker: (fn: ((t: number) => void) | null) => void
  seekTo: (t: number) => void
  selectedSegmentId: number | null
  selectSegment: (id: number | null) => void
}

export const usePlayback = create<PlaybackState>((set, get) => ({
  currentTime: 0,
  setCurrentTime: (t) => set({ currentTime: t }),
  seeker: null,
  setSeeker: (fn) => set({ seeker: fn }),
  seekTo: (t) => {
    get().seeker?.(t)
    set({ currentTime: t })
  },
  selectedSegmentId: null,
  selectSegment: (id) => set({ selectedSegmentId: id }),
}))
