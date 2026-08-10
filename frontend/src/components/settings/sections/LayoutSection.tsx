/** 縦横変換の設定(入力と出力の向きが違うときの埋め方)。 */
import { CONVERT_METHOD_LABELS } from '../../../lib/catalogs'
import { selectCls } from '../../ui'
import { Row, Section, resetButton, type SectionProps } from './common'

export function LayoutSection(props: SectionProps) {
  const { values: v, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)

  return (
    <Section title="レイアウト(縦横変換)">
      <Row label="変換方式">
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
      <p className="text-xs text-neutral-500">
        入力と出力の向きが違うとき(横→縦 等)の変換方法。クリップごとに上書きもできます。
      </p>
    </Section>
  )
}
