import { useState, useEffect } from 'react'
import { X, Save, Sun, Moon, CheckCircle, Building2, MapPin, Phone, Mail, User as UserIcon } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTheme } from '../hooks/useTheme'
import { api } from '../api/client'
import type { User } from '../types'

interface ProfileModalProps {
  user: User | null
  onClose: () => void
}

export default function ProfileModal({ user, onClose }: ProfileModalProps) {
  const { theme, toggleTheme } = useTheme()
  const [activeTab, setActiveTab] = useState<'profile' | 'company' | 'settings'>('company')
  const [form, setForm] = useState({
    company_name: '',
    inn: '',
    kpp: '',
    address: '',
    phone: '',
    email: '',
    contact_person: '',
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadProfile()
  }, [])

  async function loadProfile() {
    try {
      const res = await api.getProfile()
      if (res.data) {
        setForm({
          company_name: res.data.company_name || '',
          inn: res.data.inn || '',
          kpp: res.data.kpp || '',
          address: res.data.address || '',
          phone: res.data.phone || '',
          email: res.data.email || '',
          contact_person: res.data.contact_person || '',
        })
      }
    } catch (err) {
      console.error('Failed to load profile:', err)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await api.updateProfile(form)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const tabs = [
    { id: 'company' as const, label: 'Компания', icon: <Building2 size={16} /> },
    { id: 'settings' as const, label: 'Настройки', icon: <Sun size={16} /> },
  ]

  const fields = [
    { key: 'company_name' as const, label: 'Название', icon: <Building2 size={16} />, placeholder: 'ООО «Alloy»' },
    { key: 'inn' as const, label: 'ИНН', icon: <UserIcon size={16} />, placeholder: '7701234567', maxLength: 12 },
    { key: 'kpp' as const, label: 'КПП', icon: <UserIcon size={16} />, placeholder: '770101001', maxLength: 9 },
    { key: 'address' as const, label: 'Адрес', icon: <MapPin size={16} />, placeholder: 'г. Москва' },
    { key: 'phone' as const, label: 'Телефон', icon: <Phone size={16} />, placeholder: '+7 (999) 123-45-67', type: 'tel' },
    { key: 'email' as const, label: 'Email', icon: <Mail size={16} />, placeholder: 'info@alloy.ru', type: 'email' },
    { key: 'contact_person' as const, label: 'Контактное лицо', icon: <UserIcon size={16} />, placeholder: 'Иванов И.И.' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 dialog-overlay"
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 30, scale: 0.95 }}
        transition={{ type: 'spring', stiffness: 400, damping: 30 }}
        className="relative w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border">
          <h2 className="text-xl font-bold text-foreground">Профиль</h2>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-muted rounded-lg transition-colors"
          >
            <X size={20} className="text-muted-foreground" />
          </button>
        </div>

        {/* VK Info */}
        <div className="p-6 border-b border-border">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-muted border border-border overflow-hidden flex items-center justify-center">
              {user?.photo_200 ? (
                <img src={user.photo_200} alt="" className="w-full h-full object-cover" />
              ) : (
                <UserIcon size={32} className="text-muted-foreground" />
              )}
            </div>
            <div>
              <p className="font-semibold text-foreground">
                {user?.first_name} {user?.last_name}
              </p>
              <p className="text-sm text-muted-foreground">VK ID: {user?.vk_id}</p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-accent text-accent'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6 max-h-[60vh] overflow-y-auto">
          <AnimatePresence mode="wait">
            {activeTab === 'company' && (
              <motion.div
                key="company"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-4"
              >
                {fields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-sm font-medium text-muted-foreground mb-1.5">
                      <div className="flex items-center gap-2">
                        {field.icon}
                        {field.label}
                      </div>
                    </label>
                    <input
                      type={field.type || 'text'}
                      value={form[field.key]}
                      onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                      placeholder={field.placeholder}
                      maxLength={field.maxLength}
                      className="w-full px-4 py-2.5 rounded-xl bg-muted border border-border text-foreground placeholder:text-muted-foreground focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                    />
                  </div>
                ))}

                <div className="flex items-center gap-3 pt-2">
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={handleSave}
                    disabled={saving}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-accent text-accent-foreground font-semibold hover:bg-accent/90 transition-colors disabled:opacity-50"
                  >
                    {saving ? (
                      <div className="w-5 h-5 border-2 border-accent-foreground/30 border-t-accent-foreground rounded-full animate-spin" />
                    ) : (
                      <>
                        <Save size={16} />
                        Сохранить
                      </>
                    )}
                  </motion.button>
                  
                  {saved && (
                    <motion.div
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="flex items-center gap-2 text-success"
                    >
                      <CheckCircle size={18} />
                      <span className="text-sm font-medium">Сохранено</span>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            )}

            {activeTab === 'settings' && (
              <motion.div
                key="settings"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-6"
              >
                <div className="flex items-center justify-between p-4 rounded-xl bg-muted border border-border">
                  <div className="flex items-center gap-3">
                    {theme === 'dark' ? (
                      <Moon size={20} className="text-accent" />
                    ) : (
                      <Sun size={20} className="text-accent" />
                    )}
                    <div>
                      <p className="font-medium text-foreground">Тема</p>
                      <p className="text-sm text-muted-foreground">{theme === 'dark' ? 'Тёмная' : 'Светлая'}</p>
                    </div>
                  </div>
                  
                  <motion.button
                    whileTap={{ scale: 0.95 }}
                    onClick={toggleTheme}
                    className="relative w-14 h-8 rounded-full bg-muted-foreground/20 transition-colors"
                  >
                    <motion.div
                      animate={{ x: theme === 'dark' ? 24 : 4 }}
                      transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                      className="absolute top-1 w-6 h-6 rounded-full bg-accent shadow-lg"
                    />
                  </motion.button>
                </div>

                <div className="p-4 rounded-xl bg-muted border border-border">
                  <p className="text-sm text-muted-foreground">Версия приложения</p>
                  <p className="font-semibold text-foreground">1.2.0</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}
