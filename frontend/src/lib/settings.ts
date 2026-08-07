/**
 * 設定の解決(グローバル既定 + プロジェクト差分)。
 *
 * backendの `resolve_settings`(backend/core/project_settings.py)と同じ規則。
 * プロジェクトは差分だけを持つので、未上書きの項目はグローバルに追従する。
 */
export type SettingsValues = Record<string, unknown>

export function resolveSettings(
  globalValues: SettingsValues | undefined,
  projectOverrides: SettingsValues | undefined,
): SettingsValues {
  return { ...(globalValues ?? {}), ...(projectOverrides ?? {}) }
}

/**
 * 差分(overrides)を編集するための SettingsFields 向けpropsを組み立てる。
 * 保存先(ローカルstate / API)だけが違う2つの呼び出し元で共用する。
 */
export function overrideProps(
  globalValues: SettingsValues | undefined,
  overrides: SettingsValues,
  save: (next: SettingsValues) => void,
) {
  return {
    values: resolveSettings(globalValues, overrides),
    overriddenKeys: new Set(Object.keys(overrides)),
    onSet: (key: string, value: unknown) => save({ ...overrides, [key]: value }),
    onReset: (key: string) => {
      const next = { ...overrides }
      delete next[key]
      save(next)
    },
  }
}
