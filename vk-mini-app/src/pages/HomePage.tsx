import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FileText, TrendingUp, Clock, ArrowRight } from 'lucide-react'
import { api } from '../api/client'
import type { RFQ } from '../types'

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 }
  }
}

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 30 } }
}

export default function HomePage() {
  const navigate = useNavigate()
  const [rfqs, setRFQs] = useState<RFQ[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadRFQs()
  }, [])

  async function loadRFQs() {
    try {
      const res = await api.getRFQs()
      setRFQs(res.data)
    } catch (err) {
      console.error('Failed to load RFQs:', err)
    } finally {
      setLoading(false)
    }
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
    <div className="space-y-8">
      {/* Stats */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold text-foreground">Заявки</h1>
          <p className="text-muted-foreground mt-1">{rfqs.length} заявок всего</p>
        </div>
        <div className="flex gap-6">
          <div className="text-right">
            <p className="text-2xl font-bold text-foreground">{rfqs.filter(r => r.status === 'active').length}</p>
            <p className="text-sm text-muted-foreground">Активных</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-foreground">{rfqs.filter(r => r.status === 'completed').length}</p>
            <p className="text-sm text-muted-foreground">Завершено</p>
          </div>
        </div>
      </motion.div>

      {/* Grid */}
      {rfqs.length > 0 ? (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          {rfqs.map((rfq) => {
            const progress = rfq.items_count > 0 
              ? Math.round((rfq.quotes_count / rfq.items_count) * 100)
              : 0

            return (
              <motion.div
                key={rfq.id}
                variants={item}
                whileHover={{ y: -4, transition: { duration: 0.2 } }}
                onClick={() => navigate(`/rfqs/${rfq.id}`)}
                className="group bg-card border border-border hover:border-accent/30 rounded-2xl p-6 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-muted flex items-center justify-center group-hover:bg-accent/10 transition-colors">
                      <FileText size={20} className="text-muted-foreground group-hover:text-accent transition-colors" />
                    </div>
                    <div>
                      <p className="font-semibold text-foreground group-hover:text-accent transition-colors">
                        Заявка #{rfq.id}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {new Date(rfq.created_at).toLocaleDateString('ru-RU')}
                      </p>
                    </div>
                  </div>
                  <ArrowRight 
                    size={18} 
                    className="text-muted-foreground group-hover:text-accent group-hover:translate-x-1 transition-all" 
                  />
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm">
                    <Clock size={14} className="text-muted-foreground" />
                    <span className="text-muted-foreground">{rfq.city || 'Без города'}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{rfq.items_count} позиций</span>
                    <span className="text-sm font-medium text-foreground">{rfq.quotes_count} котировок</span>
                  </div>

                  {/* Progress */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Прогресс</span>
                      <span className="font-medium text-accent">{progress}%</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.7, ease: 'easeOut' }}
                        className="h-full rounded-full bg-accent"
                      />
                    </div>
                  </div>

                  {/* Status */}
                  <div className="flex justify-end">
                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${
                      rfq.status === 'completed'
                        ? 'bg-success/10 text-success'
                        : 'bg-accent/10 text-accent'
                    }`}>
                      {rfq.status === 'completed' ? 'Завершена' : 'Активна'}
                    </span>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-20"
        >
          <div className="w-20 h-20 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-6">
            <TrendingUp size={40} className="text-muted-foreground" />
          </div>
          <p className="text-xl font-semibold text-foreground mb-2">У вас пока нет заявок</p>
          <p className="text-muted-foreground">Создайте первую заявку нажав на кнопку выше</p>
        </motion.div>
      )}
    </div>
  )
}
