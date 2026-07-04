/**
 * GitHub Release 更新檢測服務
 * 跨平臺支持（Electron + Web）
 */

export interface ReleaseInfo {
  version: string
  name: string
  body: string // Release notes (Markdown)
  publishedAt: string
  htmlUrl: string
  downloadUrl?: string
}

export interface UpdateCheckResult {
  hasUpdate: boolean
  currentVersion: string
  latestVersion?: string
  releaseInfo?: ReleaseInfo
}

const GITHUB_REPO = 'RhythmicWave/NovelForge'
const GITHUB_API_BASE = 'https://api.github.com'
const REQUEST_TIMEOUT = 10000 // 10秒超時

/**
 * 從 package.json 獲取當前版本號
 */
export function getCurrentVersion(): string {
  // 在構建時，版本號會被注入到 import.meta.env
  // 如果沒有，則使用默認值
  return import.meta.env.VITE_APP_VERSION || '0.8.5'
}

/**
 * 比較版本號，支持諸如 0.8.5-fix2 這一類帶後綴的 tag。
 * 規則：
 *   1) 先比較數字主版本（按 x.y.z 拆分）；
 *   2) 若主版本相同，帶後綴的視爲高於無後綴（0.8.5-fix2 > 0.8.5）；
 *   3) 若雙方都有後綴，則嘗試解析尾部數字進行比較（fix2 > fix1），否則按字符串比較。
 * @returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal
 */
function compareVersions(v1: string, v2: string): number {
  const parseVersion = (v: string) => {
    const cleaned = v.replace(/^v/, '')
    const [core, suffixRaw] = cleaned.split('-', 2)
    const coreParts = core.split('.').map((s) => {
      const n = parseInt(s, 10)
      return Number.isNaN(n) ? 0 : n
    })
    return { coreParts, suffix: suffixRaw || '' }
  }

  const a = parseVersion(v1)
  const b = parseVersion(v2)

  // 1) 比較主版本號
  const maxLen = Math.max(a.coreParts.length, b.coreParts.length)
  for (let i = 0; i < maxLen; i++) {
    const num1 = a.coreParts[i] ?? 0
    const num2 = b.coreParts[i] ?? 0
    if (num1 > num2) return 1
    if (num1 < num2) return -1
  }

  // 2) 主版本相等時比較後綴
  if (a.suffix === b.suffix) return 0
  if (a.suffix && !b.suffix) return 1
  if (!a.suffix && b.suffix) return -1

  // 3) 雙方都有後綴，優先比較尾部數字
  const re = /^([a-zA-Z\-]*)(\d*)$/
  const ma = a.suffix.match(re)
  const mb = b.suffix.match(re)
  if (ma && mb) {
    const labelA = ma[1]
    const labelB = mb[1]
    const numA = ma[2] ? parseInt(ma[2], 10) : 0
    const numB = mb[2] ? parseInt(mb[2], 10) : 0
    if (labelA === labelB && (numA !== numB)) {
      return numA > numB ? 1 : -1
    }
  }

  // 4) 回退到純字符串比較
  if (a.suffix > b.suffix) return 1
  if (a.suffix < b.suffix) return -1
  return 0
}

/**
 * 帶超時的 fetch
 */
async function fetchWithTimeout(url: string, timeout: number): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'NovelForge-App'
      }
    })
    clearTimeout(timeoutId)
    return response
  } catch (error) {
    clearTimeout(timeoutId)
    throw error
  }
}

/**
 * 獲取最新的 GitHub Release
 */
async function fetchLatestRelease(timeout: number = REQUEST_TIMEOUT): Promise<ReleaseInfo | null> {
  const url = `${GITHUB_API_BASE}/repos/${GITHUB_REPO}/releases/latest`
  
  try {
    const response = await fetchWithTimeout(url, timeout)
    
    if (!response.ok) {
      // 對於 HTTP 錯誤，拋出異常而不是當成「沒有更新」，
      // 這樣上層可以給出明確的錯誤提示（例如 403 速率限制）。
      if (response.status === 403) {
        throw new Error('GitHub API 訪問受限 (403)，可能已達到未登錄用戶的速率限制，請稍後重試')
      }
      throw new Error(`GitHub API 返回錯誤: ${response.status}`)
    }
    
    const data = await response.json()
    
    return {
      version: data.tag_name?.replace(/^v/, '') || data.name,
      name: data.name || data.tag_name,
      body: data.body || '',
      publishedAt: data.published_at,
      htmlUrl: data.html_url,
      downloadUrl: data.assets?.[0]?.browser_download_url
    }
  } catch (error: any) {
    if (error.name === 'AbortError') {
      throw new Error('請求超時')
    }
    throw error
  }
}

/**
 * 檢查更新（帶重試機制）
 * @param maxRetries 最大重試次數（0 表示不重試）
 */
export async function checkForUpdates(maxRetries: number = 0): Promise<UpdateCheckResult> {
  const currentVersion = getCurrentVersion()
  let lastError: Error | null = null
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const releaseInfo = await fetchLatestRelease()
      
      if (!releaseInfo) {
        return {
          hasUpdate: false,
          currentVersion
        }
      }
      
      const hasUpdate = compareVersions(releaseInfo.version, currentVersion) > 0
      
      return {
        hasUpdate,
        currentVersion,
        latestVersion: releaseInfo.version,
        releaseInfo: hasUpdate ? releaseInfo : undefined
      }
    } catch (error: any) {
      lastError = error
      console.warn(`更新檢測失敗 (嘗試 ${attempt + 1}/${maxRetries + 1}):`, error.message)
      
      // 如果還有重試機會，等待一段時間後重試
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1)))
      }
    }
  }
  
  // 所有重試都失敗
  throw lastError || new Error('更新檢測失敗')
}

/**
 * 自動檢查更新（帶1次重試）
 */
export async function autoCheckForUpdates(): Promise<UpdateCheckResult> {
  return checkForUpdates(1)
}

/**
 * 手動檢查更新（不重試）
 */
export async function manualCheckForUpdates(): Promise<UpdateCheckResult> {
  return checkForUpdates(0)
}
