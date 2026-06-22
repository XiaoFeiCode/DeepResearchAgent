export type AgentStatus = 'idle' | 'running'
export type DrawerMode = 'files' | 'knowledge'

export interface LogItem {
  type: string
  title: string
  details: unknown
  timestamp: string
}

export interface FileItem {
  name: string
  path: string
  url: string
  size?: number
  mtime?: number
}

export interface Message {
  role: 'user' | 'ai' | 'system'
  content: string
  logs?: LogItem[]
  files?: FileItem[]
  timestamp?: number
}

export interface RagflowDataset {
  id: string
  name: string
  description?: string
  doc_num?: number
  chunk_num?: number
  language?: string
  parser_id?: string
}

export interface RagflowDocument {
  id: string
  name: string
  run?: string | number | null
  progress?: number | string | null
  chunk_count?: number | null
  token_count?: number | null
  create_date?: string
  update_date?: string
}
