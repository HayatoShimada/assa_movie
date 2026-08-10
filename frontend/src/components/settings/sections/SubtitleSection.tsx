/** 字幕の見た目と採否の設定。 */
import { useQuery } from '@tanstack/react-query'
import { api, machineQueryOptions } from '../../../api/client'
import { BASE_RES_X } from '../../../lib/subtitleLayout'
import { selectCls } from '../../ui'
import { Row, Section, resetButton, type SectionProps } from './common'

/** これ未満は縦動画(1080px幅)で1桁pxになり読めない(1920px幅基準の値) */
const MIN_READABLE_FONT_SIZE = 20

export function SubtitleSection(props: SectionProps) {
  const { values: v, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const fonts = useQuery({ queryKey: ['fonts'], queryFn: api.getFonts, ...machineQueryOptions })
  // 字幕サイズは1920px幅基準の値。実際の見え方は「画面幅の何%か」で決まる
  const fontRatioPct = (Number(v.subtitle_font_size ?? 48) / BASE_RES_X) * 100

  return (
    <Section title="字幕">
      {/* 採否は「字幕の取捨選択」ジョブが決める。ここはその採用率の閾値 */}
      <Row label={`採用率 ${Math.round(Number(v.subtitle_adoption_rate) * 100)}%`}>
        <input
          data-testid={`${idPrefix}-subtitle-adoption-rate`}
          type="range"
          min={0.1}
          max={1}
          step={0.05}
          defaultValue={Number(v.subtitle_adoption_rate)}
          onMouseUp={(e) =>
            set('subtitle_adoption_rate')(Number((e.target as HTMLInputElement).value))
          }
        />
      </Row>
      <Row label="フォント">
        <span>
          <select
            data-testid={`${idPrefix}-subtitle-font-family`}
            className={`${selectCls} max-w-52`}
            value={String(v.subtitle_font_family ?? 'Noto Sans JP')}
            onChange={(e) => set('subtitle_font_family')(e.target.value)}
          >
            {(fonts.data?.fonts ?? ['Noto Sans JP']).map((f) => (
              <option key={f} value={f} style={{ fontFamily: f }}>
                {f}
              </option>
            ))}
          </select>
          {resetButton(props, 'subtitle_font_family')}
        </span>
      </Row>
      <Row label={`字幕サイズ: ${v.subtitle_font_size}px(画面幅の${fontRatioPct.toFixed(1)}%)`}>
        <input
          data-testid={`${idPrefix}-subtitle-font-size`}
          type="range"
          // 値は1920px幅基準。これ未満は縦動画(1080px幅)で数pxになり読めない
          min={MIN_READABLE_FONT_SIZE}
          max={96}
          step={1}
          value={Number(v.subtitle_font_size ?? 48)}
          onChange={(e) => set('subtitle_font_size')(Number(e.target.value))}
        />
      </Row>
      {Number(v.subtitle_font_size ?? 48) < MIN_READABLE_FONT_SIZE && (
        <p data-testid={`${idPrefix}-subtitle-font-size-warning`} className="text-xs text-amber-600">
          ⚠ 小さすぎます。書き出すと縦動画で約
          {Math.round((Number(v.subtitle_font_size) * 1080) / 1920)}px になり、ほぼ見えません。
          {MIN_READABLE_FONT_SIZE}以上にしてください。
        </p>
      )}
      <Row label="文字色">
        <span className="flex items-center gap-1">
          <input
            data-testid={`${idPrefix}-subtitle-text-color`}
            type="color"
            // color入力はドラッグ中も連続でchangeが飛ぶため、確定時にだけ保存する
            defaultValue={String(v.subtitle_text_color ?? '#FFFFFF')}
            onBlur={(e) => set('subtitle_text_color')(e.target.value.toUpperCase())}
          />
          {resetButton(props, 'subtitle_text_color')}
        </span>
      </Row>
      <Row label="話者ごとの色分け">
        <input
          type="checkbox"
          checked={Boolean(v.subtitle_speaker_colors ?? true)}
          onChange={(e) => set('subtitle_speaker_colors')(e.target.checked)}
        />
      </Row>
      <Row label="背景">
        <span>
          <select
            data-testid={`${idPrefix}-subtitle-bg`}
            className={selectCls}
            value={String(v.subtitle_bg ?? 'none')}
            onChange={(e) => set('subtitle_bg')(e.target.value)}
          >
            <option value="none">なし(縁取りのみ)</option>
            <option value="box">背景ボックス</option>
          </select>
          {resetButton(props, 'subtitle_bg')}
        </span>
      </Row>
      {v.subtitle_bg === 'box' && (
        <>
          <Row label="背景色">
            <input
              data-testid={`${idPrefix}-subtitle-bg-color`}
              type="color"
              defaultValue={String(v.subtitle_bg_color ?? '#000000')}
              onBlur={(e) => set('subtitle_bg_color')(e.target.value.toUpperCase())}
            />
          </Row>
          <Row label={`背景の不透明度: ${Math.round(Number(v.subtitle_bg_opacity ?? 0.5) * 100)}%`}>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              defaultValue={Number(v.subtitle_bg_opacity ?? 0.5)}
              onMouseUp={(e) =>
                set('subtitle_bg_opacity')(Number((e.target as HTMLInputElement).value))
              }
            />
          </Row>
        </>
      )}
      <Row label="字幕位置(既定)">
        <select
          data-testid={`${idPrefix}-subtitle-position`}
          className={selectCls}
          value={String(v.subtitle_position ?? 'bottom')}
          onChange={(e) => set('subtitle_position')(e.target.value)}
        >
          <option value="top">上</option>
          <option value="center">中央</option>
          <option value="bottom">下</option>
        </select>
      </Row>
      <Row label={`字幕の上下微調整(既定): ${v.subtitle_offset_y ?? 0}px`}>
        <input
          data-testid={`${idPrefix}-subtitle-offset`}
          type="range"
          min={-120}
          max={120}
          step={1}
          defaultValue={Number(v.subtitle_offset_y ?? 0)}
          onMouseUp={(e) => set('subtitle_offset_y')(Number((e.target as HTMLInputElement).value))}
        />
      </Row>
      <Row label={`1行の最大文字数: ${v.subtitle_max_chars_per_line}`}>
        <input
          type="range"
          min={10}
          max={20}
          defaultValue={Number(v.subtitle_max_chars_per_line)}
          onMouseUp={(e) =>
            set('subtitle_max_chars_per_line')(Number((e.target as HTMLInputElement).value))
          }
        />
      </Row>
    </Section>
  )
}
