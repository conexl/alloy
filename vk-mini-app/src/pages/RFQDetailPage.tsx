import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Package, TrendingUp, CheckCircle2, Circle } from 'lucide-react'
import { api } from '../api/client'
import type { Item, RFQ } from '../types'
import ItemModal from '../components/ItemModal'

export default function RFQDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [rfq, setRFQ] = useState<RFQ | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedItem, setSelectedItem] = useState<Item | null>(null)

  useEffect(() => {
    if (id) loadData()
  }, [id])

  async function loadData() {
    try {
      const [rfqRes, itemsRes] = await Promise.all([
        api.getRFQ(parseInt(id!)),
        api.getItems(parseInt(id!)),
      ])
      setRFQ(rfqRes.data)
      setItems(itemsRes.data)
    } catch (err) {
      console.error('Failed to load RFQ:', err)
    } finally {
      setLoading(false)
    }
  }

  const progress = items.length > 0 
    ? Math.round((items.filter(i => i.quotes_count > 0).length / items.length) * 100)
    : 0

  const getStatusInfo = (item: Item) => {
    if (item.winner) {
      return { icon: <CheckCircle2 size={16} className="text-success" />, text: 'Выбран', color: 'text-success', bg: 'bg-success/10' }
    }
    if (item.quotes_count > 0) {
      return { icon: <TrendingUp size={16} className="text-accent" />, text: `${item.quotes_count} котир.`, color: 'text-accent', bg: 'bg-accent/10' }
    }
    return { icon: <Circle size={16} className="text-muted-foreground" />, text: 'Ожидание', color: 'text-muted-foreground', bg: 'bg-muted' }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="w-10 h-10 rounded-xl bg-accent"
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex items-center gap-4"
      >
        <motion.button
          whileHover={{ x: -4 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft size={20} />
          <span className="hidden sm:inline">Назад</span>
        </motion.button>

        <div>
          <h1 className="text-3xl font-bold text-foreground">Заявка #{id}</h1>
          <p className="text-muted-foreground">{rfq?.city || 'Без города'} · {rfq?.created_at && new Date(rfq.created_at).toLocaleDateString('ru-RU')}</p>
        </div>
      </motion.div>

      {/* Progress */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-card rounded-2xl p-6"
      >
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-muted-foreground">Прогресс</span>
          <span className="text-2xl font-bold text-accent">{progress}%</span>
        </div>
        <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.7, ease: 'easeOut' }}
            className="h-full rounded-full bg-accent"
          />
        </div>
        <p className="text-sm text-muted-foreground mt-3">
          {items.filter(i => i.quotes_count > 0).length} из {items.length} позиций с котировками
        </p>
      </motion.div>

      {/* Items Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-foreground">Позиции ({items.length})</h2>
        </div>

        <div className="bg-card rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr className="text-left">
                  <th className="px-6 py-4 text-sm font-medium text-muted-foreground">Название</th>
                  <th className="px-6 py-4 text-sm font-medium text-muted-foreground">Кол-во</th>
                  <th className="px-6 py-4 text-sm font-medium text-muted-foreground">Срок</th>
                  <th className="px-6 py-4 text-sm font-medium text-muted-foreground">Котировок</th>
                  <th className="px-6 py-4 text-sm font-medium text-muted-foreground">Статус</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((item, index) => {
                  const status = getStatusInfo(item)
                  
                  return (
                    <motion.tr
                      key={item.id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.03 }}
                      onClick={() => setSelectedItem(item)}
                      className="hover:bg-muted/50 cursor-pointer transition-colors"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
                            <Package size={16} className="text-muted-foreground" />
                          </div>
                          <span className="font-medium text-foreground">{item.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {item.qty} {item.unit || 'шт'}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {item.deadline ? new Date(item.deadline).toLocaleDateString('ru-RU') : '—'}
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-sm font-medium text-foreground">{item.quotes_count}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${status.bg} ${status.color}`}>
                          {status.icon}
                          {status.text}
                        </span>
                      </td>
                    </motion.tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </motion.div>

      {/* Item Modal */}
      <AnimatePresence>
        {selectedItem && (
          <ItemModal 
            item={selectedItem} 
            onClose={() => setSelectedItem(null)} 
          />
        )}
      </AnimatePresence>
    </div>
  )
}
