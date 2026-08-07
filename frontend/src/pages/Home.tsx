/** ホーム: プロジェクト・メディアの登録と、文字起こしジョブの投入・進捗表示。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Media, type Project } from '../api/client'
import { Button, Card, ProgressBar, formatTime } from '../components/ui'
import { useJobProgress } from '../hooks/useJobProgress'
import { navigate } from '../hooks/useHashRoute'

function MediaRow({ media }: { media: Media }) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | null>(null)
  const progress = useJobProgress(jobId, () => {
    queryClient.invalidateQueries({ queryKey: ['media', media.project_id] })
    queryClient.invalidateQueries({ queryKey: ['segments', media.id] })
  })

  const transcribe = useMutation({
    mutationFn: () => api.createJob(media.id, 'transcribe', { language: 'ja' }),
    onSuccess: (job) => setJobId(job.id),
  })

  const running = progress.status === 'running' || progress.status === 'queued'
  const name = media.path.split('/').pop()

  return (
    <li
      data-testid={`media-${media.id}`}
      className="flex items-center gap-3 border-b border-neutral-100 py-2 last:border-0 dark:border-neutral-800"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className="text-xs text-neutral-500">
          {media.duration ? formatTime(media.duration) : '長さ不明'} ・ {media.status}
        </p>
        {jobId !== null && progress.status !== 'idle' && (
          <div className="mt-1">
            <ProgressBar
              value={progress.progress}
              label={
                progress.status === 'failed'
                  ? `失敗: ${progress.error?.split('\n')[0] ?? ''}`
                  : progress.status === 'completed'
                    ? '文字起こし完了'
                    : `文字起こし中... ${Math.round(progress.progress * 100)}%`
              }
            />
          </div>
        )}
      </div>
      <Button
        variant="ghost"
        disabled={running || transcribe.isPending}
        onClick={() => transcribe.mutate()}
      >
        {media.status === 'transcribed' ? '再文字起こし' : '文字起こし'}
      </Button>
      <Button
        disabled={media.status !== 'transcribed'}
        onClick={() => navigate({ page: 'editor', mediaId: media.id })}
      >
        開く
      </Button>
    </li>
  )
}

function ProjectCard({ project }: { project: Project }) {
  const queryClient = useQueryClient()
  const media = useQuery({
    queryKey: ['media', project.id],
    queryFn: () => api.listMedia(project.id),
  })
  const [path, setPath] = useState('')
  const addMedia = useMutation({
    mutationFn: () => api.addMedia(project.id, path),
    onSuccess: () => {
      setPath('')
      queryClient.invalidateQueries({ queryKey: ['media', project.id] })
    },
  })

  return (
    <Card title={project.name}>
      {media.data?.length ? (
        <ul>
          {media.data.map((m) => (
            <MediaRow key={m.id} media={m} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-neutral-500">動画がまだありません</p>
      )}
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (path.trim()) addMedia.mutate()
        }}
      >
        <input
          className="flex-1 rounded-md border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="動画ファイルのパス(例: /home/user/対談.mov)"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <Button type="submit" variant="ghost" disabled={addMedia.isPending}>
          動画を追加
        </Button>
      </form>
      {addMedia.isError && (
        <p className="mt-1 text-xs text-red-600">{String(addMedia.error.message)}</p>
      )}
    </Card>
  )
}

export function Home() {
  const queryClient = useQueryClient()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects })
  const [name, setName] = useState('')
  const create = useMutation({
    mutationFn: () => api.createProject(name),
    onSuccess: () => {
      setName('')
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-xl font-bold">Attention Subtitle Separate Application</h1>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (name.trim()) create.mutate()
        }}
      >
        <input
          data-testid="new-project-name"
          className="flex-1 rounded-md border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="新しいプロジェクト名"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button type="submit" disabled={create.isPending}>
          作成
        </Button>
      </form>

      {projects.isError && (
        <p className="text-sm text-red-600">
          バックエンドに接続できません。`./dev.sh api` で起動してください。
        </p>
      )}
      {projects.data?.map((p) => <ProjectCard key={p.id} project={p} />)}
      {projects.data?.length === 0 && (
        <p className="text-sm text-neutral-500">プロジェクトを作成して動画を追加してください。</p>
      )}
    </main>
  )
}
