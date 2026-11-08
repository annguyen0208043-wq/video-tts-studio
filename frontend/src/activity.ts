import { useSyncExternalStore } from 'react'

export type Activity = { id: number; label: string; status: 'pending' | 'success' | 'error'; detail: string }
let sequence = 0
let activities: Activity[] = []
const listeners = new Set<() => void>()
const notify = () => listeners.forEach(listener => listener())
export function beginActivity(label: string) {
  const id = ++sequence
  activities = [...activities.filter(item => item.status === 'pending'), ...activities.filter(item => item.status === 'error').slice(-5),
    { id, label, status: 'pending', detail: 'Đang gửi và tiếp nhận. Bạn có thể tiếp tục thao tác.' }]
  notify()
  return id
}
export function finishActivity(id: number, status: 'success' | 'error', detail: string) {
  activities = activities.map(item => item.id === id ? { ...item, status, detail } : item)
  notify()
  if (status === 'success') window.setTimeout(() => dismissActivity(id), 7000)
}
export function dismissActivity(id: number) {
  activities = activities.filter(item => item.id !== id || item.status === 'pending')
  notify()
}
export function useActivities() {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener) } }, () => activities)
}
