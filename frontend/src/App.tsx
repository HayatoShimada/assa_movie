import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import { SetupWizard } from './components/setup/SetupWizard'
import { Editor } from './pages/Editor'
import { Home } from './pages/Home'
import { useHashRoute } from './hooks/useHashRoute'

export default function App() {
  const route = useHashRoute()
  // 初回はウィザードを重ねて出す。済ませたかどうかは設定として持っているので、
  // 設定タブの「やり直す」で false に戻せば何度でも開く
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const needsSetup = settings.data?.values?.setup_completed === false

  return (
    <>
      {route.page === 'editor' ? <Editor mediaId={route.mediaId} /> : <Home />}
      {needsSetup && <SetupWizard />}
    </>
  )
}
