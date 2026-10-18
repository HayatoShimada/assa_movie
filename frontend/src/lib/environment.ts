/**
 * 実行環境パネルの表示文言(純関数)。
 *
 * 「h264_vaapi」のようなエンコーダ名だけを出しても、初めての人には
 * 何のことか分からなかった(評価での指摘)。何をする方式かを先に書き、
 * 正式名はカッコで添える(問い合わせのときに要るので消さない)。
 */

/** GPUの専用回路で書き出すエンコーダ */
const HARDWARE_ENCODERS = new Set([
  'h264_nvenc',
  'h264_qsv',
  'h264_amf',
  'h264_vaapi',
  'h264_videotoolbox',
])

export function encoderDescription(encoder: string | null): string {
  if (!encoder) return 'ソフトウェア'
  if (HARDWARE_ENCODERS.has(encoder)) return `GPUで高速に書き出します(${encoder})`
  if (encoder === 'h264_mf') return `Windows標準の方式で書き出します(${encoder})`
  return `CPUで書き出します(${encoder})`
}
