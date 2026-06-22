export const formatBytes = (size?: number) => {
  if (!size) return '0 KB'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export const formatTime = (timestamp?: number) => {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export const getFileTag = (name: string) => {
  const suffix = name.split('.').pop()?.toUpperCase()
  return suffix ? suffix.slice(0, 4) : 'FILE'
}

export const normalizeTitle = (title: string) => {
  return title
    .replace('姝ｅ湪浣跨敤鍔╂墜锛?', '正在使用助手：')
    .replace('浣跨敤鐨勫伐鍏凤細', '使用工具：')
}
