export type Project = { id: string; name: string; settings: Record<string, unknown>; created_at: string; updated_at: string }
export type Asset = {
  id: string; project_id: string; type: 'video' | 'tts_audio' | 'external_audio' | 'output'
  display_name: string; relative_path: string; thumbnail_path?: string | null; duration_ms?: number | null
  width?: number | null; height?: number | null; fps?: number | null; codec?: string | null
  has_audio: boolean; metadata_json: Record<string, unknown>; created_at: string
  video_batch_name?: string | null
}
export type SequenceItem = { id: string; asset_id: string; position: number; asset: Asset }
export type VideoSequence = { id: string; project_id: string; name: string; batch_name: string; enabled: boolean; items: SequenceItem[]; created_at: string }
export type Job = {
  id: string; project_id: string; kind: string; status: string; progress: number
  input_json: Record<string, unknown>; output_asset_id?: string | null; error_message?: string | null
  log_path?: string | null; created_at: string; updated_at: string
}
