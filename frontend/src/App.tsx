import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'

export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects })

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-bold">Attention Subtitle Separate Application</h1>
      <p className="mt-2 text-neutral-500">
        自動切り抜き動画作成アプリ(UI実装はこれから)
      </p>

      <section className="mt-8 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="font-semibold">バックエンド接続</h2>
        <p data-testid="health" className="mt-1 text-sm">
          {health.isPending && '確認中...'}
          {health.isError && '接続できません(uvicorn を起動してください)'}
          {health.data && `接続OK (${health.data.status})`}
        </p>
      </section>

      <section className="mt-4 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="font-semibold">プロジェクト</h2>
        {projects.data?.length ? (
          <ul data-testid="projects" className="mt-2 list-disc pl-5 text-sm">
            {projects.data.map((p) => (
              <li key={p.id}>{p.name}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-neutral-500">まだありません</p>
        )}
      </section>
    </main>
  )
}
