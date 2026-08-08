/**
 * バックエンドのOpenAPIスキーマから型定義を生成する。
 *
 * サーバーが起動していればHTTPから、していなければFastAPIアプリを直接importして
 * スキーマを書き出す(uvが必要)。生成先: src/api/schema.d.ts
 */
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../..')
const outFile = resolve(here, '../src/api/schema.d.ts')
const schemaFile = resolve(here, '../.openapi.json')

const API_URL = process.env.API_URL ?? 'http://localhost:8000'

async function fetchSchema() {
  try {
    const res = await fetch(`${API_URL}/openapi.json`, { signal: AbortSignal.timeout(2000) })
    if (res.ok) {
      console.log(`OpenAPIを取得: ${API_URL}`)
      return JSON.stringify(await res.json())
    }
  } catch {
    // サーバー未起動 → 直接生成にフォールバック
  }
  console.log('サーバー未起動のためFastAPIアプリから直接生成します')
  return execFileSync(
    'uv',
    ['run', 'python', '-c', 'import json,backend.app as a;print(json.dumps(a.app.openapi()))'],
    { cwd: repoRoot, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 },
  )
}

const schema = await fetchSchema()
writeFileSync(schemaFile, schema) // 中身を確かめたいとき用に残す
mkdirSync(dirname(outFile), { recursive: true })

// CLIではなくNode APIを使い、スキーマをオブジェクトのまま渡す。
// CLIに渡すとファイルパスをURLに変換する過程で、非ASCIIを含むパス
// (例: OneDrive\ドキュメント)が壊れてENOENTになる。またWindowsでは
// npxの実体が npx.cmd で、Node 20以降はシェル無しに起動できない(EINVAL)。
// オブジェクトを直接渡せば、パスもシェルも介さない
const ast = await openapiTS(JSON.parse(schema))
writeFileSync(outFile, astToString(ast))
console.log(`生成しました: ${outFile}`)
