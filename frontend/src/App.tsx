import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AudioLines, Bot, CheckCircle2, Clapperboard, Download, Eye, FolderOpen, Layers3,
  LoaderCircle, MousePointer2, Music, Pause, Play, Plus, RefreshCw, Scissors, Sparkles, Trash2,
  Upload, Volume2, VolumeX, Wand2, X, XCircle,
} from 'lucide-react'
import { bgmStreamUrl, jsonOptions, request, streamUrl, thumbnailUrl } from './api'
import type { AIProvider, AISkill, Asset, BgmTrack, GeneratedScript, Job, Project, ScriptGenerateResult, VideoSequence } from './types'

type Tab = 'media' | 'scripts' | 'voice' | 'sequence' | 'render' | 'jobs'
type SidebarState = 'open' | 'closed'
type Guard = (action: () => Promise<void>) => Promise<void>
type BatchDraft = { id: string; name: string; selected: string[]; mode: string; k: number; manual: string[] }
type Assignment = {
  audioId: string
  bgmId: string
  muteOriginal: boolean
  customName: string
  voiceVolume: number
  bgmVolume: number
}

let rememberedDownloadRoot: FileSystemDirectoryHandle | null = null

const formatDuration = (ms?: number | null) => {
  if (!ms) return '--:--'
  const seconds = Math.round(ms / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
const formatDateTime = (value: string) => new Date(value).toLocaleString('vi-VN')
const dateKey = (value: string) => new Date(value).toLocaleDateString('en-CA')
function groupBy<T>(items: T[], key: (item: T) => string): Record<string, T[]> {
  return items.reduce<Record<string, T[]>>((groups, item) => {
    const name = key(item); (groups[name] ||= []).push(item); return groups
  }, {})
}

function ErrorBanner({ message, clear }: { message: string; clear: () => void }) {
  return <div className="error-banner"><XCircle size={18} /><span>{message}</span><button onClick={clear}>Đóng</button></div>
}

function Empty({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return <div className="empty"><Sparkles size={34} /><h2>{title}</h2><p>{text}</p>{action}</div>
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState(localStorage.getItem('projectId') || '')
  const [assets, setAssets] = useState<Asset[]>([])
  const [sequences, setSequences] = useState<VideoSequence[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [system, setSystem] = useState<any>(null)
  const [tab, setTab] = useState<Tab>('media')
  const [error, setError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const jobsRef = useRef<Job[]>([])
  const assetsRef = useRef<Asset[]>([])
  const jobsRefreshInFlight = useRef(false)
  const assetsRefreshInFlight = useRef(false)

  const guarded: Guard = useCallback(async action => {
    setError('')
    try { await action() } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
  }, [])
  const refreshProjects = useCallback(() => guarded(async () => {
    const values = await request<Project[]>('/projects')
    setProjects(values)
    if (!projectId && values[0]) setProjectId(values[0].id)
  }), [guarded, projectId])
  const refreshProjectData = useCallback(() => {
    if (!projectId) { setAssets([]); setSequences([]); setJobs([]); return Promise.resolve() }
    return guarded(async () => {
      const [a, s, j] = await Promise.all([
        request<Asset[]>(`/projects/${projectId}/assets`),
        request<VideoSequence[]>(`/projects/${projectId}/sequences`),
        request<Job[]>(`/jobs?project_id=${projectId}`),
      ])
      setAssets(a); setSequences(s); setJobs(j)
    })
  }, [guarded, projectId])

  useEffect(() => { refreshProjects(); request('/system/status').then(setSystem).catch(() => {}) }, [])
  useEffect(() => { localStorage.setItem('projectId', projectId); refreshProjectData() }, [projectId, refreshProjectData])
  useEffect(() => { jobsRef.current = jobs }, [jobs])
  useEffect(() => { assetsRef.current = assets }, [assets])
  useEffect(() => {
    if (!projectId) return
    const source = new EventSource(`/api/events?project_id=${projectId}`)
    source.addEventListener('jobs', event => {
      let summaries: Array<Pick<Job, 'id'|'status'|'progress'|'error_message'|'output_asset_id'>>
      try { summaries = JSON.parse((event as MessageEvent).data) } catch { return }
      const knownIds = new Set(jobsRef.current.map(job => job.id))
      const hasUnknownJob = summaries.some(job => !knownIds.has(job.id))
      const hasNewOutput = summaries.some(job => job.output_asset_id && !assetsRef.current.some(asset => asset.id === job.output_asset_id))
      if (hasUnknownJob && !jobsRefreshInFlight.current) {
        jobsRefreshInFlight.current = true
        request<Job[]>(`/jobs?project_id=${projectId}`).then(setJobs).catch(() => {}).finally(()=>{jobsRefreshInFlight.current=false})
      } else {
        const updates = new Map(summaries.map(job => [job.id, job]))
        setJobs(current => current.map(job => updates.has(job.id) ? { ...job, ...updates.get(job.id)! } : job))
      }
      if (hasNewOutput && !assetsRefreshInFlight.current) {
        assetsRefreshInFlight.current = true
        request<Asset[]>(`/projects/${projectId}/assets`).then(setAssets).catch(() => {}).finally(()=>{assetsRefreshInFlight.current=false})
      }
    })
    return () => source.close()
  }, [projectId])

  const project = projects.find(item => item.id === projectId)
  const videos = useMemo(() => assets.filter(item => item.type === 'video'), [assets])
  const audios = useMemo(() => assets.filter(item => item.type === 'tts_audio' || item.type === 'external_audio'), [assets])
  const outputs = useMemo(() => assets.filter(item => item.type === 'output'), [assets])

  async function createProject() {
    const name = prompt('Tên project mới:')?.trim(); if (!name) return
    await guarded(async () => {
      const created = await request<Project>('/projects', jsonOptions('POST', { name }))
      setProjects(old => [created, ...old]); setProjectId(created.id)
    })
  }
  async function renameProject() {
    if (!project) return
    const name = prompt('Tên project mới:', project.name)?.trim(); if (!name) return
    await guarded(async () => {
      const updated = await request<Project>(`/projects/${project.id}`, jsonOptions('PATCH', { name }))
      setProjects(old => old.map(item => item.id === updated.id ? updated : item))
    })
  }
  async function deleteProject() {
    if (!project || !confirm(`Xóa project “${project.name}” và toàn bộ media?`)) return
    await guarded(async () => {
      await request(`/projects/${project.id}`, { method: 'DELETE' })
      const rest = projects.filter(item => item.id !== project.id)
      setProjects(rest); setProjectId(rest[0]?.id || '')
    })
  }
  const nav: Array<[Tab, string, any]> = [
    ['media', 'Media', FolderOpen], ['scripts', 'AI viết kịch bản', Bot], ['voice', 'Tạo giọng', AudioLines],
    ['sequence', 'Batch video', Layers3], ['render', 'Gán audio & xuất', Clapperboard],
    ['jobs', 'Công việc', Activity],
  ]

  return <div className={`app-shell${sidebarOpen ? '' : ' sidebar-collapsed'}`}>
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Play size={20} fill="currentColor" /></div><div><strong>Video TTS</strong><span>Studio</span></div></div>
      <label className="mini-label">PROJECT HIỆN TẠI</label>
      <select value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">Chọn project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <button className="secondary full" onClick={createProject}><Plus size={16} /> Project mới</button>
      <nav>{nav.map(([id, label, Icon]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}><Icon size={18} />{label}</button>)}</nav>
      <div className="system-mini">
        <span><i className={system?.database?.ok ? 'ok' : 'bad'} /> PostgreSQL</span>
        <span><i className={system?.media?.ffmpeg ? 'ok' : 'bad'} /> FFmpeg</span>
        <span><i className={system?.cuda?.available ? 'ok' : 'bad'} /> {system?.cuda?.device || 'CUDA'}</span>
      </div>
    </aside>
    <main>
      <div className="topbar">
        <button className="topbar-toggle" onClick={() => setSidebarOpen(v => !v)} title={sidebarOpen ? 'Ẩn sidebar' : 'Hiện sidebar'}>
          {sidebarOpen ? <X size={18} /> : <Layers3 size={18} />}
        </button>
        <span className="topbar-title">{project?.name || 'Video TTS Studio'}</span>
        <div className="topbar-actions">
          {project && <>
            <button className="secondary" onClick={renameProject}>Đổi tên</button>
            <button className="danger-button" onClick={deleteProject}><Trash2 size={16} /> Xóa</button>
          </>}
          <button className="icon-button" onClick={refreshProjectData}><RefreshCw size={18} /></button>
        </div>
      </div>
      {error && <ErrorBanner message={error} clear={() => setError('')} />}
      {!projectId ? <Empty title="Bắt đầu bằng một project" text="Tạo project để quản lý từng chiến dịch video." action={<button onClick={createProject}><Plus size={16} /> Tạo project</button>} /> : <>
        {tab === 'media' && <MediaPanel projectId={projectId} assets={assets} refresh={refreshProjectData} guarded={guarded} />}
        {tab === 'scripts' && <AIScriptPanel key={projectId} projectId={projectId} guarded={guarded} refresh={refreshProjectData} />}
        {tab === 'voice' && <VoicePanel projectId={projectId} audios={audios} jobs={jobs} guarded={guarded} />}
        {tab === 'sequence' && <SequencePanel projectId={projectId} videos={videos} sequences={sequences} refresh={refreshProjectData} guarded={guarded} />}
        {tab === 'render' && <RenderPanel key={projectId} projectId={projectId} audios={audios} sequences={sequences} outputs={outputs} system={system} guarded={guarded} setTab={setTab} refresh={refreshProjectData} />}
        {tab === 'jobs' && <JobsPanel jobs={jobs} outputs={outputs} refresh={refreshProjectData} guarded={guarded} />}
      </>}
    </main>
  </div>
}

function AIScriptPanel({ projectId, guarded, refresh }: { projectId: string; guarded: Guard; refresh: () => Promise<void> }) {
  const [skills, setSkills] = useState<AISkill[]>([])
  const [providers, setProviders] = useState<AIProvider[]>([])
  const [productInfo, setProductInfo] = useState('')
  const [skillId, setSkillId] = useState('')
  const [provider, setProvider] = useState('auto')
  const [count, setCount] = useState(5)
  const [durationMin, setDurationMin] = useState(18)
  const [durationMax, setDurationMax] = useState(20)
  const draftKey = `ai-script-drafts:${projectId}`
  const [scripts, setScripts] = useState<GeneratedScript[]>(() => {
    try { return JSON.parse(localStorage.getItem(draftKey) || '[]') } catch { return [] }
  })
  const [selected, setSelected] = useState<number[]>([])
  const [providerUsed, setProviderUsed] = useState('')
  const [modelUsed, setModelUsed] = useState('')
  const [generating, setGenerating] = useState(false)
  const [creatingVoice, setCreatingVoice] = useState(false)
  const [voices, setVoices] = useState<Array<{label:string;id:string}>>([])
  const [voice, setVoice] = useState('')
  const [device, setDevice] = useState('cuda')
  const [audioName, setAudioName] = useState('kich-ban-ai')
  const [groupName, setGroupName] = useState('AI kịch bản')
  const [speed, setSpeed] = useState(1)
  const [queueProgress, setQueueProgress] = useState('')

  useEffect(() => { localStorage.setItem(draftKey, JSON.stringify(scripts)) }, [draftKey, scripts])

  useEffect(() => {
    Promise.all([
      request<AISkill[]>('/ai/skills'),
      request<{providers: AIProvider[]}>('/ai/providers'),
      request<Array<{label:string;id:string}>>('/system/tts/voices'),
    ]).then(([skillRows, providerRows, voiceRows]) => {
      setSkills(skillRows); setProviders(providerRows.providers); setVoices(voiceRows)
      if (skillRows[0]) setSkillId(current => current || skillRows[0].id)
      if (voiceRows[0]) setVoice(current => current || voiceRows[0].id)
    }).catch(() => {})
  }, [])

  async function generate() {
    if (scripts.length && !confirm(`Tạo mới sẽ thay thế ${scripts.length} bản nháp hiện tại. Tiếp tục?`)) return
    await guarded(async () => {
      setGenerating(true)
      try {
        const result = await request<ScriptGenerateResult>(`/projects/${projectId}/scripts/generate`, jsonOptions('POST', {
          product_info: productInfo, skill_id: skillId, provider, count,
          duration_min: durationMin, duration_max: durationMax,
        }))
        setScripts(result.scripts); setSelected(result.scripts.map(item => item.index))
        setProviderUsed(result.provider_used); setModelUsed(result.model_used)
      } finally { setGenerating(false) }
    })
  }

  function patchText(index: number, text: string, el?: HTMLTextAreaElement) {
    if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' }
    setScripts(old => old.map(item => item.index === index ? { ...item, text, estimated_duration_seconds: Math.round(text.trim().split(/\s+/).filter(Boolean).length / 4 * 10) / 10 } : item))
  }

  function addScript() {
    const index = Math.max(0, ...scripts.map(item => item.index)) + 1
    setScripts(old => [...old, { index, text: '', estimated_duration_seconds: 0, warnings: [] }])
    setSelected(old => [...old, index])
  }

  function removeScript(index: number) {
    if (!confirm(`Xóa kịch bản ${index}?`)) return
    setScripts(old => old.filter(item => item.index !== index))
    setSelected(old => old.filter(value => value !== index))
  }

  function clearScripts() {
    if (!scripts.length || !confirm(`Xóa toàn bộ ${scripts.length} bản nháp?`)) return
    setScripts([]); setSelected([]); setProviderUsed(''); setModelUsed('')
  }

  async function createVoices(indexes = selected) {
    const chosen = scripts.filter(item => indexes.includes(item.index) && item.text.trim())
    if (!chosen.length) return
    const cleanGroup = groupName.trim()
    if (!cleanGroup) { alert('Hãy nhập tên nhóm audio trước khi tạo giọng.'); return }
    if (!confirm(`Tạo nhóm “${cleanGroup}” gồm ${chosen.length} audio, tốc độ ${speed.toFixed(1)}×?`)) return
    await guarded(async () => {
      setCreatingVoice(true)
      try {
        for (let position = 0; position < chosen.length; position++) {
          const item = chosen[position]
          setQueueProgress(`${position + 1}/${chosen.length}`)
          await request(`/projects/${projectId}/tts/jobs`, jsonOptions('POST', {
            text: item.text.trim(), voice, device, name: `${audioName}-${item.index}`,
            group_name: cleanGroup, output_format: 'mp3', use_batch: true,
            batch_size: 16, temperature: .8, max_chars: 256, top_k: 25,
            top_p: .95, repetition_penalty: 1.2, silence_p: .15, speed,
          }))
        }
        await refresh()
      } finally { setCreatingVoice(false); setQueueProgress('') }
    })
  }

  const configured = providers.filter(item => item.configured)
  const allSelected = scripts.length > 0 && selected.length === scripts.length
  return <section className="ai-section-full">
    <div className="ai-studio-grid">
      <aside className="panel ai-setup-sidebar">
        <div className="ai-sidebar-title"><Wand2 size={17}/><strong>Tạo kịch bản</strong><i className={configured.length?'ready':''}/></div>
        <label>Mô tả sản phẩm</label><textarea rows={6} value={productInfo} onChange={e=>setProductInfo(e.target.value)} placeholder="Tên sản phẩm, đặc điểm, công dụng, giá hoặc ưu đãi nếu có..."/>
        <label>Skill</label><select value={skillId} onChange={e=>setSkillId(e.target.value)}>{skills.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <label>Nhà cung cấp</label><select value={provider} onChange={e=>setProvider(e.target.value)}><option value="auto">Auto</option>{providers.map(item=><option key={item.id} value={item.id} disabled={!item.configured}>{item.name}{item.configured?` · ${item.model}`:' · chưa cấu hình'}</option>)}</select>
        <div className="ai-sidebar-numbers"><div><label>Số lượng</label><input type="number" min="1" max="100" value={count} onChange={e=>setCount(Math.max(1,Math.min(100,Math.trunc(+e.target.value||1))))}/></div><div><label>Thời lượng</label><div className="duration-pair"><input aria-label="Từ giây" type="number" min="5" max="120" value={durationMin} onChange={e=>setDurationMin(+e.target.value)}/><span>–</span><input aria-label="Đến giây" type="number" min="5" max="120" value={durationMax} onChange={e=>setDurationMax(+e.target.value)}/></div></div></div>
        <button className="primary wide" disabled={generating||!productInfo.trim()||!skillId||!configured.length} onClick={generate}><Wand2 size={16}/>{generating?'Đang tạo...':`Tạo ${count} kịch bản`}</button>
        {!configured.length&&<small className="ai-provider-note">Chưa cấu hình API AI trong .env</small>}
        <div className="ai-voice-section">
          <div className="ai-voice-section-title"><AudioLines size={14}/><span>Tạo giọng</span></div>
          <label>Giọng đọc</label>
          <select aria-label="Giọng đọc" value={voice} onChange={e=>setVoice(e.target.value)}>{voices.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select>
          <div className="ai-voice-row">
            <div>
              <label>Thiết bị</label>
              <select aria-label="Thiết bị" value={device} onChange={e=>setDevice(e.target.value)}><option value="cuda">CUDA</option><option value="auto">Auto</option><option value="cpu">CPU</option></select>
            </div>
            <div>
              <label>Tốc độ: <b style={{color:'#45d8b7'}}>{speed.toFixed(1)}×</b></label>
              <input type="range" min=".5" max="2" step=".1" value={speed} onChange={e=>setSpeed(+e.target.value)} style={{padding:0,border:0,boxShadow:'none'}}/>
            </div>
          </div>
          <label>Tên file</label>
          <input aria-label="Tên file" value={audioName} onChange={e=>setAudioName(e.target.value)} placeholder="kich-ban-ai"/>
          <label>Tên nhóm audio</label>
          <input aria-label="Tên nhóm" value={groupName} onChange={e=>setGroupName(e.target.value)} placeholder="Tên nhóm audio"/>
          <button className="primary wide" style={{marginTop:10}} disabled={creatingVoice||!selected.length||!voice||!groupName.trim()} onClick={()=>createVoices()}><AudioLines size={15}/>{creatingVoice?queueProgress:`Tạo nhóm (${selected.length})`}</button>
        </div>
      </aside>

      <div className="ai-script-workspace">
        <div className="script-table-toolbar">
          <div className="toolbar-left">
            <strong className="toolbar-title">{scripts.length} kịch bản</strong>
            <span className="toolbar-badge selected">{selected.length} đã chọn</span>
            {providerUsed && <span className="toolbar-badge provider">{providerUsed} · {modelUsed}</span>}
          </div>
          <div className="toolbar-right">
            <button
              type="button"
              className={`sel-all-btn${allSelected ? ' sel-all-active' : ''}`}
              title={allSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả'}
              onClick={() => setSelected(allSelected ? [] : scripts.map(s => s.index))}
            >
              <CheckCircle2 size={15} />
              <span>{allSelected ? 'Bỏ chọn' : 'Chọn tất cả'}</span>
            </button>
            <button type="button" className="icon-button" title="Thêm kịch bản" onClick={addScript}>
              <Plus size={16} />
            </button>
            <button type="button" className="icon-button danger-quiet" title="Xóa toàn bộ" disabled={!scripts.length} onClick={clearScripts}>
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        {!scripts.length ? (
          <Empty title="Chưa có kịch bản" text="Tạo bằng AI hoặc thêm một dòng để nhập thủ công." />
        ) : (
          <div className="script-table-container">
            <table className="script-table">
              <thead>
                <tr>
                  <th className="th-index">#</th>
                  <th className="th-content">Nội dung kịch bản ({scripts.length})</th>
                  <th className="th-actions">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {scripts.map(item => {
                  const words = item.text.trim() ? item.text.trim().split(/\s+/).filter(Boolean).length : 0
                  const isSel = selected.includes(item.index)
                  return (
                    <tr key={item.index} className={`script-row${isSel ? ' script-row-selected' : ''}`}>
                      <td className="script-col-index">
                        <span className="script-index-badge">{item.index}</span>
                      </td>
                      <td className="script-col-content">
                        <textarea
                          rows={3}
                          value={item.text}
                          onChange={e => patchText(item.index, e.target.value)}
                          placeholder="Nhập nội dung kịch bản..."
                          className="script-table-textarea"
                        />
                        <div className="script-meta-bar">
                          <span className="script-word-count">{words} từ</span>
                          <span className="script-duration">≈ {item.estimated_duration_seconds || Math.round(words / 4)}s</span>
                          {item.warnings && item.warnings.length > 0 && (
                            <span className="script-warning-badge" title={item.warnings.join('\n')}>
                              ⚠️ {item.warnings[0]}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="script-col-actions">
                        <div className="script-action-group">
                          <button
                            type="button"
                            className="row-icon voice"
                            title="Tạo giọng cho dòng này"
                            disabled={creatingVoice || !voice || !item.text.trim()}
                            onClick={() => createVoices([item.index])}
                          >
                            <AudioLines size={15} />
                          </button>
                          <button
                            type="button"
                            className="row-icon delete"
                            title="Xóa dòng"
                            onClick={() => removeScript(item.index)}
                          >
                            <Trash2 size={15} />
                          </button>
                          <button
                            type="button"
                            className={`sel-row-btn${isSel ? ' sel-row-active' : ''}`}
                            title={isSel ? 'Bỏ chọn' : 'Chọn dòng này'}
                            onClick={() => setSelected(old => isSel ? old.filter(v => v !== item.index) : Array.from(new Set([...old, item.index])))}
                          >
                            <MousePointer2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  </section>
}

async function uploadAssets(projectId: string, files: FileList | File[] | null, batchName?: string): Promise<Asset[]> {
  if (!files?.length) return []
  const form = new FormData(); Array.from(files).forEach(file => form.append('files', file))
  if (batchName) form.append('batch_name', batchName)
  const response = await fetch(`/api/projects/${projectId}/assets/import`, { method: 'POST', body: form })
  if (!response.ok) { const body = await response.json(); throw new Error(body.detail || 'Nhập file thất bại') }
  return response.json() as Promise<Asset[]>
}

function MediaPanel({ projectId, assets, refresh, guarded }: { projectId: string; assets: Asset[]; refresh: () => Promise<void>; guarded: Guard }) {
  const [filter, setFilter] = useState('all'); const [busy, setBusy] = useState(false)
  const shown = filter === 'all' ? assets : assets.filter(item => item.type === filter)
  async function upload(files: FileList | null) { await guarded(async () => { setBusy(true); await uploadAssets(projectId, files); await refresh(); setBusy(false) }); setBusy(false) }
  async function remove(id: string) { if (!confirm('Xóa asset và file này?')) return; await guarded(async () => { await request(`/assets/${id}`, { method: 'DELETE' }); await refresh() }) }
  return <section>
    <div className="section-title compact-section-title"><div className="header-actions"><button className="secondary" onClick={() => guarded(async () => { await request(`/projects/${projectId}/open-folder`, { method:'POST' }) })}><FolderOpen size={16} /> Mở thư mục</button><label className="button"><Upload size={16} />{busy ? 'Đang nhập...' : 'Nhập file'}<input hidden multiple type="file" accept="video/*,audio/*" disabled={busy} onChange={e => upload(e.target.files)} /></label></div></div>
    <div className="segmented">{[['all','Tất cả'],['video','Video'],['tts_audio','TTS'],['external_audio','Audio'],['output','Output']].map(([id,label]) => <button key={id} className={filter === id ? 'active':''} onClick={() => setFilter(id)}>{label}</button>)}</div>
    {!shown.length ? <Empty title="Chưa có media" text="Nhập video hoặc tạo giọng đọc để bắt đầu." /> : <div className="asset-grid">{shown.map(asset => <article className="asset-card" key={asset.id}>
      <div className="asset-preview">{asset.type === 'video' || asset.type === 'output' ? <video src={streamUrl(asset.id)} controls preload="metadata" poster={asset.thumbnail_path ? thumbnailUrl(asset.id) : undefined} /> : <AudioLines size={34} />}</div>
      <div className="asset-info"><strong>{asset.display_name}</strong><span>{asset.type} · {formatDuration(asset.duration_ms)} · {formatDateTime(asset.created_at)}</span></div>
      {asset.type.includes('audio') && <audio controls preload="none" src={streamUrl(asset.id)} />}
      <button className="danger-icon" onClick={() => remove(asset.id)}><Trash2 size={15} /></button>
    </article>)}</div>}
  </section>
}

function VoicePanel({ projectId, audios, jobs, guarded }: { projectId: string; audios: Asset[]; jobs: Job[]; guarded: Guard }) {
  const [text, setText] = useState(''); const [device, setDevice] = useState('cuda'); const [name, setName] = useState('giong-doc')
  const [voices, setVoices] = useState<Array<{label:string;id:string}>>([]); const [voice, setVoice] = useState(''); const [loadingVoices, setLoadingVoices] = useState(true)
  const [advanced, setAdvanced] = useState(false); const [useBatch, setUseBatch] = useState(true); const [batchSize, setBatchSize] = useState(16)
  const [temperature, setTemperature] = useState(.8); const [maxChars, setMaxChars] = useState(256); const [topK, setTopK] = useState(25); const [topP, setTopP] = useState(.95); const [repetition, setRepetition] = useState(1.2); const [silence, setSilence] = useState(.15)
  const [format, setFormat] = useState('mp3'); const [day, setDay] = useState('all'); const [editing, setEditing] = useState<Asset | null>(null)
  const [submitting, setSubmitting] = useState(false); const [speed, setSpeed] = useState(1); const [importingExcel, setImportingExcel] = useState(false)
  const [groupName, setGroupName] = useState(''); const [audioGroup, setAudioGroup] = useState('all')
  const [excelFile, setExcelFile] = useState<File|null>(null)
  const [selectedAudioIds, setSelectedAudioIds] = useState<string[]>([]); const [bulkSpeed, setBulkSpeed] = useState(1)
  const ttsQueue = jobs
    .filter(job => job.kind === 'tts' && ['queued','running'].includes(job.status))
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  const activeJob = ttsQueue.find(job => job.status === 'running')
  const days = Array.from(new Set(audios.map(a => dateKey(a.created_at)))).sort().reverse()
  const audioGroups = Array.from(new Set(audios.map(a => String(a.metadata_json.group_name || '')).filter(Boolean)))
  const filtered = audios.filter(a => (day === 'all' || dateKey(a.created_at) === day) && (audioGroup === 'all' || String(a.metadata_json.group_name || '') === audioGroup))

  useEffect(() => {
    let alive = true; setLoadingVoices(true)
    request<Array<{label:string;id:string}>>(`/system/tts/voices?device=${device}`).then(values => {
      if (!alive) return; setVoices(values); setVoice(old => old || values[0]?.id || ''); setLoadingVoices(false)
    }).catch(() => { if (alive) setLoadingVoices(false) })
    return () => { alive = false }
  }, [device])

  function ttsPayload(nextText: string) {
    return {
      text: nextText, voice, device, name: name.trim(), group_name: null as string|null,
      output_format: format, speed, use_batch: useBatch, batch_size: batchSize,
      temperature, max_chars: maxChars, top_k: topK, top_p: topP,
      repetition_penalty: repetition, silence_p: silence,
    }
  }

  async function generate() {
    if (!text.trim() || !voice) throw new Error('Cần nhập văn bản và chọn giọng')
    if (!name.trim()) return
    setSubmitting(true)
    await guarded(async () => { await request(`/projects/${projectId}/tts/jobs`, jsonOptions('POST', ttsPayload(text))); setText('') })
    setSubmitting(false)
  }
  async function importExcel(file: File | undefined) {
    if (!file) return
    const now = new Date()
    const prefix = `${now.getMonth()+1}-${now.getDate()}`
    const used = new Set([...audioGroups, ...jobs.map(job => String(job.input_json.group_name || ''))])
    let index = 1
    while (used.has(`${prefix}-${index}`)) index++
    setGroupName(`${prefix}-${index}`)
    setExcelFile(file)
  }
  async function confirmExcel() {
    const file = excelFile
    if (!file || !groupName.trim()) return
    if (!voice || !name.trim()) throw new Error('Cần nhập tên file và chọn giọng trước khi nhập Excel')
    setImportingExcel(true)
    await guarded(async () => {
      const form = new FormData()
      form.append('upload', file)
      form.append('settings', JSON.stringify({...ttsPayload('Nội dung lấy từ Excel'), group_name:groupName.trim()}))
      await request(`/projects/${projectId}/tts/excel-jobs`, { method: 'POST', body: form })
      setExcelFile(null)
    })
    setImportingExcel(false)
  }
  async function cancelTts(jobId: string) {
    await guarded(async () => { await request(`/jobs/${jobId}/cancel`, { method: 'POST' }) })
  }
  async function processAudioBatch() {
    if (!selectedAudioIds.length) return
    await guarded(async () => {
      await request(`/projects/${projectId}/audio/batch-jobs`, jsonOptions('POST', {asset_ids:selectedAudioIds, speed:bulkSpeed, output_format:'mp3'}))
      setSelectedAudioIds([])
    })
  }
  return <section>
    {activeJob && <div className="tts-progress"><div><span>Đang tạo: {String(activeJob.input_json.name || 'voice')} · tiến độ ước tính</span><b>{Math.round(activeJob.progress)}%</b></div><div className="progress"><i style={{width:`${activeJob.progress}%`}} /></div></div>}
    <div className="two-columns"><div className="panel"><label>Văn bản</label><textarea rows={10} value={text} onChange={e => setText(e.target.value)} placeholder="Nhập nội dung cần đọc..." /><div className="counter">{text.length.toLocaleString()} ký tự</div>
      <div className="form-row"><div><label>Tên file gốc</label><input value={name} onChange={e => setName(e.target.value)} /><small className="field-hint">Tự động thêm _1, _2, _3...</small></div><div><label>Thiết bị</label><select value={device} onChange={e => setDevice(e.target.value)}><option value="cuda">CUDA</option><option value="auto">Auto</option><option value="cpu">CPU</option></select></div><div><label>Định dạng</label><select value={format} onChange={e => setFormat(e.target.value)}><option value="mp3">MP3</option><option value="wav">WAV</option></select></div></div>
      <label>Giọng đọc</label><select value={voice} disabled={loadingVoices} onChange={e => setVoice(e.target.value)}><option value="">{loadingVoices ? 'Đang tải giọng...' : 'Chọn giọng'}</option>{voices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}</select>
      <label>Tốc độ đọc: <b>{speed.toFixed(1)}×</b></label><input className="tts-speed" type="range" min=".5" max="2" step=".1" value={speed} onChange={e => setSpeed(+e.target.value)} />
      <p className="muted">Dán text: audio riêng. Nhập Excel: tạo một nhóm audio mới.</p>
      <button className="advanced-toggle" onClick={() => setAdvanced(v => !v)}>⚙ Tham số VieNeu {advanced ? '▲' : '▼'}</button>
      {advanced && <div className="advanced-grid"><label><span>Batch processing</span><input type="checkbox" checked={useBatch} onChange={e => setUseBatch(e.target.checked)} /></label><label><span>Batch size: {batchSize}</span><input type="range" min="1" max="64" step="1" value={batchSize} disabled={!useBatch} onChange={e => setBatchSize(+e.target.value)} /></label><label><span>Temperature: {temperature}</span><input type="range" min=".1" max="1.5" step=".1" value={temperature} onChange={e => setTemperature(+e.target.value)} /></label><label><span>Max chars: {maxChars}</span><input type="range" min="128" max="512" step="32" value={maxChars} onChange={e => setMaxChars(+e.target.value)} /></label><label><span>Top K: {topK}</span><input type="range" min="0" max="100" step="1" value={topK} onChange={e => setTopK(+e.target.value)} /></label><label><span>Top P: {topP}</span><input type="range" min=".1" max="1" step=".05" value={topP} onChange={e => setTopP(+e.target.value)} /></label><label><span>Repetition: {repetition}</span><input type="range" min="1" max="2" step=".1" value={repetition} onChange={e => setRepetition(+e.target.value)} /></label><label><span>Khoảng lặng: {silence}s</span><input type="range" min="0" max="3" step=".1" value={silence} onChange={e => setSilence(+e.target.value)} /></label></div>}
      <button className="primary wide" disabled={submitting || !text.trim() || !voice || !name.trim()} onClick={generate}><Plus size={17} /> {submitting ? 'Đang thêm...' : 'Thêm vào hàng chờ'}</button>
      <div className="excel-import"><div><strong>Nhập kịch bản từ Excel</strong><span>File .xlsx gồm 2 cột: STT (1 đến n) và text.</span></div><label className="button secondary"><Upload size={15}/>{importingExcel ? 'Đang đọc...' : 'Chọn file Excel'}<input hidden type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={importingExcel || !voice || !name.trim()} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; void importExcel(file) }}/></label></div>
      <div className="tts-queue">
        <div className="panel-heading"><h3>Hàng chờ tạo giọng</h3><span className="count">{ttsQueue.length} tác vụ</span></div>
        {ttsQueue.length === 0 ? <p className="muted">Chưa có tác vụ. Bạn có thể thêm nhiều nội dung liên tiếp.</p> : ttsQueue.map((job, index) => <div className={`tts-queue-item ${job.status}`} key={job.id}>
          <div className="tts-queue-order">{job.status === 'running' ? <LoaderCircle className="spin" size={16} /> : index + (activeJob ? 0 : 1)}</div>
          <div className="tts-queue-info"><strong>{String(job.input_json.name || 'voice')}.{String(job.input_json.output_format || 'mp3')}</strong><span>{job.status === 'running' ? `Đang tạo · ${Math.round(job.progress)}%` : `Đang chờ · vị trí ${index + (activeJob ? 0 : 1)}`}</span></div>
          <button className="tts-queue-cancel" onClick={() => cancelTts(job.id)} title="Hủy tác vụ"><X size={14} /></button>
        </div>)}
      </div>
    </div><div className="panel"><div className="panel-heading"><h3>Thư viện audio</h3><div className="audio-filters"><select value={audioGroup} onChange={e => setAudioGroup(e.target.value)}><option value="all">Tất cả nhóm</option>{audioGroups.map(group => <option value={group} key={group}>{group}</option>)}</select><select value={day} onChange={e => setDay(e.target.value)}><option value="all">Tất cả ngày</option>{days.map(d => <option value={d} key={d}>{new Date(`${d}T00:00:00`).toLocaleDateString('vi-VN')}</option>)}</select></div></div><div className="audio-bulk"><span>{selectedAudioIds.length} audio đã chọn</span><label>Tốc độ <b>{bulkSpeed.toFixed(1)}×</b><input type="range" min=".5" max="2" step=".1" value={bulkSpeed} onChange={e=>setBulkSpeed(+e.target.value)}/></label><button className="secondary" disabled={!selectedAudioIds.length || bulkSpeed === 1} onClick={processAudioBatch}><Scissors size={14}/> Tạo bản hàng loạt</button></div>{filtered.length ? filtered.map(asset => <div className="audio-row" key={asset.id}><div><label className="audio-select"><input type="checkbox" checked={selectedAudioIds.includes(asset.id)} onChange={e=>setSelectedAudioIds(old=>e.target.checked?[...old,asset.id]:old.filter(id=>id!==asset.id))}/><strong>{asset.display_name}</strong></label><span>{String(asset.metadata_json.group_name || 'Riêng')} · {formatDateTime(asset.created_at)} · {formatDuration(asset.duration_ms)}</span></div><audio controls src={streamUrl(asset.id)} preload="metadata" /><button className="secondary edit-audio" onClick={() => setEditing(asset)}><Scissors size={14} /> Tốc độ / cắt</button></div>) : <p className="muted">Không có audio phù hợp bộ lọc.</p>}</div></div>
    {editing && <AudioEditor asset={editing} close={() => setEditing(null)} guarded={guarded} />}
    {excelFile && <div className="modal-backdrop"><div className="modal"><h2>Tạo nhóm từ Excel</h2><p>{excelFile.name} · Toàn bộ kịch bản dùng giọng và tham số đang chọn.</p><label>Tên nhóm mới</label><input maxLength={100} value={groupName} onChange={e=>setGroupName(e.target.value)}/><p>Gợi ý tháng-ngày-index; bạn có thể sửa tên.</p><div className="header-actions"><button disabled={importingExcel} className="secondary" onClick={()=>setExcelFile(null)}>Hủy</button><button disabled={importingExcel || !groupName.trim()} onClick={confirmExcel}>{importingExcel?'Đang nhập…':'Xác nhận chạy'}</button></div></div></div>}
  </section>
}

function AudioEditor({ asset, close, guarded }: { asset: Asset; close: () => void; guarded: Guard }) {
  const duration = (asset.duration_ms || 0) / 1000
  const [speed, setSpeed] = useState(1); const [start, setStart] = useState(0); const [end, setEnd] = useState(duration); const [name, setName] = useState(`${asset.display_name}-edited`)
  async function save() { await guarded(async () => { await request(`/assets/${asset.id}/audio/jobs`, jsonOptions('POST', { name, speed, trim_start:start, trim_end:end, output_format:'mp3' })); close() }) }
  return <div className="modal-backdrop"><div className="modal"><div className="panel-heading"><h2>Chỉnh audio</h2><button className="icon-button" onClick={close}>×</button></div><audio controls src={streamUrl(asset.id)} /><label>Tên file mới</label><input value={name} onChange={e => setName(e.target.value)} /><label>Tốc độ: <b>{speed.toFixed(1)}×</b></label><input type="range" min=".5" max="2" step=".1" value={speed} onChange={e => setSpeed(+e.target.value)} /><div className="form-row"><div><label>Bắt đầu (giây)</label><input type="number" min="0" max={end} step=".1" value={start} onChange={e => setStart(+e.target.value)} /></div><div><label>Kết thúc (giây)</label><input type="number" min={start} max={duration} step=".1" value={end} onChange={e => setEnd(+e.target.value)} /></div></div><p className="muted">Kết quả dự kiến: {((end-start)/speed).toFixed(1)} giây</p><button className="primary wide" onClick={save}><Scissors size={16} /> Tạo bản MP3 mới</button></div></div>
}

function estimateOutputs(count: number, mode: string, k: number) {
  if (!count || k < 1) return 0
  if (mode === 'product_with_repetition') return count ** k
  if (k > count) return 0
  let value = 1; for (let i=0;i<k;i++) value *= count-i; return value
}

function SequencePanel({ projectId, videos, sequences, refresh, guarded }: { projectId:string; videos:Asset[]; sequences:VideoSequence[]; refresh:()=>Promise<void>; guarded:Guard }) {
  const newBatch = (index:number):BatchDraft => {
    const now = new Date()
    const time = `${String(now.getHours()).padStart(2,'0')}-${String(now.getMinutes()).padStart(2,'0')}`
    return { id:crypto.randomUUID(), name:`Batch ${index} - ${time}`, selected:[], mode:'product_with_repetition', k:2, manual:[] }
  }
  const nextBatchIndex = (names:string[]) => names.reduce((highest, name) => {
    const match = /^Batch\s+(\d+)/i.exec(name)
    return match ? Math.max(highest, Number(match[1])) : highest
  }, 0) + 1
  const [batches, setBatches] = useState<BatchDraft[]>(() => [newBatch(nextBatchIndex(sequences.map(sequence => sequence.batch_name)))])
  const [uploading, setUploading] = useState(false)
  const [generatingAll, setGeneratingAll] = useState(false)
  const [dragOverBatch, setDragOverBatch] = useState<string|null>(null)
  const [selectedSourceIds, setSelectedSourceIds] = useState<Set<string>>(new Set())
  const labels = useMemo(() => Object.fromEntries(videos.map((v,i) => [v.id,String.fromCharCode(65+i)])), [videos])
  const update = (id:string, values:Partial<BatchDraft>) => setBatches(old => old.map(b => b.id === id ? {...b,...values}:b))

  function addBatch() {
    setBatches(old => {
      const usedNames = [...old.map(batch => batch.name), ...sequences.map(sequence => sequence.batch_name)]
      return [...old, newBatch(nextBatchIndex(usedNames))]
    })
  }

  async function upload(files:FileList|File[]|null, batchId?:string) {
    await guarded(async()=>{
      setUploading(true)
      const batch = batchId ? batches.find(item => item.id === batchId) : undefined
      const created = await uploadAssets(projectId, files, batch?.name)
      if (batch && created.length) {
        update(batch.id, {selected:[...batch.selected, ...created.filter(asset => asset.type === 'video').map(asset => asset.id)]})
      }
      await refresh()
      setUploading(false)
    })
    setUploading(false)
  }

  function addVideoToBatch(batchId:string, videoId:string) {
    setBatches(old => old.map(b => {
      if (b.id !== batchId) return b
      if (old.some(other => other.id !== batchId && other.selected.includes(videoId))) return b
      if (b.selected.includes(videoId)) return b // already in batch
      return { ...b, selected: [...b.selected, videoId] }
    }))
    setSelectedSourceIds(prev => { const next = new Set(prev); next.delete(videoId); return next })
  }

  function toggleSourceSelect(videoId: string) {
    setSelectedSourceIds(prev => {
      const next = new Set(prev)
      next.has(videoId) ? next.delete(videoId) : next.add(videoId)
      return next
    })
  }

  function addSelectedToBatch(batchId: string) {
    if (!selectedSourceIds.size) return
    setBatches(old => old.map(b => {
      if (b.id !== batchId) return b
      const usedElsewhere = new Set(old.filter(other => other.id !== batchId).flatMap(other => other.selected))
      const toAdd = [...selectedSourceIds].filter(id => !b.selected.includes(id) && !usedElsewhere.has(id))
      return { ...b, selected: [...b.selected, ...toAdd] }
    }))
    setSelectedSourceIds(new Set())
  }

  function removeVideoFromBatch(batchId:string, videoId:string) {
    setBatches(old => old.map(b => b.id !== batchId ? b : { ...b, selected: b.selected.filter(id => id !== videoId) }))
  }

  async function generate(batch:BatchDraft) {
    await guarded(async()=>{
      await request(`/projects/${projectId}/sequences/generate`, jsonOptions('POST', {
        video_asset_ids:batch.selected, mode:batch.mode, length:batch.k, limit:100, replace_existing:false, batch_name:batch.name
      }))
      await refresh()
    })
  }

  async function generateAll() {
    const valid = batches.filter(batch => {
      const count = estimateOutputs(batch.selected.length, batch.mode, batch.k)
      return batch.name.trim() && batch.selected.length > 0 && count > 0 && count <= 100
    })
    if (!valid.length) return
    setGeneratingAll(true)
    await guarded(async()=>{
      for (const batch of valid) {
        await request(`/projects/${projectId}/sequences/generate`, jsonOptions('POST', {
          video_asset_ids:batch.selected, mode:batch.mode, length:batch.k, limit:100,
          replace_existing:false, batch_name:batch.name
        }))
      }
      await refresh()
    })
    setGeneratingAll(false)
  }

  async function manual(batch:BatchDraft) {
    await guarded(async()=>{
      await request(`/projects/${projectId}/sequences/manual`, jsonOptions('POST', {
        name:batch.manual.map(id=>labels[id]).join('-'), video_asset_ids:batch.manual, batch_name:batch.name
      }))
      update(batch.id,{manual:[]})
      await refresh()
    })
  }

  async function toggleSequence(seq:VideoSequence){
    await guarded(async()=>{ await request(`/sequences/${seq.id}`,jsonOptions('PATCH',{enabled:!seq.enabled})); await refresh() })
  }

  async function deleteSavedBatch(batchName:string) {
    if (!confirm(`Xóa toàn bộ ${batchName} và tất cả sequence bên trong? Video nguồn sẽ được trả về để dùng lại.`)) return
    await guarded(async()=>{
      await request(`/projects/${projectId}/sequence-batches/${encodeURIComponent(batchName)}`, {method:'DELETE'})
      setBatches(old => old.filter(batch => batch.name !== batchName))
      await refresh()
    })
  }

  const groups = Object.entries(groupBy(sequences, sequence => sequence.batch_name || 'Batch 1'))
  const usedVideoIds = new Set(batches.flatMap(batch => batch.selected))
  const sourceVideos = videos.filter(video => !video.video_batch_name)

  return (
    <section>
      {/* ── Nguồn video: strip ngang trên đầu ── */}
      <div className="video-source-strip">
        <div className="video-source-strip-header">
          <div>
            <h3>Nguồn video</h3>
            <p>Click để chọn · kéo vào batch · {sourceVideos.length} clip{selectedSourceIds.size > 0 ? ` · ${selectedSourceIds.size} đã chọn` : ''}</p>
          </div>
          <label className="button small">
            <Upload size={14}/>{uploading ? 'Đang thêm...' : 'Thêm video'}
            <input hidden multiple type="file" accept="video/*" disabled={uploading} onChange={e=>upload(e.target.files)}/>
          </label>
        </div>
        <div className="video-source-cards">
          {sourceVideos.length === 0
            ? <div className="video-source-empty"><Layers3 size={22} opacity={.4}/><span>Chưa có video. Nhập file từ Media hoặc nút Thêm video.</span></div>
            : sourceVideos.map(video => {
              const isSel = selectedSourceIds.has(video.id)
              const isUsed = usedVideoIds.has(video.id)
              return (
                <div
                  key={video.id}
                  className={`video-source-card${isSel ? ' selected' : ''}${isUsed ? ' disabled' : ''}`}
                  draggable={!isUsed}
                  title={isUsed ? 'Video đã thuộc một batch' : isSel ? 'Đã chọn · Kéo hoặc dùng nút Thêm vào batch' : 'Click chọn · hoặc kéo vào batch'}
                  onClick={() => { if (!isUsed) toggleSourceSelect(video.id) }}
                  onDragStart={e => { if (isUsed) { e.preventDefault(); return }; e.dataTransfer.setData('videoId', video.id) }}
                >
                  <div className="video-source-card-thumb">
                    <video src={streamUrl(video.id)} preload="metadata" muted onClick={e => e.stopPropagation()}/>
                    <span className="media-label-badge">{labels[video.id]}</span>
                    {isUsed
                      ? <div className="video-source-used">Đã dùng</div>
                      : isSel
                      ? <div className="video-source-check">✓</div>
                      : <div className="video-source-drag-hint">Kéo / Chọn</div>
                    }
                  </div>
                  <div className="video-source-card-info">
                    <span title={video.display_name}>{video.display_name}</span>
                    <small>{formatDuration(video.duration_ms)}</small>
                  </div>
                </div>
              )
            })
          }
        </div>
      </div>

      {/* ── Batch section ── */}
      <div className="section-title" style={{marginTop:'28px'}}>
        <div><h2>Batch video độc lập</h2><p>Mỗi batch có nguồn, K và thuật toán riêng.</p></div>
        <div className="header-actions">
          <button className="secondary" disabled={generatingAll || !batches.some(batch => batch.selected.length && estimateOutputs(batch.selected.length, batch.mode, batch.k) <= 100)} onClick={generateAll}>
            <Wand2 size={16}/>{generatingAll ? 'Đang sinh tất cả...' : 'Sinh chuỗi hàng loạt'}
          </button>
          <button onClick={addBatch}><Plus size={16}/> Thêm batch</button>
        </div>
      </div>

      <div className="batch-list">
        {batches.map((batch, index) => {
          const selectedVideos = batch.selected.map(id => videos.find(v => v.id === id)).filter(Boolean) as Asset[]
          const outputCount = estimateOutputs(batch.selected.length, batch.mode, batch.k)
          const isDragOver = dragOverBatch === batch.id
          return (
            <div
              className={`panel batch-card${isDragOver ? ' drag-over' : ''}`}
              key={batch.id}
              onDragOver={e=>{ e.preventDefault(); setDragOverBatch(batch.id) }}
              onDragLeave={()=>setDragOverBatch(null)}
              onDrop={e=>{ e.preventDefault(); setDragOverBatch(null); const vid=e.dataTransfer.getData('videoId'); if(vid) addVideoToBatch(batch.id,vid) }}
            >
              {/* Batch header */}
              <div className="panel-heading">
                <div>
                  <span className="batch-number">{index+1}</span>
                  <input className="batch-name" value={batch.name} onChange={e=>update(batch.id,{name:e.target.value})}/>
                </div>
                <div className="header-actions">
                  {selectedSourceIds.size > 0 && (
                    <button className="secondary" style={{color:'#7ddfb8',borderColor:'#2a4a3e'}} onClick={()=>addSelectedToBatch(batch.id)}>
                      <Plus size={14}/> Thêm {selectedSourceIds.size} đã chọn
                    </button>
                  )}
                  <label className="button small">
                    <Upload size={13}/> Thêm file
                    <input hidden multiple type="file" accept="video/*" disabled={uploading} onChange={e=>{ const files=Array.from(e.target.files || []); e.target.value=''; void upload(files,batch.id) }}/>
                  </label>
                  <button className="danger-button" title="Xóa batch nháp" onClick={()=>{
                    if (!batch.selected.length || confirm(`Xóa batch nháp ${batch.name}?`)) setBatches(old=>old.filter(b=>b.id!==batch.id))
                  }}><Trash2 size={14}/></button>
                </div>
              </div>

              {/* Drop zone / selected videos */}
              <div className={`batch-drop-zone${selectedVideos.length === 0 ? ' empty' : ''}`}>
                {selectedVideos.length === 0 ? (
                  <div className="batch-drop-hint">
                    <Layers3 size={28} opacity={.4}/>
                    <span>Kéo video từ nguồn ở trên · hoặc chọn video rồi nhấn "Thêm đã chọn"</span>
                  </div>
                ) : (
                  <div className="batch-selected-videos">
                    {selectedVideos.map(video => (
                      <div className="batch-video-chip" key={video.id}>
                        <div className="batch-chip-thumb">
                          <video src={streamUrl(video.id)} preload="metadata" muted/>
                          <span className="media-label-badge">{labels[video.id]}</span>
                        </div>
                        <span className="batch-chip-name" title={video.display_name}>{video.display_name}</span>
                        <button
                          className="batch-chip-remove"
                          title="Xóa khỏi batch"
                          onClick={()=>removeVideoFromBatch(batch.id, video.id)}
                        >×</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Controls */}
              <div className="batch-controls">
                <div>
                  <label>Thuật toán</label>
                  <select value={batch.mode} onChange={e=>update(batch.id,{mode:e.target.value})}>
                    <option value="product_with_repetition">Có lặp (A-A, A-B...)</option>
                    <option value="permutation">Không lặp (A-B, B-A...)</option>
                  </select>
                </div>
                <div>
                  <label>K - số clip/output</label>
                  <input type="number" min="1" max="10" value={batch.k} onChange={e=>update(batch.id,{k:+e.target.value})}/>
                </div>
                <div className="estimate">
                  <span>Dự kiến</span>
                  <b>{outputCount.toLocaleString()} output</b>
                </div>
                <button
                  className="primary"
                  disabled={!batch.selected.length || outputCount > 100}
                  onClick={()=>generate(batch)}
                >Sinh chuỗi</button>
              </div>

              {/* Manual timeline */}
              <div className="manual-line">
                <span>Timeline:</span>
                {selectedVideos.map(v=>(
                  <button key={v.id} onClick={()=>update(batch.id,{manual:[...batch.manual,v.id]})}>+ {labels[v.id]}</button>
                ))}
                <div className="timeline">
                  {batch.manual.map((id,i)=>(
                    <button key={`${id}-${i}`} onClick={()=>update(batch.id,{manual:batch.manual.filter((_,x)=>x!==i)})}>{labels[id]} ×</button>
                  ))}
                </div>
                <button className="secondary" disabled={!batch.manual.length} onClick={()=>manual(batch)}>Lưu timeline</button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Sequences created */}
      <h2 className="top-gap">Sequence đã tạo</h2>
      {groups.map(([name,items])=>(
        <div className="panel sequence-group" key={name}>
          <div className="panel-heading"><h3>{name} <span className="count">{items.length}</span></h3><button className="danger-button" onClick={()=>deleteSavedBatch(name)}><Trash2 size={14}/> Xóa batch</button></div>
          <div className="sequence-list">
            {items.map(seq=>(
              <label className={seq.enabled?'sequence enabled':'sequence'} key={seq.id}>
                <input type="checkbox" checked={seq.enabled} onChange={()=>toggleSequence(seq)}/>
                <strong>{seq.name}</strong>
                <span>{seq.items.map(i=>i.asset.display_name).join(' → ')}</span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}

function SequencePreviewModal({
  sequence,
  assignment,
  audios,
  patchAssignment,
  close,
}: {
  sequence: VideoSequence
  assignment: Assignment
  audios: Asset[]
  patchAssignment: (id: string, values: Partial<Assignment>) => void
  close: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const voiceRef = useRef<HTMLAudioElement>(null)
  const bgmRef = useRef<HTMLAudioElement>(null)

  const [clipIndex, setClipIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const clips = sequence.items || []
  const currentClip = clips[clipIndex]?.asset

  const voiceAsset = audios.find(a => a.id === assignment.audioId)
  const bgmAsset = audios.find(a => a.id === assignment.bgmId)

  const totalClipsMs = useMemo(() => clips.reduce((acc, c) => acc + (c.asset.duration_ms || 0), 0), [clips])
  const totalClipsSec = totalClipsMs / 1000 || 10
  const voiceSec = (voiceAsset?.duration_ms || 0) / 1000
  const totalDuration = Math.max(totalClipsSec, voiceSec || 0)

  useEffect(() => {
    if (voiceRef.current) voiceRef.current.volume = Math.min(1, Math.max(0, assignment.voiceVolume))
    if (bgmRef.current) bgmRef.current.volume = Math.min(1, Math.max(0, assignment.bgmVolume))
    if (videoRef.current) videoRef.current.muted = assignment.muteOriginal
  }, [assignment.voiceVolume, assignment.bgmVolume, assignment.muteOriginal])

  const togglePlay = () => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
      voiceRef.current?.pause()
      bgmRef.current?.pause()
      setIsPlaying(false)
    } else {
      videoRef.current.play().catch(() => {})
      if (voiceAsset && voiceRef.current) voiceRef.current.play().catch(() => {})
      if (bgmAsset && bgmRef.current) bgmRef.current.play().catch(() => {})
      setIsPlaying(true)
    }
  }

  const handleClipEnded = () => {
    if (clipIndex < clips.length - 1) {
      setClipIndex(prev => prev + 1)
    } else {
      if (voiceRef.current && !voiceRef.current.paused && voiceRef.current.currentTime < (voiceSec - 0.5)) {
        setClipIndex(0)
      } else {
        setIsPlaying(false)
        setClipIndex(0)
        if (voiceRef.current) { voiceRef.current.pause(); voiceRef.current.currentTime = 0 }
        if (bgmRef.current) { bgmRef.current.pause(); bgmRef.current.currentTime = 0 }
      }
    }
  }

  useEffect(() => {
    if (isPlaying && videoRef.current) {
      videoRef.current.currentTime = 0
      videoRef.current.play().catch(() => {})
    }
  }, [clipIndex, isPlaying])

  const handleTimeUpdate = () => {
    if (!videoRef.current) return
    let elapsedBefore = 0
    for (let i = 0; i < clipIndex; i++) {
      elapsedBefore += (clips[i].asset.duration_ms || 0) / 1000
    }
    const currentTotal = elapsedBefore + (videoRef.current.currentTime || 0)
    setCurrentTime(currentTotal)

    if (bgmRef.current && !bgmRef.current.paused && bgmAsset?.duration_ms) {
      const bgmTarget = currentTotal % (bgmAsset.duration_ms / 1000)
      if (Math.abs(bgmRef.current.currentTime - bgmTarget) > 0.4) {
        bgmRef.current.currentTime = bgmTarget
      }
    }
  }

  const handleSeek = (sec: number) => {
    setCurrentTime(sec)
    let acc = 0
    let targetClip = 0
    let offsetInClip = 0
    for (let i = 0; i < clips.length; i++) {
      const d = (clips[i].asset.duration_ms || 0) / 1000
      if (sec <= acc + d || i === clips.length - 1) {
        targetClip = i
        offsetInClip = Math.max(0, sec - acc)
        break
      }
      acc += d
    }
    setClipIndex(targetClip)
    if (videoRef.current) videoRef.current.currentTime = offsetInClip
    if (voiceRef.current && voiceAsset) voiceRef.current.currentTime = Math.min(sec, voiceSec)
    if (bgmRef.current && bgmAsset?.duration_ms) {
      bgmRef.current.currentTime = sec % (bgmAsset.duration_ms / 1000)
    }
  }

  return (
    <div className="modal-backdrop" onClick={close}>
      <div className="modal preview-modal" onClick={e => e.stopPropagation()}>
        <div className="panel-heading">
          <div>
            <h2>Xem & nghe thử video</h2>
            <p><span className="batch-tag">{sequence.batch_name}</span> <b>{sequence.name}</b></p>
          </div>
          <button className="icon-button" onClick={close}><X size={18} /></button>
        </div>

        <div className="preview-player-wrapper">
          {currentClip ? (
            <video
              ref={videoRef}
              src={streamUrl(currentClip.id)}
              onEnded={handleClipEnded}
              onTimeUpdate={handleTimeUpdate}
              playsInline
            />
          ) : (
            <div className="empty">Sequence không có clip nào</div>
          )}

          {voiceAsset && (
            <audio ref={voiceRef} src={streamUrl(voiceAsset.id)} onEnded={() => {
              if (clipIndex >= clips.length - 1) setIsPlaying(false)
            }} />
          )}
          {bgmAsset && (
            <audio ref={bgmRef} src={streamUrl(bgmAsset.id)} loop />
          )}

          <div className="preview-clip-badge">
            Clip {clipIndex + 1}/{clips.length}: {currentClip?.display_name}
          </div>
        </div>

        <div className="preview-controls">
          <button className="preview-play-btn" onClick={togglePlay}>
            {isPlaying ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
          </button>
          <span className="time-display">{formatDuration(currentTime * 1000)} / {formatDuration(totalDuration * 1000)}</span>
          <input
            type="range"
            min="0"
            max={totalDuration || 1}
            step="0.1"
            value={currentTime}
            onChange={e => handleSeek(+e.target.value)}
            className="preview-seekbar"
          />
        </div>

        <div className="preview-mixer">
          <h3>Điều chỉnh âm lượng realtime</h3>
          <div className="preview-mixer-grid">
            <div className={`preview-mixer-channel ${voiceAsset ? 'active' : ''}`}>
              <div className="channel-header">
                <AudioLines size={15} color="#9d86ff" />
                <span>Giọng đọc (Voice)</span>
                <b>{voiceAsset ? `${Math.round(assignment.voiceVolume * 100)}%` : 'Chưa gán'}</b>
              </div>
              <small title={voiceAsset?.display_name}>{voiceAsset?.display_name || 'Kéo audio vào sequence để thêm'}</small>
              <input
                type="range"
                min="0"
                max="2"
                step="0.05"
                disabled={!voiceAsset}
                value={assignment.voiceVolume}
                onChange={e => patchAssignment(sequence.id, { voiceVolume: +e.target.value })}
              />
            </div>

            <div className={`preview-mixer-channel ${bgmAsset ? 'active' : ''}`}>
              <div className="channel-header">
                <Music size={15} color="#29d5b0" />
                <span>Nhạc nền (BGM)</span>
                <b>{bgmAsset ? `${Math.round(assignment.bgmVolume * 100)}%` : 'Chưa gán'}</b>
              </div>
              <small title={bgmAsset?.display_name}>{bgmAsset?.display_name || 'Kéo nhạc nền vào sequence để thêm'}</small>
              <input
                type="range"
                min="0"
                max="1"
                step="0.02"
                disabled={!bgmAsset}
                value={assignment.bgmVolume}
                onChange={e => patchAssignment(sequence.id, { bgmVolume: +e.target.value })}
              />
            </div>

            <div className="preview-mixer-channel">
              <div className="channel-header">
                {assignment.muteOriginal ? <VolumeX size={15} color="#ee8498" /> : <Volume2 size={15} color="#58ddbe" />}
                <span>Tiếng gốc video</span>
                <b>{assignment.muteOriginal ? 'Đã tắt' : 'Đang bật'}</b>
              </div>
              <small>Tiếng thu âm gốc của file video</small>
              <label className="mute-toggle" style={{marginTop:'8px'}}>
                <input
                  type="checkbox"
                  checked={assignment.muteOriginal}
                  onChange={e => patchAssignment(sequence.id, { muteOriginal: e.target.checked })}
                />
                Tắt tiếng gốc video
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function RenderPanel({ projectId, audios, sequences, outputs, system, guarded, setTab, refresh }: any) {
  const enabled: VideoSequence[] = sequences.filter((s: VideoSequence) => s.enabled)
  const [assignments, setAssignments] = useState<Record<string, Assignment>>(() => {
    try { return JSON.parse(localStorage.getItem(`assignments:${projectId}`) || '{}') } catch { return {} }
  })
  useEffect(()=>{ localStorage.setItem(`assignments:${projectId}`, JSON.stringify(assignments)) },[assignments,projectId])
  const [allowDuplicate, setAllowDuplicate] = useState(false)
  const [allowMissing, setAllowMissing] = useState(false)
  const [runName, setRunName] = useState('san-pham')
  const [groupName, setGroupName] = useState('Nhóm render 1')
  const [outputFolder, setOutputFolder] = useState('renders')
  const [resolution, setResolution] = useState('1080x1920')
  const [encoder, setEncoder] = useState('h264_nvenc')
  const [fit, setFit] = useState('fit')
  const [durationPolicy, setDurationPolicy] = useState('match_audio_loop_video')
  const [audioTab, setAudioTab] = useState<'voice' | 'bgm'>('voice')
  const [voiceGroupFilter, setVoiceGroupFilter] = useState('all')
  const [uploadingBgm, setUploadingBgm] = useState(false)
  const [globalBgmTracks, setGlobalBgmTracks] = useState<BgmTrack[]>([])

  // Fetch global BGM library
  useEffect(() => {
    request<BgmTrack[]>('/bgm').then(setGlobalBgmTracks).catch(() => {})
  }, [])

  async function refreshBgmLibrary() {
    try { setGlobalBgmTracks(await request<BgmTrack[]>('/bgm')) } catch {}
  }
  const [previewSeq, setPreviewSeq] = useState<VideoSequence | null>(null)
  const [batchFilter, setBatchFilter] = useState<string[] | 'all'>('all')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const selectionInitialized = useRef(false)
  const batchNames = Array.from(new Set(enabled.map(seq => seq.batch_name))) as string[]
  const visibleSequences = batchFilter === 'all' ? enabled : enabled.filter(seq => batchFilter.includes(seq.batch_name))
  const selectedSequences = visibleSequences.filter(seq => selectedIds.includes(seq.id))
  const batchFilterLabel = batchFilter === 'all'
    ? 'Tất cả batch'
    : batchFilter.length === 0
      ? 'Chưa chọn batch'
      : batchFilter.length === 1
        ? batchFilter[0]
        : `${batchFilter.length} batch đã chọn`

  function toggleBatchFilter(batchName: string) {
    setBatchFilter(current => {
      const selected = current === 'all' ? batchNames : current
      return selected.includes(batchName)
        ? selected.filter(name => name !== batchName)
        : [...selected, batchName]
    })
  }

  useEffect(() => {
    const sequenceIds = new Set(enabled.map(seq => seq.id))
    const audioIds = new Set((audios as Asset[]).map(audio => audio.id))
    setAssignments(old => {
      let changed = false
      const next: Record<string, Assignment> = {}
      for (const [sequenceId, value] of Object.entries(old)) {
        if (!sequenceIds.has(sequenceId)) { changed = true; continue }
        const cleaned = {
          ...value,
          audioId: value.audioId && audioIds.has(value.audioId) ? value.audioId : '',
          bgmId: value.bgmId || '',
        }
        if (cleaned.audioId !== value.audioId || cleaned.bgmId !== value.bgmId) changed = true
        next[sequenceId] = cleaned
      }
      return changed ? next : old
    })
  }, [sequences, audios])

  useEffect(() => {
    const validIds = enabled.map(seq => seq.id)
    if (!selectionInitialized.current && validIds.length) {
      setSelectedIds(validIds)
      selectionInitialized.current = true
    } else setSelectedIds(old => old.filter(id => validIds.includes(id)))
  }, [sequences])

  const assigned = (id: string): Assignment =>
    assignments[id] || {
      audioId: '',
      bgmId: '',
      muteOriginal: true,
      customName: '',
      voiceVolume: 1.0,
      bgmVolume: 1.0,
    }

  const patchAssignment = (id: string, values: Partial<Assignment>) => {
    if (values.audioId && Object.entries(assignments).some(([key,value])=>key!==id && value.audioId===values.audioId)) {
      if (!allowDuplicate || !confirm('Audio đã được gán cho video khác. Cho phép dùng lại audio này?')) return
    }
    setAssignments(old => ({ ...old, [id]: { ...assigned(id), ...values } }))
  }

  // Phân loại audio
  const voiceAudios = audios.filter((a: Asset) => a.type === 'tts_audio' || (!a.display_name.toLowerCase().includes('bgm') && a.type !== 'external_audio'))
  // bgmAudios replaced by globalBgmTracks (global BGM library)
  const bgmAudios = globalBgmTracks
  const voiceGroups = Array.from(new Set(voiceAudios.map((a: Asset) => String(a.metadata_json.group_name || '')).filter(Boolean))) as string[]
  const filteredVoiceAudios = voiceGroupFilter === 'all' ? voiceAudios : voiceAudios.filter((a: Asset) => String(a.metadata_json.group_name || '') === voiceGroupFilter)
  const usedVoiceAudioIds = new Set((sequences as VideoSequence[]).map(seq => assignments[seq.id]?.audioId).filter(Boolean))
  const availableFilteredVoiceAudios = filteredVoiceAudios.filter((audio: Asset) => !usedVoiceAudioIds.has(audio.id))
  const selectedTargetHasAllVoice = !selectedSequences.some(seq=>!assigned(seq.id).audioId)
  const missingAudioCount = selectedSequences.filter(seq=>!assigned(seq.id).audioId).length

  // Gán ngẫu nhiên audio chưa dùng cho từng video, tuyệt đối không lặp khi gán hàng loạt.
  function applyAudioGroupToBatch() {
    if (voiceGroupFilter === 'all' || availableFilteredVoiceAudios.length === 0 || selectedTargetHasAllVoice) return
    const targetSeqs = selectedSequences
    const emptyTargetSeqs = targetSeqs.filter(seq => !assigned(seq.id).audioId)
    if (!emptyTargetSeqs.length) return
    const shuffledAudios = [...availableFilteredVoiceAudios]
    for (let index = shuffledAudios.length - 1; index > 0; index--) {
      const randomIndex = Math.floor(Math.random() * (index + 1))
      ;[shuffledAudios[index], shuffledAudios[randomIndex]] = [shuffledAudios[randomIndex], shuffledAudios[index]]
    }
    setAssignments(old => {
      const next = { ...old }
      const used = new Set((sequences as VideoSequence[]).map(seq=>old[seq.id]?.audioId).filter(Boolean))
      const available = shuffledAudios.filter(audio=>!used.has(audio.id))
      emptyTargetSeqs.filter(seq=>!old[seq.id]?.audioId).slice(0, available.length).forEach((seq, index) => {
        const audio = available[index]
        next[seq.id] = { ...(next[seq.id] || assigned(seq.id)), audioId: audio.id }
      })
      return next
    })
  }

  async function handleUploadBgm(files: FileList | null) {
    if (!files?.length) return
    await guarded(async () => {
      setUploadingBgm(true)
      const form = new FormData()
      Array.from(files).forEach(f => form.append('files', f))
      await request<BgmTrack[]>('/bgm/upload', { method: 'POST', body: form })
      await refreshBgmLibrary()
      setUploadingBgm(false)
    })
  }

  async function deleteBgmTrack(trackId: string) {
    if (!confirm('Xóa nhạc nền này khỏi kho?')) return
    await request('/bgm/' + trackId, { method: 'DELETE' })
    await refreshBgmLibrary()
  }

  function applyBgmToAll(bgmId: string) {
    setAssignments(old => {
      const next = { ...old }
      for (const seq of selectedSequences) {
        next[seq.id] = { ...assigned(seq.id), bgmId, bgmVolume: 1.0 }
      }
      return next
    })
  }

  function toggleVisibleSelection() {
    const visibleIds = visibleSequences.map(seq => seq.id)
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.includes(id))
    setSelectedIds(old => allSelected
      ? old.filter(id => !visibleIds.includes(id))
      : Array.from(new Set([...old, ...visibleIds])))
  }

  function setMuteForSelected(muteOriginal: boolean) {
    setAssignments(old => {
      const next = {...old}
      for (const seq of selectedSequences) next[seq.id] = {...assigned(seq.id), muteOriginal}
      return next
    })
  }

  async function deleteRenderSequence(sequence: VideoSequence) {
    if (!confirm(`Xóa video ${sequence.name} khỏi ${sequence.batch_name}?`)) return
    await guarded(async () => {
      await request(`/sequences/${sequence.id}`, { method: 'DELETE' })
      setSelectedIds(old => old.filter(id => id !== sequence.id))
      if (refresh) await refresh()
    })
  }

  async function render() {
    await guarded(async () => {
      if (!allowMissing && missingAudioCount) throw new Error(`Còn ${missingAudioCount} video chưa có audio`)
      await request(
        `/projects/${projectId}/render/jobs`,
        jsonOptions('POST', {
          items: selectedSequences.map(seq => {
            const a = assigned(seq.id)
            return {
              sequence_id: seq.id,
              audio_asset_id: a.audioId || null,
              bgm_asset_id: a.bgmId || null,
              source_audio_policy: a.muteOriginal ? 'mute' : 'mix',
              voice_volume: a.voiceVolume ?? 1.0,
              bgm_volume: a.bgmVolume ?? 1.0,
              custom_name: runName,
            }
          }),
          run_name: runName,
          group_name: groupName,
          output_folder: outputFolder,
          allow_missing_audio: allowMissing,
          allow_duplicate_audio: allowDuplicate,
          duration_policy: durationPolicy,
          resolution,
          fps: 30,
          video_encoder: encoder,
          fit_mode: fit,
          voice_volume: 1,
          source_volume: 0.25,
          bgm_volume: 1.0,
        })
      )
      setTab('jobs')
    })
  }

  return (
    <section>
      <div className="section-title">
        <div>
          <h2>Gán audio & nhạc nền cho từng video</h2>
          <p>Chọn video, chọn nhóm audio rồi gán tay hoặc gán ngẫu nhiên hàng loạt. Audio đã dùng được loại khỏi danh sách.</p>
        </div>
      </div>

      {/* ── Audio & BGM Trays ── */}
      <div className="audio-tray-panel">
        <div className="audio-tray-tabs">
          <div className="segmented">
            <button className={audioTab === 'voice' ? 'active' : ''} onClick={() => setAudioTab('voice')}>
              <AudioLines size={14} /> Giọng đọc ({voiceAudios.length})
            </button>
            <button className={audioTab === 'bgm' ? 'active' : ''} onClick={() => setAudioTab('bgm')}>
              <Music size={14} /> Kho nhạc nền ({globalBgmTracks.length})
            </button>
          </div>
          {audioTab === 'bgm' && (
            <label className="button small">
              <Upload size={13} /> {uploadingBgm ? 'Đang tải...' : 'Thêm nhạc nền'}
              <input hidden multiple type="file" accept="audio/*" disabled={uploadingBgm} onChange={e => handleUploadBgm(e.target.files)} />
            </label>
          )}
          {audioTab === 'voice' && (
            <div className="audio-group-assign-row">
              <select className="audio-group-filter" value={voiceGroupFilter} onChange={e => { setVoiceGroupFilter(e.target.value) }}>
                <option value="all">Tất cả nhóm audio</option>
                {voiceGroups.map(group => <option value={group} key={group}>{group}</option>)}
              </select>
              {voiceGroupFilter !== 'all' && <span className="audio-available-count">Còn {availableFilteredVoiceAudios.length}/{filteredVoiceAudios.length} audio chưa gán</span>}
              {voiceGroupFilter !== 'all' && (
                <div className="audio-group-apply">
                  <span className="audio-group-target" title="Các batch video đang được hiển thị">{batchFilterLabel} · chỉ video được chọn</span>
                  <button
                    className="apply-group-btn"
                    disabled={selectedTargetHasAllVoice || availableFilteredVoiceAudios.length === 0}
                    onClick={applyAudioGroupToBatch}
                    title={selectedTargetHasAllVoice ? 'Batch này đã được gán đủ audio' : `Gán lần lượt audio chưa dùng của nhóm "${voiceGroupFilter}" vào batch`}
                  >
                    <Wand2 size={13} /> Gán vào video đã chọn
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {audioTab === 'voice' ? (
          <div className="audio-tray-scroll">
            {availableFilteredVoiceAudios.length === 0 ? (
              <p className="muted" style={{padding:'12px'}}>{filteredVoiceAudios.length ? 'Tất cả audio trong nhóm này đã được gán. Tháo audio khỏi video để sử dụng lại.' : 'Chưa có giọng đọc. Hãy vào tab "Tạo giọng" để sinh audio TTS.'}</p>
            ) : (
              availableFilteredVoiceAudios.map((a: Asset) => (
                <article
                  key={a.id}
                  className="audio-card voice-card"
                  title="Nghe thử; dùng dropdown trong từng video để gán"
                >
                  <div className="audio-card-top">
                    <AudioLines size={15} color="#9d86ff" />
                    <div>
                      <b>{a.display_name}</b>
                      <span>{String(a.metadata_json.group_name || 'Riêng')} · {formatDuration(a.duration_ms)} · {formatDateTime(a.created_at)}</span>
                    </div>
                  </div>
                  <audio controls preload="none" src={streamUrl(a.id)} />
                </article>
              ))
            )}
          </div>
        ) : (
          <div className="audio-tray-scroll">
            {globalBgmTracks.length === 0 ? (
              <p className="muted" style={{padding:'12px'}}>Kho nhạc nền trống. Bấm "Thêm nhạc nền" để upload file MP3/WAV vào kho dùng chung.</p>
            ) : (
              globalBgmTracks.map((t: BgmTrack) => (
                <article
                  draggable
                  onDragStart={e => {
                    e.dataTransfer.setData('type', 'bgm')
                    e.dataTransfer.setData('bgmId', t.id)
                  }}
                  key={t.id}
                  className="audio-card bgm-card"
                  title="Kéo thả vào ô Nhạc nền của sequence"
                >
                  <div className="audio-card-top">
                    <Music size={15} color="#29d5b0" />
                    <div>
                      <b>{t.display_name}</b>
                      <span>{formatDuration(t.duration_ms)}{t.tags ? ` · ${t.tags}` : ''} · {formatDateTime(t.created_at)}</span>
                    </div>
                  </div>
                  <audio controls preload="none" src={bgmStreamUrl(t.id)} />
                  <div className="bgm-card-footer">
                    <button
                      type="button"
                      className="bgm-apply-btn"
                      title="Gán nhạc này cho tất cả video đã chọn"
                      onClick={() => applyBgmToAll(t.id)}
                    >
                      Áp dụng cho video đã chọn
                    </button>
                    <button
                      type="button"
                      className="bgm-delete-btn"
                      title="Xóa khỏi kho"
                      onClick={() => deleteBgmTrack(t.id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        )}
      </div>

      <div className="batch-render-toolbar">
        <div className="batch-multi-field">
          <label>Chọn một hoặc nhiều batch</label>
          <details className="batch-multi-select">
            <summary>{batchFilterLabel}</summary>
            <div className="batch-multi-menu">
              <label className="batch-multi-option select-all">
                <input
                  type="checkbox"
                  checked={batchFilter === 'all'}
                  onChange={() => setBatchFilter('all')}
                />
                <span>Tất cả batch</span>
              </label>
              {batchNames.map(name => (
                <label className="batch-multi-option" key={name}>
                  <input
                    type="checkbox"
                    checked={batchFilter === 'all' || batchFilter.includes(name)}
                    onChange={() => toggleBatchFilter(name)}
                  />
                  <span>{name}</span>
                  <small>{enabled.filter(seq => seq.batch_name === name).length} video</small>
                </label>
              ))}
            </div>
          </details>
        </div>
        <button className="secondary" onClick={toggleVisibleSelection}>
          {visibleSequences.length > 0 && visibleSequences.every(seq => selectedIds.includes(seq.id)) ? 'Bỏ chọn các batch' : 'Chọn toàn bộ các batch'}
        </button>
        <button className="secondary" disabled={!selectedSequences.length} onClick={()=>setMuteForSelected(true)}><VolumeX size={14}/> Tắt tiếng hàng loạt</button>
        <button className="secondary" disabled={!selectedSequences.length} onClick={()=>setMuteForSelected(false)}><Volume2 size={14}/> Bật tiếng hàng loạt</button>
        <span>{selectedSequences.length}/{visibleSequences.length} video được chọn</span>
      </div>

      {/* ── Render Sequences Grid ── */}
      <div className="render-grid">
        {visibleSequences.map(seq => {
          const a = assigned(seq.id)
          const voice = audios.find((x: Asset) => x.id === a.audioId)
          const bgm = audios.find((x: Asset) => x.id === a.bgmId)

          return (
            <article
              className="render-card"
              key={seq.id}
              onDragOver={e => e.preventDefault()}
              onDrop={e => {
                e.preventDefault()
                const type = e.dataTransfer.getData('type')
                const bid = e.dataTransfer.getData('bgmId')
                if (type === 'bgm' && bid) patchAssignment(seq.id, { bgmId: bid, bgmVolume: 1.0 })
                else if (bid) patchAssignment(seq.id, { bgmId: bid, bgmVolume: 1.0 })
              }}
            >
              <div className="render-preview">
                {seq.items.map((item, index) => (
                  <video key={item.id} controls muted preload="metadata" src={streamUrl(item.asset.id)} className={index === 0 ? 'main-preview' : 'mini-preview'} />
                ))}
              </div>

              <div className="render-card-body">
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                  <div style={{display:'flex',alignItems:'center',gap:'8px'}}>
                    <input className="sequence-select" type="checkbox" checked={selectedIds.includes(seq.id)} onChange={e => setSelectedIds(old => e.target.checked ? Array.from(new Set([...old, seq.id])) : old.filter(id => id !== seq.id))} />
                    <span className="batch-tag">{seq.batch_name}</span>
                    <b>{seq.name}</b>
                  </div>
                  <div className="render-card-actions"><button className="preview-trigger-btn" onClick={() => setPreviewSeq(seq)}><Eye size={13} /> Xem & nghe thử</button><button className="delete-sequence-btn" onClick={() => deleteRenderSequence(seq)} title="Xóa video khỏi batch"><Trash2 size={13} /></button></div>
                </div>
                <p>{seq.items.map(i => i.asset.display_name).join(' → ')}</p>

                {/* Drop Zone: Giọng đọc */}
                <div
                  className={`audio-drop-slot voice-slot ${voice ? 'filled' : ''}`}
                >
                  <div className="slot-title">
                    <AudioLines size={14} color="#9d86ff" />
                    <span>Giọng đọc (Voice)</span>
                  </div>
                  <select aria-label="Chọn giọng đọc cho video" value={a.audioId} onChange={e=>patchAssignment(seq.id,{audioId:e.target.value})}>
                    <option value="">Chọn audio chưa gán…</option>
                    {voice && <option value={voice.id}>{voice.display_name} · đang gán</option>}
                    {filteredVoiceAudios.filter((audio:Asset)=>audio.id!==a.audioId && (allowDuplicate || !usedVoiceAudioIds.has(audio.id))).map((audio:Asset)=><option key={audio.id} value={audio.id}>{audio.display_name}{usedVoiceAudioIds.has(audio.id)?' · đã dùng (cần xác nhận)':''}</option>)}
                  </select>
                  {voice ? (
                    <div className="slot-content">
                      <span className="slot-name" title={voice.display_name}>{voice.display_name}</span>
                      <button className="slot-remove" onClick={() => patchAssignment(seq.id, { audioId: '' })}>×</button>
                    </div>
                  ) : (
                    <div className="slot-placeholder">Chọn audio từ dropdown phía trên</div>
                  )}
                  {voice && (
                    <div className="volume-slider-row">
                      <span>Âm lượng: <b>{Math.round((a.voiceVolume ?? 1.0) * 100)}%</b></span>
                      <input
                        type="range"
                        min="0"
                        max="2"
                        step="0.05"
                        value={a.voiceVolume ?? 1.0}
                        onChange={e => patchAssignment(seq.id, { voiceVolume: +e.target.value })}
                      />
                    </div>
                  )}
                </div>

                {/* Drop Zone: Nhạc nền */}
                <div
                  className={`audio-drop-slot bgm-slot ${bgm ? 'filled' : ''}`}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => {
                    e.stopPropagation()
                    const id = e.dataTransfer.getData('bgmId') || e.dataTransfer.getData('audioId')
                    if (id) patchAssignment(seq.id, { bgmId: id, bgmVolume: 1.0 })
                  }}
                >
                  <div className="slot-title">
                    <Music size={14} color="#29d5b0" />
                    <span>Nhạc nền (BGM)</span>
                  </div>
                  {bgm ? (
                    <div className="slot-content">
                      <span className="slot-name" title={bgm.display_name}>{bgm.display_name}</span>
                      <button className="slot-remove" onClick={() => patchAssignment(seq.id, { bgmId: '' })}>×</button>
                    </div>
                  ) : (
                    <div className="slot-placeholder">Kéo nhạc nền vào đây</div>
                  )}
                  {bgm && (
                    <div className="volume-slider-row">
                      <span>Âm lượng: <b>{Math.round((a.bgmVolume ?? 1.0) * 100)}%</b></span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.02"
                        value={a.bgmVolume ?? 1.0}
                        onChange={e => patchAssignment(seq.id, { bgmVolume: +e.target.value })}
                      />
                    </div>
                  )}
                </div>

                <label className="mute-toggle">
                  <input type="checkbox" checked={a.muteOriginal} onChange={e => patchAssignment(seq.id, { muteOriginal: e.target.checked })} /> Tắt tiếng gốc video
                </label>
              </div>
            </article>
          )
        })}
      </div>

      <div className="render-permissions">
        <p>{selectedSequences.length} video được chọn · {missingAudioCount} video còn thiếu audio</p>
        <label><input type="checkbox" checked={allowDuplicate} onChange={e=>setAllowDuplicate(e.target.checked)}/> Cho phép dùng trùng khi gán tay (cần xác nhận)</label>
        <label><input type="checkbox" checked={allowMissing} onChange={e=>setAllowMissing(e.target.checked)}/> Cho phép xuất video thiếu audio</label>
      </div>
      {/* ── Render Settings Panel ── */}
      <div className="panel render-settings">
        <div><label>Tên nhóm render</label><input maxLength={100} value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="Ví dụ: Nhóm túi xách 01" /></div>
        <div><label>Thư mục output</label><input value={outputFolder} onChange={e => setOutputFolder(e.target.value)} placeholder="Ví dụ: chien-dich-thang-9" /></div>
        <div><label>Tên file output (tự thêm index)</label><input value={runName} onChange={e => setRunName(e.target.value)} placeholder="Ví dụ: gocdoxinh" /></div>
        <div><label>Tỷ lệ video</label><select value={resolution} onChange={e => setResolution(e.target.value)}><option value="1080x1920">9:16 · 1080×1920</option><option value="1920x1080">16:9 · 1920×1080</option><option value="1280x720">16:9 · 1280×720</option></select></div>
        <div><label>Khung hình</label><select value={fit} onChange={e => setFit(e.target.value)}><option value="fit">Fit + viền</option><option value="fill">Fill + crop</option></select></div>
        <div><label>Độ dài</label><select value={durationPolicy} onChange={e => setDurationPolicy(e.target.value)}><option value="match_audio_loop_video">Theo audio</option><option value="match_video">Theo video</option><option value="shortest">Nguồn ngắn hơn</option></select></div>
        <div><label>Encoder</label><select value={encoder} onChange={e => setEncoder(e.target.value)}><option value="libx264">CPU · libx264</option><option value="h264_nvenc">GPU · NVENC{system?.media?.nvenc === false ? ' (chưa khả dụng)' : ''}</option></select></div>
        <button className="primary" disabled={!selectedSequences.length || !groupName.trim() || !runName.trim() || !outputFolder.trim() || (!allowMissing && missingAudioCount>0)} onClick={render}><Clapperboard size={16} /> Render {selectedSequences.length} video</button>
      </div>

      {outputs.length > 0 && (
        <>
          <h2 className="top-gap">Output gần đây</h2>
          <div className="output-grid">
            {outputs.slice(0, 6).map((o: Asset) => (
              <article key={o.id}>
                <video controls src={streamUrl(o.id)} />
                <strong>{o.display_name}</strong>
              </article>
            ))}
          </div>
        </>
      )}

      {/* ── Live Preview Modal ── */}
      {previewSeq && (
        <SequencePreviewModal
          sequence={previewSeq}
          assignment={assigned(previewSeq.id)}
          audios={audios}
          patchAssignment={patchAssignment}
          close={() => setPreviewSeq(null)}
        />
      )}
    </section>
  )
}

function JobsPanel({ jobs, outputs, refresh, guarded }: { jobs:Job[]; outputs:Asset[]; refresh:()=>Promise<void>; guarded:Guard }) {
  const [renameNames,setRenameNames]=useState<Record<string,string>>({})
  const [allOutputsName,setAllOutputsName]=useState('')
  const [selectedOutputIds,setSelectedOutputIds]=useState<string[]>([])
  const [downloading,setDownloading]=useState(false)
  const [downloadProgress,setDownloadProgress]=useState('')
  const [selectingFolder,setSelectingFolder]=useState<string|null>(null)
  const [downloadRoot,setDownloadRoot]=useState<FileSystemDirectoryHandle|null>(rememberedDownloadRoot)
  const [gridDensity,setGridDensity]=useState<'large'|'compact'|'small'>(()=>{
    const saved=localStorage.getItem('outputGridDensity')
    return saved==='large'||saved==='small'?'large'===saved?'large':'small':'compact'
  })
  useEffect(()=>localStorage.setItem('outputGridDensity',gridDensity),[gridDensity])
  async function action(job:Job,kind:'cancel'|'retry'){await guarded(async()=>{await request(`/jobs/${job.id}/${kind}`,{method:'POST'});await refresh()})}
  const renderBatchKey = (job:Job) => String(job.input_json.group_name || job.input_json.run_timestamp || job.input_json.run_folder || job.input_json.batch_name || job.id)
  const visibleJobs = useMemo(()=>{
    const recentBatches = new Set([...jobs].filter(job=>job.kind==='render').sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at)).map(renderBatchKey).filter((key,index,array)=>array.indexOf(key)===index).slice(0,3))
    return jobs.filter(job=>['queued','running','processing','rendering'].includes(job.status) || (job.kind==='render' && recentBatches.has(renderBatchKey(job))))
  },[jobs])
  const outputGroups=useMemo(()=>Object.entries(groupBy(outputs,o=>String(
    o.metadata_json?.group_name ||
    (o.metadata_json?.run_timestamp
      ? `${o.metadata_json?.custom_name || 'Nhóm render'} - ${o.metadata_json.run_timestamp}`
      : o.metadata_json?.run_folder || 'Output cũ')
  ))),[outputs])
  async function renameGroup(folder:string,items:Asset[]){
    const baseName=(renameNames[folder]||'').trim(); if(!baseName)return
    const ordered=[...items].sort((a,b)=>Number(a.metadata_json.output_index||0)-Number(b.metadata_json.output_index||0)||new Date(a.created_at).getTime()-new Date(b.created_at).getTime())
    await guarded(async()=>{await request(`/projects/${items[0].project_id}/outputs/rename`,jsonOptions('PATCH',{asset_ids:ordered.map(item=>item.id),base_name:baseName}));await refresh()})
  }
  async function renameAllOutputs(){
    const baseName=allOutputsName.trim();if(!baseName||!outputs.length)return
    const ordered=[...outputs].sort((a,b)=>String(a.metadata_json?.run_folder||'').localeCompare(String(b.metadata_json?.run_folder||''),'vi')||Number(a.metadata_json.output_index||0)-Number(b.metadata_json.output_index||0)||new Date(a.created_at).getTime()-new Date(b.created_at).getTime())
    await guarded(async()=>{await request(`/projects/${ordered[0].project_id}/outputs/rename`,jsonOptions('PATCH',{asset_ids:ordered.map(item=>item.id),base_name:baseName}));setAllOutputsName('');await refresh()})
  }
  function toggleOutputGroup(items:Asset[]){
    const ids=items.map(item=>item.id); const all=ids.every(id=>selectedOutputIds.includes(id))
    setSelectedOutputIds(old=>all?old.filter(id=>!ids.includes(id)):Array.from(new Set([...old,...ids])))
  }
  async function chooseDownloadRoot(){
    if(!window.showDirectoryPicker)throw new Error('Trình duyệt không hỗ trợ chọn thư mục. Hãy dùng Chrome hoặc Edge phiên bản mới.')
    try{const directory=await window.showDirectoryPicker({mode:'readwrite'});rememberedDownloadRoot=directory;setDownloadRoot(directory);return directory}catch(error){if(error instanceof DOMException&&error.name==='AbortError')return null;throw error}
  }
  async function downloadOutputs(folder:string,items:Asset[],downloadWholeFolder=false){
    const selected=downloadWholeFolder?items:items.filter(item=>selectedOutputIds.includes(item.id)); if(!selected.length)return
    await guarded(async()=>{
      setDownloading(true)
      try{
        const root=downloadRoot||await chooseDownloadRoot();if(!root)return
        const safeFolderName=folder.replace(/[<>:"/\\|?*\x00-\x1F]/g,'-').replace(/[. ]+$/g,'').trim()||'output'
        const directory=await root.getDirectoryHandle(safeFolderName,{create:true})
        let cursor=0;let completed=0
        const worker=async()=>{while(true){
          const index=cursor++;if(index>=selected.length)return
          const item=selected[index]
          const response=await fetch(streamUrl(item.id));if(!response.ok)throw new Error(`Không tải được ${item.display_name}`)
          const fileHandle=await directory.getFileHandle(item.display_name,{create:true});const writable=await fileHandle.createWritable()
          try{await writable.write(await response.blob())}finally{await writable.close()}
          completed++;setDownloadProgress(`${completed}/${selected.length}`)
        }}
        await Promise.all(Array.from({length:Math.min(3,selected.length)},worker))
      }finally{setDownloading(false);setDownloadProgress('')}
    })
  }
  async function downloadAllOutputs(){
    if(!outputs.length)return
    const requestedName=prompt('Tên thư mục chứa toàn bộ video:','tat-ca-video')?.trim();if(!requestedName)return
    await guarded(async()=>{
      setDownloading(true)
      try{
        const root=downloadRoot||await chooseDownloadRoot();if(!root)return
        const safeFolderName=requestedName.replace(/[<>:"/\\|?*\x00-\x1F]/g,'-').replace(/[. ]+$/g,'').trim()||'tat-ca-video'
        const directory=await root.getDirectoryHandle(safeFolderName,{create:true})
        const usedNames=new Set<string>();let cursor=0;let completed=0
        const worker=async()=>{while(true){
          const index=cursor++;if(index>=outputs.length)return
          const item=outputs[index];const original=item.display_name;const dot=original.lastIndexOf('.');const stem=dot>0?original.slice(0,dot):original;const suffix=dot>0?original.slice(dot):''
          let fileName=original;let counter=2
          while(usedNames.has(fileName.toLocaleLowerCase()))fileName=`${stem}-${counter++}${suffix}`
          usedNames.add(fileName.toLocaleLowerCase())
          const response=await fetch(streamUrl(item.id));if(!response.ok)throw new Error(`Không tải được ${item.display_name}`)
          const fileHandle=await directory.getFileHandle(fileName,{create:true});const writable=await fileHandle.createWritable()
          try{await writable.write(await response.blob())}finally{await writable.close()}
          completed++;setDownloadProgress(`${completed}/${outputs.length}`)
        }}
        await Promise.all(Array.from({length:Math.min(3,outputs.length)},worker))
      }finally{setDownloading(false);setDownloadProgress('')}
    })
  }
  return <section><div className="section-title"><div><h2>Công việc & kết quả</h2><p>Tối đa 3 job media chạy đồng thời; TTS được khóa riêng để an toàn GPU.</p></div><div className="download-root-picker"><span>{downloadRoot?`Thư mục lưu: ${downloadRoot.name}`:'Chưa chọn thư mục lưu'}</span><button className="secondary" onClick={()=>guarded(async()=>{await chooseDownloadRoot()})}><FolderOpen size={15}/>{downloadRoot?'Đổi thư mục lưu':'Chọn thư mục lưu'}</button></div></div><div className="results-layout"><div className="results-videos"><div className="all-output-actions"><button className="primary download-all-batches" disabled={!outputs.length||downloading} onClick={downloadAllOutputs}><Download size={15}/>{downloading?`Đang tải ${downloadProgress}`:`Tải toàn bộ ${outputGroups.length} batch (${outputs.length} video)`}</button><div className="bulk-rename-all"><input value={allOutputsName} onChange={e=>setAllOutputsName(e.target.value)} placeholder="Tên mới cho toàn bộ video"/><button className="secondary" disabled={!allOutputsName.trim()||!outputs.length} onClick={renameAllOutputs}>Đổi tên toàn bộ file</button></div></div><div className="grid-density-toolbar"><span>Kích thước lưới</span><div className="segmented">{([['large','Lớn'],['compact','Gọn'],['small','Nhỏ']] as const).map(([value,label])=><button key={value} className={gridDensity===value?'active':''} onClick={()=>setGridDensity(value)}>{label}</button>)}</div></div>
    {outputGroups.map(([folder,items])=>{const selectedCount=items.filter(item=>selectedOutputIds.includes(item.id)).length;const selecting=selectingFolder===folder;return <div key={folder} className="output-group"><div className="output-group-heading"><h2>{folder} <span className="count">{items.length}</span></h2><div className="output-download-actions"><button className={selecting?'primary':'secondary'} onClick={()=>{setSelectingFolder(selecting?null:folder);if(!selecting)setSelectedOutputIds(old=>old.filter(id=>!items.some(item=>item.id===id)))}}><Download size={15}/>{selecting?'Xong chọn': 'Chọn video để tải'}</button>{selecting&&<button className="secondary" onClick={()=>toggleOutputGroup(items)}>{selectedCount===items.length?'Bỏ chọn tất cả':'Chọn tất cả'}</button>}{selecting&&<button className="secondary" disabled={!selectedCount||downloading} onClick={()=>downloadOutputs(folder,items)}>{downloading?`Đang tải ${downloadProgress}`:`Tải ${selectedCount} đã chọn`}</button>}<button className="primary" disabled={downloading} onClick={()=>downloadOutputs(folder,items,true)}>{downloading?`Đang tải ${downloadProgress}`:`Tải cả thư mục (${items.length})`}</button></div><div className="bulk-rename"><input value={renameNames[folder]||''} onChange={e=>setRenameNames(old=>({...old,[folder]:e.target.value}))} placeholder="Tên mới, ví dụ: gocdoxinh"/><button className="secondary" disabled={!renameNames[folder]?.trim()} onClick={()=>renameGroup(folder,items)}>Đổi tên tất cả</button></div></div>{selecting&&<p className="selection-hint">Đang chọn tải: click vào từng video · đã chọn {selectedCount}/{items.length} · file sẽ lưu trong thư mục con {folder}</p>}<p className="rename-preview">Kết quả: {renameNames[folder]?.trim()||'ten-file'}-1.mp4, {renameNames[folder]?.trim()||'ten-file'}-2.mp4, …</p><div className={`output-grid density-${gridDensity}${selecting?' selecting':''}`}>{items.map(o=><article className={selectedOutputIds.includes(o.id)?'output-selected':''} key={o.id} onClick={()=>{if(selecting)setSelectedOutputIds(old=>old.includes(o.id)?old.filter(id=>id!==o.id):[...old,o.id])}}><div className="output-checkmark">{selectedOutputIds.includes(o.id)?'✓':''}</div><video controls={!selecting} src={streamUrl(o.id)} preload="metadata"/><strong>{o.display_name}</strong><span>{formatDuration(o.duration_ms)} · {o.width}×{o.height}</span></article>)}</div></div>})}
</div><aside className="jobs-sidebar"><h3>Đang chạy & 3 batch gần nhất</h3><div className="job-list">{visibleJobs.map(job=><article className="job" key={job.id}><div className={`job-status ${job.status}`}>{job.status==='completed'?<CheckCircle2/>:job.status==='failed'?<XCircle/>:<LoaderCircle className={['running','rendering','processing'].includes(job.status)?'spin':''}/>}</div><div className="job-body"><div><strong>{job.kind==='tts'?'Tạo giọng':job.kind==='audio_process'?'Chỉnh audio':'Render video'}</strong><span>{formatDateTime(job.created_at)} · {job.status} · {Math.round(job.progress)}%</span></div><div className="progress"><i style={{width:`${job.progress}%`}}/></div>{job.error_message&&<p className="job-error">{job.error_message}</p>}</div><div className="job-actions">{['queued','running','rendering','processing'].includes(job.status)&&<button onClick={()=>action(job,'cancel')}>Hủy</button>}{['failed','cancelled'].includes(job.status)&&<button onClick={()=>action(job,'retry')}>Thử lại</button>}</div></article>)}</div></aside></div>
  </section>
}
