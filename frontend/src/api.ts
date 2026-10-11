const API = '/api'

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      message = body.detail || message
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
export const thumbnailUrl = (assetId: string) => `${API}/assets/${assetId}/thumbnail`
export const bgmStreamUrl = (trackId: string) => `${API}/bgm/${trackId}/stream`
