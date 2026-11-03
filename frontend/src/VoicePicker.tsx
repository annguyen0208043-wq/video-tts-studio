import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AudioLines, Check, ChevronDown, FolderHeart, LoaderCircle, Pause, Pencil, Play, Plus, Search, Upload, X } from 'lucide-react'
import { jsonOptions, request } from './api'
import './voice-library.css'

type Voice = { id: string; label: string; custom?: boolean; preview_url?: string | null }
type Props = { device: string; value: string; onChange: (id: string) => void }
type LibraryTab = 'preset' | 'mine' | 'clone'
const SAMPLE = 'Xin chào, rất vui được gặp bạn hôm nay. Chúc bạn một ngày thật nhiều niềm vui và công việc luôn thuận lợi.'
const normalize = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase()
function parts(voice: Voice) {
  const [title, ...details] = voice.label.replace(/^⭐\s*/, '').split(' — ')
  return { title: voice.custom ? title.replace(/^Giọng clone · /, '') : title, details: details.join(' — '), featured: voice.label.startsWith('⭐') }
}

export function VoicePicker({ device, value, onChange }: Props) {
  const [voices, setVoices] = useState<Voice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<LibraryTab>('preset')
  const [search, setSearch] = useState('')
  const [gender, setGender] = useState('')
  const [region, setRegion] = useState('')
  const [playing, setPlaying] = useState('')
  const [pendingVoice, setPendingVoice] = useState('')
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [cloning, setCloning] = useState(false)
  const [sourceUrl, setSourceUrl] = useState('')
  const [renaming, setRenaming] = useState('')
  const [renameName, setRenameName] = useState('')
  const [savingName, setSavingName] = useState(false)
  const audio = useRef<HTMLAudioElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const searchInput = useRef<HTMLInputElement>(null)
  const sourceAudio = useRef<HTMLAudioElement>(null)
  const playRequest = useRef(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const selected = useRef(value)
  selected.current = value

  useEffect(() => {
    let alive = true
    setLoading(true); setError('')
    request<Voice[]>(`/system/tts/voices?device=${device}`).then(items => {
      if (!alive) return
      setVoices(items)
      if (!items.some(item => item.id === selected.current)) onChange(items[0]?.id || '')
    }).catch(err => { if (alive) setError(String(err.message || err)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [device, onChange])

  function stopAudio() {
    playRequest.current++; audio.current?.pause(); setPlaying(''); setPendingVoice('')
  }

  useEffect(() => { stopAudio() }, [device])
  useEffect(() => {
    if (open) { dialog.current?.showModal(); searchInput.current?.focus() }
    else dialog.current?.close()
  }, [open])
  useEffect(() => {
    if (!file) { setSourceUrl(''); return }
    const url = URL.createObjectURL(file)
    setSourceUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  useEffect(() => () => { playRequest.current++ }, [])

  function closeLibrary() {
    if (cloning || savingName) return
    stopAudio(); sourceAudio.current?.pause(); setOpen(false); trigger.current?.focus()
  }

  function openLibrary(nextTab: LibraryTab) {
    setTab(nextTab); setSearch(''); setGender(''); setRegion(''); setError(''); setNotice(''); setRenaming(''); setOpen(true)
  }

  function changeTab(nextTab: LibraryTab) {
    stopAudio(); sourceAudio.current?.pause(); setTab(nextTab); setSearch(''); setGender(''); setRegion(''); setRenaming(''); setError('')
  }

  async function listen(voiceId: string) {
    const player = audio.current
    if (!player) return
    if (playing === voiceId) { stopAudio(); return }
    const token = ++playRequest.current
    player.pause(); sourceAudio.current?.pause(); setPlaying(''); setError(''); setPendingVoice(voiceId)
    try {
      let url = voices.find(item => item.id === voiceId)?.preview_url
      if (!url) {
        const result = await request<{ audio_url: string }>('/system/tts/preview', jsonOptions('POST', { voice: voiceId, device }))
        url = result.audio_url
        if (playRequest.current !== token) return
        setVoices(items => items.map(item => item.id === voiceId ? { ...item, preview_url: url } : item))
      }
      if (playRequest.current !== token) return
      player.src = url
      await player.play()
      if (playRequest.current === token) setPlaying(voiceId)
    } catch (err) { if (playRequest.current === token) setError(err instanceof Error ? err.message : String(err)) }
    finally { if (playRequest.current === token) setPendingVoice('') }
  }

  async function clone() {
    if (!file || !name.trim() || cloning) return
    setCloning(true); setError(''); stopAudio(); sourceAudio.current?.pause()
    try {
      const form = new FormData()
      form.append('name', name.trim()); form.append('device', device); form.append('upload', file)
      const voice = await request<Voice>('/system/tts/voices/clone', { method: 'POST', body: form })
      setVoices(items => [...items, voice]); setTab('mine'); setSearch(''); setName(''); setFile(null)
      setNotice(`Đã lưu “${parts(voice).title}” vào Giọng của tôi. Bạn có thể nghe thử hoặc bấm Sử dụng.`)
      if (fileInput.current) fileInput.current.value = ''
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setCloning(false) }
  }

  async function saveName(id: string) {
    if (!renameName.trim() || savingName) return
    setSavingName(true); setError('')
    try {
      const updated = await request<Voice>(`/system/tts/voices/${encodeURIComponent(id)}`, jsonOptions('PATCH', { name: renameName.trim() }))
      setVoices(items => items.map(item => item.id === id ? updated : item)); setRenaming(''); setNotice('Đã lưu tên giọng mới.')
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setSavingName(false) }
  }

  const mine = voices.filter(item => item.custom)
  const current = voices.find(item => item.id === value)
  const filtered = voices.filter(item => !!item.custom === (tab === 'mine') && normalize(item.label).includes(normalize(search))
    && (!gender || parts(item).details.split(' · ')[0] === gender)
    && (!region || parts(item).details.split(' · ')[1] === region))

  return <div className="voice-picker">
    <label id="tts-voice-label">Giọng đọc</label>
    <button ref={trigger} type="button" className="voice-library-trigger" disabled={loading || cloning}
      aria-labelledby="tts-voice-label tts-voice-value" aria-haspopup="dialog" onClick={() => openLibrary(current?.custom ? 'mine' : 'preset')}>
      <span className="voice-library-avatar"><AudioLines size={21} /></span>
      <span id="tts-voice-value"><strong>{loading ? 'Đang tải giọng...' : current ? parts(current).title : 'Chọn giọng đọc'}</strong><small>{current ? parts(current).details || 'Đã lưu trong Giọng của tôi' : 'Mở thư viện để nghe thử và chọn giọng'}</small></span>
      <span className="voice-library-change">Đổi giọng <ChevronDown size={15} /></span>
    </button>
    <div className="voice-library-shortcuts"><button type="button" onClick={() => openLibrary('mine')}><FolderHeart size={15} />Giọng của tôi <span>{mine.length}</span></button><button type="button" onClick={() => openLibrary('clone')}><Plus size={15} />Clone giọng mới</button></div>
    <audio ref={audio} hidden onEnded={() => setPlaying('')} onPause={() => setPlaying('')} onError={() => { setPlaying(''); setError('Không phát được bản nghe thử. Hãy thử lại.') }} />
    {!open && error && <p className="voice-picker-error" role="alert">{error}</p>}
    {createPortal(<dialog ref={dialog} className="voice-library-dialog" aria-labelledby="voice-library-title" onCancel={event => { event.preventDefault(); closeLibrary() }} onClick={event => { if (event.target === event.currentTarget) closeLibrary() }}>
      <div className="voice-library-shell">
        <div className="voice-library-header"><div><span className="voice-library-eyebrow">VIDEO TTS STUDIO</span><h2 id="voice-library-title">Thư viện giọng đọc</h2><p>Nghe thử, chọn giọng phù hợp hoặc tạo giọng riêng của bạn.</p></div><button type="button" className="vl-icon" aria-label="Đóng thư viện giọng" disabled={cloning || savingName} onClick={closeLibrary}><X size={21} /></button></div>
        <div className="voice-library-tabs" role="tablist" aria-label="Kho giọng">
          {([['preset', 'Giọng có sẵn', voices.length - mine.length], ['mine', 'Giọng của tôi', mine.length], ['clone', 'Clone giọng mới', null]] as const).map(([id, label, count]) => <button type="button" role="tab" aria-selected={tab === id} aria-controls="voice-library-content" id={`voice-tab-${id}`} key={id} disabled={cloning || savingName} onClick={() => changeTab(id)}>{id === 'clone' && <Plus size={16} />}{label}{count !== null && <span>{count}</span>}</button>)}
        </div>
        <div className="voice-library-content" id="voice-library-content" role="tabpanel" aria-labelledby={`voice-tab-${tab}`}>
          {notice && <div className="vl-notice" role="status"><Check size={17} />{notice}</div>}
          {error && <div className="vl-error" role="alert">{error}</div>}
          {tab !== 'clone' ? <>
            <div className="voice-library-toolbar"><div className="vl-search"><Search size={18} /><input ref={searchInput} aria-label="Tìm giọng" placeholder={tab === 'mine' ? 'Tìm giọng theo tên bạn đã đặt...' : 'Tìm tên giọng, phong cách đọc...'} value={search} onChange={e => setSearch(e.target.value)} /></div>{tab === 'preset' && <><select aria-label="Lọc giới tính" value={gender} onChange={e => setGender(e.target.value)}><option value="">Tất cả giới tính</option><option>Nam</option><option>Nữ</option></select><select aria-label="Lọc vùng miền" value={region} onChange={e => setRegion(e.target.value)}><option value="">Tất cả vùng miền</option><option value="Bắc">Miền Bắc</option><option value="Trung">Miền Trung</option><option value="Nam">Miền Nam</option></select></>}</div>
            <div className="vl-list-heading"><div><h3>{tab === 'mine' ? 'Giọng của tôi' : 'Giọng có sẵn'}</h3><p>{tab === 'mine' ? 'Giọng clone được lưu riêng và dùng lại trong mọi dự án.' : 'Bấm nút phát để nghe mẫu. Bấm Sử dụng để chọn giọng.'}</p></div><span>{filtered.length} giọng</span></div>
            <div className="voice-library-list">
              {filtered.map(item => { const info = parts(item), active = playing === item.id, pending = pendingVoice === item.id; return <div key={item.id} className={`vl-row ${value === item.id ? 'selected' : ''} ${active ? 'playing' : ''}`}>
                <button type="button" className="vl-audition" disabled={pending || cloning} aria-label={`${active ? 'Dừng nghe' : 'Nghe thử'} ${info.title}`} title={active ? 'Dừng nghe thử' : 'Nghe thử 2 câu tiếng Việt'} onClick={() => void listen(item.id)}>{pending ? <LoaderCircle size={20} className="spin" /> : active ? <Pause size={20} /> : <Play size={20} />}</button>
                <div className="vl-row-info">{renaming === item.id ? <form className="vl-rename" onSubmit={event => { event.preventDefault(); void saveName(item.id) }}><input autoFocus aria-label="Tên giọng mới" maxLength={100} value={renameName} disabled={savingName} onChange={e => setRenameName(e.target.value)} /><button type="submit" disabled={savingName || !renameName.trim()}>{savingName ? 'Đang lưu...' : 'Lưu tên'}</button><button type="button" className="vl-quiet" disabled={savingName} onClick={() => setRenaming('')}>Hủy</button></form> : <><strong>{info.title}{info.featured && <span className="vl-recommended">Nổi bật</span>}</strong><small>{item.custom ? 'Giọng clone · Đã lưu trong thư viện riêng' : info.details}</small></>}</div>
                <span className="vl-language">Tiếng Việt<small>{item.custom ? 'Giọng của bạn' : info.details.split(' · ')[1] ? `Miền ${info.details.split(' · ')[1]}` : 'VieNeu TTS'}</small></span>
                {item.custom && <button type="button" className="vl-icon vl-rename-button" aria-label={`Đổi tên ${info.title}`} title="Đổi tên giọng" disabled={savingName} onClick={() => { setRenaming(item.id); setRenameName(info.title); setNotice('') }}><Pencil size={16} /></button>}
                <button type="button" className={`vl-use ${value === item.id ? 'chosen' : ''}`} disabled={savingName} onClick={() => { onChange(item.id); closeLibrary() }}>{value === item.id ? <><Check size={15} />Đang chọn</> : 'Sử dụng'}</button>
              </div> })}
              {!filtered.length && <div className="vl-empty"><FolderHeart size={36} /><h3>{tab === 'mine' && !mine.length ? 'Chưa có giọng riêng' : 'Không tìm thấy giọng'}</h3><p>{tab === 'mine' && !mine.length ? 'Tải audio mẫu và đặt một cái tên dễ nhớ. Giọng của bạn sẽ xuất hiện tại đây.' : 'Thử từ khóa khác hoặc bỏ bộ lọc để xem thêm giọng.'}</p>{tab === 'mine' && !mine.length && <button type="button" className="vl-primary" onClick={() => changeTab('clone')}><Plus size={16} />Tạo giọng đầu tiên</button>}</div>}
            </div>
          </> : <div className="vl-clone-layout"><div className="vl-clone-main"><h3>Clone và lưu giọng riêng</h3><p>Chỉ cần một đoạn audio rõ tiếng. Đặt tên để tìm lại dễ dàng trong Giọng của tôi.</p><label htmlFor="clone-name">1. Đặt tên giọng dễ nhớ</label><input id="clone-name" value={name} maxLength={100} disabled={cloning} onChange={e => setName(e.target.value)} placeholder="Ví dụ: Giọng mình · Review sản phẩm" /><small>Bạn có thể đổi tên bất cứ lúc nào sau khi lưu.</small><label htmlFor="clone-audio">2. Chọn audio mẫu</label><label className={`vl-upload ${cloning ? 'busy' : ''}`} htmlFor="clone-audio"><Upload size={25} /><strong>{file ? file.name : 'Bấm để chọn audio mẫu'}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · Bấm để đổi file` : 'WAV, MP3, M4A, FLAC, OGG, WebM · tối đa 20 MB'}</span></label><input id="clone-audio" ref={fileInput} type="file" hidden accept=".wav,.mp3,.m4a,.flac,.ogg,.webm" disabled={cloning} onChange={e => { const next = e.target.files?.[0] || null; if (next && next.size > 20 * 1024 * 1024) { setError('Audio mẫu không được vượt quá 20 MB'); e.target.value = ''; setFile(null); return } setError(''); setFile(next) }} />{sourceUrl && <audio ref={sourceAudio} controls src={sourceUrl} onPlay={stopAudio} />}<button type="button" className="vl-primary vl-save-clone" disabled={!file || !name.trim() || cloning} onClick={() => void clone()}>{cloning ? <LoaderCircle size={18} className="spin" /> : <FolderHeart size={18} />}{cloning ? 'Đang clone và lưu giọng...' : 'Clone và lưu vào Giọng của tôi'}</button>{cloning && <small role="status">Đang xử lý audio. Giọng sẽ xuất hiện trong thư viện khi hoàn tất.</small>}</div><aside className="vl-clone-tips"><span className="voice-library-avatar"><AudioLines size={26} /></span><h3>Mẫu tốt, giọng rõ</h3><p>Đoạn thu dài <b>3–30 giây</b>, chỉ có một người nói, ít tiếng ồn và không có nhạc nền.</p><hr /><h3>Lưu một lần, dùng nhiều lần</h3><p>Giọng được lưu riêng trong <b>Giọng của tôi</b>, dùng được ở mọi dự án và vẫn còn sau khi khởi động lại.</p><p className="vl-tip-example">Tên gợi ý<br /><b>Giọng mình · Kể chuyện</b><br /><b>Giọng chị Lan · Quảng cáo</b></p></aside></div>}
        </div>
        <div className="voice-library-footer">{tab === 'clone' ? <span><FolderHeart size={16} />Nơi lưu: Giọng của tôi</span> : <div><span><AudioLines size={16} />Mẫu nghe thử · 2 câu tiếng Việt</span><p>{SAMPLE}</p></div>}<button type="button" className="vl-close" disabled={cloning || savingName} onClick={closeLibrary}>Đóng</button></div>
      </div>
    </dialog>, document.body)}
  </div>
}
