import { beginActivity, finishActivity } from './activity'

const API = '/api'
const inFlight = new Map<string, Promise<unknown>>()
const fileIds = new WeakMap<Blob, number>()
let fileSequence = 0

function bodyKey(body?: BodyInit | null): string | null {
  if (!body || typeof body === 'string') return body || ''
  if (!(body instanceof FormData)) return null
  return JSON.stringify(Array.from(body.entries()).map(([key, value]) => {
    if (typeof value === 'string') return [key, value]
    if (!fileIds.has(value)) fileIds.set(value, ++fileSequence)
    return [key, fileIds.get(value)]
  }))
}

function actionLabel(path: string): string {
  if (path.includes('/tts/excel-jobs')) return 'Nhập Excel và thêm lồng tiếng'
  if (path.includes('/render/jobs')) return 'Thêm video vào hàng chờ render'
  if (path.includes('/tts/jobs')) return 'Thêm lồng tiếng vào hàng chờ'
  if (path.includes('/assets/import')) return 'Nhập file media'
  if (path.includes('/bgm/upload')) return 'Thêm nhạc nền'
  if (path.includes('/scripts/generate')) return 'Tạo kịch bản'
  if (path.includes('/sequences/generate')) return 'Tạo batch video'
  if (path.endsWith('/cancel')) return 'Hủy tác vụ'
  if (path.endsWith('/retry')) return 'Thử lại tác vụ'
  if (path.includes('/audio/') && path.endsWith('jobs')) return 'Thêm chỉnh sửa audio vào hàng chờ'
  if (path.includes('/tts/preview')) return 'Chuẩn bị mẫu nghe thử'
  if (path.includes('/tts/voices/clone')) return 'Clone và lưu giọng'
  return 'Lưu thay đổi'
}

export function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || 'GET').toUpperCase()
  const mutation = method !== 'GET' && method !== 'HEAD'
  const body = bodyKey(options?.body)
  const key = !options?.signal && body !== null ? JSON.stringify([method, path, body]) : null
  const existing = key ? inFlight.get(key) : undefined
  if (existing) return existing as Promise<T>
  const activityId = mutation ? beginActivity(actionLabel(path)) : null
  const operation = performRequest<T>(path, options).then(result => {
    if (mutation) {
      // Publish accepted jobs immediately; don't wait for the next SSE poll.
      const rows = Array.isArray(result) ? result : [result]
      const jobs = rows.filter(item => item && typeof item === 'object' && 'kind' in item && 'status' in item && 'project_id' in item)
      if (jobs.length) window.dispatchEvent(new CustomEvent('jobs-accepted', { detail: jobs }))
      if (activityId !== null) finishActivity(activityId, 'success', jobs.length
        ? `Đã tiếp nhận ${jobs.length} tác vụ. Server sẽ xử lý trong nền.` : 'Đã hoàn tất.')
    }
    return result
  }).catch(error => {
    if (activityId !== null) finishActivity(activityId, 'error', error instanceof Error ? error.message : String(error))
    throw error
  }).finally(() => { if (key) inFlight.delete(key) })
  if (key) inFlight.set(key, operation)
  return operation
}

async function performRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      message = typeof body.detail === 'string' ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((item: { msg?: string }) => item.msg || 'Dữ liệu không hợp lệ').join('; ') : message
    } catch { /* response is not JSON */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const jsonOptions = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const streamUrl = (assetId: string) => `${API}/assets/${assetId}/stream`
export const downloadUrl = (assetId: string) => `${API}/assets/${assetId}/download`
// Refresh legacy thumbnails that may have captured a black opening frame.
export const thumbnailUrl = (assetId: string) => `${API}/assets/${assetId}/thumbnail?v=2`
export const bgmStreamUrl = (trackId: string) => `${API}/bgm/${trackId}/stream`
