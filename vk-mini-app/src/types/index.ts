export interface RFQ {
  id: number
  city: string | null
  total_budget: string | null
  created_at: string
  updated_at: string
  items_count: number
  quotes_count: number
  status: string
}

export interface Item {
  id: number
  rfq_id: number
  name: string
  tech_code: string | null
  gost: string | null
  unit: string | null
  qty: number
  deadline: string | null
  location: string | null
  material: string | null
  suppliers_count: number
  quotes_count: number
  winner?: Winner
}

export interface Supplier {
  id: number
  name: string | null
  domain: string
  email: string
  is_valid: boolean
  status: 'pending' | 'sent' | 'replied' | 'unavailable'
}

export interface Quote {
  id: number
  supplier_id: number
  supplier_name: string | null
  supplier_email: string
  price: number
  delivery_days: number | null
  pickup_address: string | null
  source: string
  received_at: string
}

export interface Winner {
  id: number
  quote_id: number
  final_price: number
  margin_pct: number
  chosen_at: string
}

export interface ThreadMessage {
  id: number
  direction: 'inbound' | 'outbound'
  body: string
  created_at: string
}

export interface User {
  vk_id: number
  first_name: string
  last_name: string
  photo_200?: string
}
