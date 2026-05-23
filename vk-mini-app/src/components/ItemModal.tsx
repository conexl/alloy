import { useState, useEffect } from 'react'
import { X, Building2, MapPin, Package, TrendingUp, CheckCircle, ChevronDown, ChevronUp, MessageSquare } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../api/client'
import type { Item, Quote, Supplier, ThreadMessage } from '../types'

interface ItemModalProps {
  item: Item
  onClose: () => void
}

export default function ItemModal({ item: initialItem, onClose }: ItemModalProps) {
  const [item, setItem] = useState<Item>(initialItem)
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [, setSuppliers] = useState<Supplier[]>([])
  const [threads, setThreads] = useState<ThreadMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [showSupplierChange, setShowSupplierChange] = useState(false)
  const [selectingQuote, setSelectingQuote] = useState<number | null>(null)
  const [activeSection, setActiveSection] = useState<'supplier' | 'threads'>('supplier')

  useEffect(() => {
    loadData()
    // Блокируем скролл body при открытии модалки
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [initialItem.id])

  async function loadData() {
    try {
      const [itemRes, quotesRes, suppliersRes, threadsRes] = await Promise.all([
        api.getItem(initialItem.id),
        api.getQuotes(initialItem.id),
        api.getSuppliers(initialItem.id),
        api.getThreads(initialItem.id),
      ])
      setItem(itemRes.data)
      setQuotes(quotesRes.data)
      setSuppliers(suppliersRes.data)
      setThreads(threadsRes.data)
    } catch (err) {
      console.error('Failed to load item details:', err)
    } finally {
      setLoading(false)
    }
  }

  async function handleSelectWinner(quoteId: number) {
    try {
      await api.selectWinner(initialItem.id, quoteId)
      await loadData()
      setShowSupplierChange(false)
      setSelectingQuote(null)
    } catch (err) {
      console.error('Failed to select winner:', err)
    }
  }

  const currentWinner = quotes.find(q => q.id === item.winner?.quote_id)
  const otherQuotes = quotes.filter(q => q.id !== item.winner?.quote_id)

  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-40 dialog-overlay"
        style={{ pointerEvents: 'auto' }}
      />

      {/* Modal Container - centered on viewport */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          className="relative w-full max-w-2xl bg-card rounded-2xl shadow-2xl max-h-[85vh] overflow-hidden flex flex-col pointer-events-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-border shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-muted flex items-center justify-center">
                <Package size={20} className="text-accent" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground">{item.name}</h2>
                <p className="text-sm text-muted-foreground">{item.qty} {item.unit || 'шт'}{item.deadline && ` · до ${new Date(item.deadline).toLocaleDateString('ru-RU')}`}</p>
              </div>
            </div>
            <button 
              onClick={onClose}
              className="p-2 hover:bg-muted rounded-lg transition-colors"
            >
              <X size={20} className="text-muted-foreground" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  className="w-8 h-8 rounded-lg bg-accent"
                />
              </div>
            ) : (
              <>
                {/* Item Details — без рамок */}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-muted/50 rounded-xl p-4 space-y-3"
                >
                  <p className="text-sm font-medium text-muted-foreground mb-2">Информация из заявки</p>
                  <div className="grid grid-cols-2 gap-3">
                    {item.tech_code && (
                      <div className="flex items-center gap-2 text-sm">
                        <TagIcon className="text-muted-foreground" />
                        <span className="text-foreground">{item.tech_code}</span>
                      </div>
                    )}
                    {item.gost && (
                      <div className="flex items-center gap-2 text-sm">
                        <TagIcon className="text-muted-foreground" />
                        <span className="text-foreground">{item.gost}</span>
                      </div>
                    )}
                    {item.material && (
                      <div className="flex items-center gap-2 text-sm">
                        <TagIcon className="text-muted-foreground" />
                        <span className="text-foreground">{item.material}</span>
                      </div>
                    )}
                    {item.location && (
                      <div className="flex items-center gap-2 text-sm">
                        <MapPin size={14} className="text-muted-foreground" />
                        <span className="text-foreground">{item.location}</span>
                      </div>
                    )}
                  </div>
                </motion.div>

                {/* Current Supplier — без рамок */}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="bg-muted/50 rounded-xl p-4"
                >
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-medium text-muted-foreground">Текущий поставщик</p>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => setShowSupplierChange(!showSupplierChange)}
                      className="text-sm text-accent hover:text-accent/80 transition-colors flex items-center gap-1"
                    >
                      Сменить
                      {showSupplierChange ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </motion.button>
                  </div>

                  {currentWinner ? (
                    <div className="flex items-center justify-between p-3 bg-success/10 rounded-xl">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-success/20 flex items-center justify-center">
                          <Building2 size={18} className="text-success" />
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{currentWinner.supplier_name || currentWinner.supplier_email}</p>
                          <div className="flex items-center gap-3 text-sm text-muted-foreground">
                            <span className="text-success font-medium">{currentWinner.price.toLocaleString('ru-RU')} ₽</span>
                            {currentWinner.delivery_days && (
                              <span>{currentWinner.delivery_days} дн.</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <CheckCircle size={20} className="text-success" />
                    </div>
                  ) : (
                    <div className="text-center py-4 text-muted-foreground text-sm">
                      Поставщик не выбран
                    </div>
                  )}

                  {/* Change Supplier */}
                  <AnimatePresence>
                    {showSupplierChange && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="overflow-hidden"
                      >
                        <div className="mt-4 space-y-3">
                          <p className="text-sm font-medium text-muted-foreground">Выберите поставщика</p>
                          
                          {otherQuotes.length > 0 ? (
                            otherQuotes.map((quote) => (
                              <motion.div
                                key={quote.id}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                className="flex items-center justify-between p-3 bg-card rounded-xl hover:bg-muted/70 transition-colors"
                              >
                                <div className="flex items-center gap-3">
                                  <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center">
                                    <TrendingUp size={16} className="text-accent" />
                                  </div>
                                  <div>
                                    <p className="text-sm font-medium text-foreground">{quote.supplier_name || quote.supplier_email}</p>
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                      <span className="font-medium text-accent">{quote.price.toLocaleString('ru-RU')} ₽</span>
                                      {quote.delivery_days && <span>{quote.delivery_days} дн.</span>}
                                    </div>
                                  </div>
                                </div>
                                
                                <motion.button
                                  whileHover={{ scale: 1.05 }}
                                  whileTap={{ scale: 0.95 }}
                                  onClick={() => handleSelectWinner(quote.id)}
                                  disabled={selectingQuote === quote.id}
                                  className="px-3 py-1.5 rounded-lg bg-accent text-accent-foreground text-sm font-medium hover:bg-accent/90 transition-colors disabled:opacity-50"
                                >
                                  {selectingQuote === quote.id ? (
                                    <div className="w-4 h-4 border-2 border-accent-foreground/30 border-t-accent-foreground rounded-full animate-spin" />
                                  ) : (
                                    'Выбрать'
                                  )}
                                </motion.button>
                              </motion.div>
                            ))
                          ) : (
                            <p className="text-sm text-muted-foreground text-center py-2">Нет других котировок</p>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>

                {/* Threads — без рамок */}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="bg-muted/50 rounded-xl overflow-hidden"
                >
                  <button
                    onClick={() => setActiveSection(activeSection === 'threads' ? 'supplier' : 'threads')}
                    className="w-full flex items-center justify-between p-4 text-left"
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquare size={16} className="text-muted-foreground" />
                      <span className="font-medium text-foreground">Переписка</span>
                      <span className="text-xs text-muted-foreground">({threads.length})</span>
                    </div>
                    {activeSection === 'threads' ? <ChevronUp size={16} className="text-muted-foreground" /> : <ChevronDown size={16} className="text-muted-foreground" />}
                  </button>

                  <AnimatePresence>
                    {activeSection === 'threads' && (
                      <motion.div
                        initial={{ height: 0 }}
                        animate={{ height: 'auto' }}
                        exit={{ height: 0 }}
                        transition={{ duration: 0.3 }}
                        className="overflow-hidden"
                      >
                        <div className="px-4 pb-4 space-y-3 max-h-64 overflow-y-auto">
                          {threads.length > 0 ? (
                            threads.map((thread, i) => (
                              <motion.div
                                key={thread.id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: i * 0.05 }}
                                className={`p-3 rounded-xl text-sm ${
                                  thread.direction === 'inbound'
                                    ? 'bg-card'
                                    : 'bg-accent/10 ml-8'
                                }`}
                              >
                                <div className="flex items-center justify-between mb-1">
                                  <span className={`text-xs font-medium ${
                                    thread.direction === 'inbound' ? 'text-muted-foreground' : 'text-accent'
                                  }`}>
                                    {thread.direction === 'inbound' ? '📥 Входящее' : '📤 Исходящее'}
                                  </span>
                                  <span className="text-xs text-muted-foreground">
                                    {new Date(thread.created_at).toLocaleString('ru-RU')}
                                  </span>
                                </div>
                                <p className="text-foreground whitespace-pre-wrap">{thread.body.substring(0, 300)}{thread.body.length > 300 && '...'}</p>
                              </motion.div>
                            ))
                          ) : (
                            <p className="text-sm text-muted-foreground text-center py-4">Пока нет сообщений</p>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              </>
            )}
          </div>
        </motion.div>
      </div>
    </>
  )
}

function TagIcon({ className }: { className?: string }) {
  return (
    <svg 
      width="14" 
      height="14" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
      className={className}
    >
      <path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z" />
      <circle cx="7" cy="7" r="1" />
    </svg>
  )
}
