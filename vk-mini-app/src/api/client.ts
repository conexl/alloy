import axios from 'axios'
import type { RFQ, Item, Quote, Supplier, ThreadMessage } from '../types'

// URL API бэкенда
const API_BASE = (import.meta as any).env?.VITE_API_URL || 
  (window.location.hostname === 'localhost' ? 'http://localhost:8002' : `http://${window.location.hostname}:8002`)

const client = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Добавляем vk_id и launch params в каждый запрос
client.interceptors.request.use((config) => {
  const vkParams = localStorage.getItem('vk_params')
  if (vkParams) {
    config.headers['X-VK-Launch-Params'] = vkParams
  }
  const vkId = localStorage.getItem('vk_user_id')
  if (vkId) {
    config.headers['X-VK-User-ID'] = vkId
  }
  return config
})

export const api = {
  // RFQ
  getRFQs: () => client.get<RFQ[]>('/api/rfqs'),
  getRFQ: (id: number) => client.get<RFQ>(`/api/rfqs/${id}`),
  
  // Items
  getItems: (rfqId: number) => client.get<Item[]>(`/api/rfqs/${rfqId}/items`),
  getItem: (id: number) => client.get<Item>(`/api/items/${id}`),
  
  // Quotes
  getQuotes: (itemId: number) => client.get<Quote[]>(`/api/items/${itemId}/quotes`),
  selectWinner: (itemId: number, quoteId: number, marginPct: number = 0) => 
    client.post(`/api/items/${itemId}/winner`, { quote_id: quoteId, margin_pct: marginPct }),
  
  // Suppliers
  getSuppliers: (itemId: number) => client.get<Supplier[]>(`/api/items/${itemId}/suppliers`),
  
  // Threads
  getThreads: (itemId: number) => client.get<ThreadMessage[]>(`/api/items/${itemId}/threads`),
  
  // User
  getProfile: () => client.get('/api/profile'),
  updateProfile: (data: any) => client.patch('/api/profile', data),
  
  // Create RFQ
  createRFQ: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post<{ rfq_id: number; items_count: number; message: string }>('/api/rfqs', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  },
  
  // Report
  getReport: (rfqId: number) => client.get(`/api/reports/${rfqId}/status`),
  downloadReport: (rfqId: number) => window.open(`${API_BASE}/api/reports/${rfqId}/file`),
  
  // SSE с reconnect
  subscribeSSE: (onMessage: (data: any) => void, onError?: (error: any) => void) => {
    const vkId = localStorage.getItem('vk_user_id')
    
    if (!vkId) {
      console.warn('SSE: vk_user_id не найден, пропускаем подписку')
      onError?.(new Error('Не авторизован'))
      return () => {}
    }
    
    let es: EventSource | null = null
    let reconnectAttempts = 0
    const maxReconnectAttempts = 5
    let reconnectTimeout: ReturnType<typeof setTimeout>
    
    const connect = () => {
      if (es) {
        es.close()
      }
      
      const url = new URL(`${API_BASE}/api/sse/subscribe`)
      url.searchParams.set('vk_user_id', vkId)
      
      es = new EventSource(url.toString())
      
      es.onopen = () => {
        console.log('SSE: Соединение установлено')
        reconnectAttempts = 0
      }
      
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'ping') return
          if (data.type === 'connected') {
            console.log('SSE: Подключено к серверу')
            return
          }
          onMessage(data)
        } catch (e) {
          console.error('SSE parse error:', e)
        }
      }
      
      es.onerror = (error) => {
        console.error('SSE error:', error)
        
        if (es?.readyState === EventSource.CLOSED) {
          reconnectAttempts++
          
          if (reconnectAttempts > maxReconnectAttempts) {
            console.error('SSE: Превышено количество попыток reconnect')
            onError?.(new Error('Не удалось подключиться к серверу'))
            return
          }
          
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)
          console.log(`SSE: Переподключение через ${delay}ms (попытка ${reconnectAttempts})`)
          
          reconnectTimeout = setTimeout(connect, delay)
        }
      }
    }
    
    connect()
    
    return () => {
      clearTimeout(reconnectTimeout)
      if (es) {
        es.close()
        es = null
      }
    }
  },
}

export default client
