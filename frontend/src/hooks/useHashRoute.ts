/**
 * 最小のハッシュルーティング。ページ3枚(ホーム/エディタ/全体の設定)にライブラリは不要。
 *   #/            → { page: 'home' }
 *   #/media/3     → { page: 'editor', mediaId: 3 }
 *   #/settings    → { page: 'settings' }
 */
import { useEffect, useState } from 'react'

export type Route = { page: 'home' } | { page: 'editor'; mediaId: number } | { page: 'settings' }

export function parseHash(hash: string): Route {
  const m = hash.match(/^#\/media\/(\d+)/)
  if (m) return { page: 'editor', mediaId: Number(m[1]) }
  if (/^#\/settings\/?$/.test(hash)) return { page: 'settings' }
  return { page: 'home' }
}

export function toHash(route: Route): string {
  if (route.page === 'editor') return `#/media/${route.mediaId}`
  if (route.page === 'settings') return '#/settings'
  return '#/'
}

export function navigate(route: Route) {
  window.location.hash = toHash(route)
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
