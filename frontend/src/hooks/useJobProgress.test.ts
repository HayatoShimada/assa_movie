import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '../api/client'

// SSEとAPIを差し替える。切断(onError)を任意の時点で起こせるようにする
const handlers: { onProgress?: (job: Job) => void; onError?: () => void }[] = []
const getJob = vi.fn<(id: number) => Promise<Job>>()

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: { ...actual.api, getJob: (id: number) => getJob(id) },
    subscribeJob: (_id: number, onProgress: (job: Job) => void, onError?: () => void) => {
      handlers.push({ onProgress, onError })
      return () => {}
    },
  }
})

const { useJobProgress } = await import('./useJobProgress')

function job(status: string, extra: Partial<Job> = {}): Job {
  return { id: 1, type: 'attention', media_id: 1, status, progress: 0.2, created_at: '', ...extra }
}

describe('useJobProgress(SSEが切れたとき)', () => {
  beforeEach(() => {
    handlers.length = 0
    getJob.mockReset()
    vi.useRealTimers()
  })

  it('切れたらジョブを取り直し、失敗していれば失敗を出す(「〜中」のまま固まらない)', async () => {
    const onDone = vi.fn()
    getJob.mockResolvedValue(job('failed', { error: 'Ollama呼び出しに3回失敗: 404' }))
    const { result } = renderHook(() => useJobProgress(1, onDone))

    act(() => handlers[0].onProgress?.(job('running')))
    expect(result.current.status).toBe('running')

    act(() => handlers[0].onError?.())
    await waitFor(() => expect(result.current.status).toBe('failed'))
    expect(result.current.error).toBe('Ollama呼び出しに3回失敗: 404')
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('取り直してもまだ実行中なら購読し直す', async () => {
    vi.useFakeTimers()
    getJob.mockResolvedValue(job('running', { progress: 0.5 }))
    const { result } = renderHook(() => useJobProgress(1))

    await act(async () => {
      handlers[0].onError?.()
      await Promise.resolve()
    })
    expect(result.current.progress).toBe(0.5)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(handlers.length).toBe(2)
  })
})
