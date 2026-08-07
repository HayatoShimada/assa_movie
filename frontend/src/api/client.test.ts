import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './client'

function mockFetch(body: unknown, status = 200) {
  const spy = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    statusText: 'ERR',
    json: async () => body,
    text: async () => JSON.stringify(body),
  })
  vi.stubGlobal('fetch', spy)
  return spy
}

afterEach(() => vi.unstubAllGlobals())

describe('apiクライアント', () => {
  it('プロジェクト一覧を取得する', async () => {
    const spy = mockFetch([{ id: 1, name: 'p', created_at: 'x' }])
    const out = await api.listProjects()
    expect(out[0].name).toBe('p')
    expect(spy).toHaveBeenCalledWith('/api/projects', expect.objectContaining({}))
  })

  it('相槌除外のクエリを付ける', async () => {
    const spy = mockFetch([])
    await api.listSegments(3, false)
    expect(spy.mock.calls[0][0]).toBe('/api/media/3/segments?include_aizuchi=false')
  })

  it('PATCHでセグメントを更新する', async () => {
    const spy = mockFetch({ id: 1 })
    await api.updateSegment(1, { text: '修正' })
    const [, init] = spy.mock.calls[0]
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({ text: '修正' })
  })

  it('エラー応答をApiErrorにする', async () => {
    mockFetch({ detail: 'だめ' }, 400)
    await expect(api.acceptEdit(1)).rejects.toBeInstanceOf(ApiError)
  })

  it('ジョブ投入はtypeとparamsを送る', async () => {
    const spy = mockFetch({ id: 9 })
    await api.createJob(2, 'resolve', { level: 'strong' })
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('/api/media/2/jobs')
    expect(JSON.parse(init.body)).toEqual({ type: 'resolve', params: { level: 'strong' } })
  })
})
