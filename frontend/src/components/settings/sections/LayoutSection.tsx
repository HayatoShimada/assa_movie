/** 縦横変換の設定(入力と出力の向きが違うときの埋め方)。基本の項目。 */
import { CONVERT_METHOD_LABELS } from '../../../lib/catalogs'
import { selectCls } from '../../ui'
import { Row, Section, resetButton, showTier, type SectionProps } from './common'

export function LayoutSection(props: SectionProps) {
  const { values: v, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  if (!showTier(props, 'basic')) return null

  return (
    <Section title="レイアウト(縦横変換)">
      <Row
        label="変換方式"
        hint="横の動画を縦で書き出すときなど、向きが違うときの埋め方。クリップごとに上書きもできます。"
      >
        <span>
          <select
            data-testid={`${idPrefix}-convert-method`}
            className={selectCls}
            value={String(v.convert_method ?? 'blur_pad')}
            onChange={(e) => set('convert_method')(e.target.value)}
          >
            {Object.entries(CONVERT_METHOD_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
          {resetButton(props, 'convert_method')}
        </span>
      </Row>
    </Section>
  )
}
