import { useState, useRef } from 'react'
import { X, Upload, FileSpreadsheet, CheckCircle, ArrowRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../api/client'
import { useNavigate } from 'react-router-dom'

interface CreateRFQPanelProps {
  onClose: () => void
}

export default function CreateRFQPanel({ onClose }: CreateRFQPanelProps) {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState<{ rfqId: number; itemsCount: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (!selected) return
    
    if (!selected.name.endsWith('.xlsx')) {
      setError('Только файлы .xlsx')
      return
    }
    
    setFile(selected)
    setError(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped && dropped.name.endsWith('.xlsx')) {
      setFile(dropped)
      setError(null)
    } else {
      setError('Только файлы .xlsx')
    }
  }

  const handleSubmit = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    
    try {
      const res = await api.createRFQ(file)
      setSuccess({ rfqId: res.data.rfq_id, itemsCount: res.data.items_count })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось создать заявку')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 dialog-overlay"
      />

      {/* Panel */}
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', stiffness: 400, damping: 35 }}
        className="relative w-full max-w-xl bg-card border border-border rounded-t-2xl shadow-2xl max-h-[90vh] overflow-y-auto"
      >
        {/* Handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-12 h-1.5 rounded-full bg-muted-foreground/30" />
        </div>

        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-foreground">Создать заявку</h2>
            <button 
              onClick={onClose}
              className="p-2 hover:bg-muted rounded-lg transition-colors"
            >
              <X size={20} className="text-muted-foreground" />
            </button>
          </div>

          <AnimatePresence mode="wait">
            {success ? (
              <motion.div
                key="success"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="text-center py-8"
              >
                <motion.div 
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                  className="w-20 h-20 rounded-2xl bg-success/20 flex items-center justify-center mx-auto mb-4"
                >
                  <CheckCircle size={40} className="text-success" />
                </motion.div>
                <h3 className="text-2xl font-bold text-foreground mb-2">Заявка создана!</h3>
                <p className="text-muted-foreground mb-6">
                  #{success.rfqId} с {success.itemsCount} позициями
                </p>
                <div className="flex gap-3 justify-center">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => {
                      onClose()
                      navigate(`/rfqs/${success.rfqId}`)
                    }}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-accent text-accent-foreground font-semibold"
                  >
                    Перейти
                    <ArrowRight size={16} />
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => {
                      setSuccess(null)
                      setFile(null)
                    }}
                    className="px-6 py-2.5 rounded-xl bg-muted text-foreground font-semibold"
                  >
                    Создать ещё
                  </motion.button>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="form"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-6"
              >
                {/* Requirements */}
                <div className="bg-accent/10 border border-accent/20 rounded-xl p-4">
                  <div className="flex items-start gap-3">
                    <Upload size={18} className="text-accent mt-0.5 shrink-0" />
                    <div>
                      <p className="text-sm text-accent font-medium">Требования к файлу</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Excel (.xlsx) с колонками: Наименование, Количество, 
                        Единица, Срок, Город
                      </p>
                    </div>
                  </div>
                </div>

                <input
                  type="file"
                  accept=".xlsx"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  className="hidden"
                />

                {/* Drop Zone */}
                {!file ? (
                  <motion.div
                    animate={{ 
                      borderColor: isDragOver ? 'var(--accent)' : 'var(--border)',
                      backgroundColor: isDragOver ? 'rgba(245, 158, 11, 0.05)' : 'transparent'
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    onDrop={handleDrop}
                    onDragOver={(e) => { e.preventDefault(); setIsDragOver(true) }}
                    onDragLeave={() => setIsDragOver(false)}
                    className="border-2 border-dashed border-border rounded-2xl p-12 text-center cursor-pointer transition-colors"
                  >
                    <motion.div 
                      animate={{ y: isDragOver ? -4 : 0 }}
                      className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-4"
                    >
                      <Upload size={32} className="text-accent" />
                    </motion.div>
                    <p className="text-foreground font-medium text-lg">Нажмите или перетащите файл</p>
                    <p className="text-sm text-muted-foreground mt-2">.xlsx до 10 МБ</p>
                  </motion.div>
                ) : (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="flex items-center justify-between p-5 bg-muted rounded-xl border border-border"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-xl bg-success/20 flex items-center justify-center">
                        <FileSpreadsheet size={24} className="text-success" />
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{file.name}</p>
                        <p className="text-sm text-muted-foreground">{(file.size / 1024).toFixed(1)} КБ</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setFile(null)}
                      className="p-2 hover:bg-background rounded-lg transition-colors"
                    >
                      <X size={20} className="text-muted-foreground" />
                    </button>
                  </motion.div>
                )}

                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="bg-danger/10 border border-danger/20 rounded-xl p-4 text-sm text-danger"
                  >
                    {error}
                  </motion.div>
                )}

                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleSubmit}
                  disabled={!file || loading}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-accent text-accent-foreground font-semibold hover:bg-accent/90 transition-colors disabled:opacity-50"
                >
                  {loading ? (
                    <div className="w-5 h-5 border-2 border-accent-foreground/30 border-t-accent-foreground rounded-full animate-spin" />
                  ) : (
                    <>
                      <Upload size={18} />
                      Создать заявку
                    </>
                  )}
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}
