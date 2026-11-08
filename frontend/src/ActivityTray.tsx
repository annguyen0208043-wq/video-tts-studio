import { CheckCircle2, LoaderCircle, X, XCircle } from 'lucide-react'
import { dismissActivity, useActivities } from './activity'

export function ActivityTray() {
  const activities = useActivities()
  return <aside className="activity-tray" aria-label="Trạng thái thao tác" aria-live="polite" aria-relevant="additions text">
    {activities.map(item => <div key={item.id} className={`activity-item ${item.status}`} role={item.status === 'error' ? 'alert' : 'status'}>
      {item.status === 'pending' ? <LoaderCircle size={18} className="spin" /> : item.status === 'error' ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
      <div><strong>{item.label}</strong><small>{item.detail}</small></div>
      {item.status !== 'pending' && <button type="button" aria-label="Đóng thông báo" onClick={() => dismissActivity(item.id)}><X size={15} /></button>}
    </div>)}
  </aside>
}
