import { describe, expect, it } from 'vitest'
import { encoderDescription } from './environment'

describe('encoderDescription(書き出し方式の説明)', () => {
  it.each([
    ['h264_vaapi', 'GPUで高速に書き出します(h264_vaapi)'],
    ['h264_nvenc', 'GPUで高速に書き出します(h264_nvenc)'],
    ['h264_videotoolbox', 'GPUで高速に書き出します(h264_videotoolbox)'],
    ['h264_mf', 'Windows標準の方式で書き出します(h264_mf)'],
    ['libx264', 'CPUで書き出します(libx264)'],
    ['libopenh264', 'CPUで書き出します(libopenh264)'],
  ])('%s', (encoder, expected) => {
    expect(encoderDescription(encoder)).toBe(expected)
  })
})
