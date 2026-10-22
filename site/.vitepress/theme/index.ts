import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import { toLegacyRedirectPath } from '../locale-paths.mts'
import './custom.css'

// 옛 URL(/en/*, /CLI 등) > 새 URL 이동 (#976)
// GitHub Pages 는 서버 리다이렉트가 없어 없는 경로는 404.html 로 들어온다 > 여기서 바꿔 준다 (해시 유지)
function redirectLegacyUrl() {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  const { pathname, search, hash } = window.location
  if (!pathname.startsWith(base)) return
  const target = toLegacyRedirectPath(pathname.slice(base.length) || '/')
  if (target) window.location.replace(`${base}${target}${search}${hash}`)
}

export default {
  extends: DefaultTheme,
  enhanceApp() {
    if (typeof window !== 'undefined') redirectLegacyUrl()
  },
} satisfies Theme
