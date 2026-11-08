import { useState } from 'react'
import { streamUrl, thumbnailUrl } from './api'
import type { Asset } from './types'

export function VideoThumbnail({ asset }: { asset: Asset }) {
  const [failedImage, setFailedImage] = useState('')
  return <div className="video-thumbnail" aria-label={`Ảnh đại diện: ${asset.display_name}`}>
    {failedImage !== asset.id
      ? <img src={thumbnailUrl(asset.id)} alt={asset.display_name} loading="lazy" decoding="async" draggable={false} onError={() => setFailedImage(asset.id)} />
      : <video src={`${streamUrl(asset.id)}#t=0.1`} preload="metadata" muted playsInline aria-label={asset.display_name} />}
  </div>
}
