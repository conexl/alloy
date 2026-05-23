import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { useVK } from './hooks/useVK'
import { ThemeProvider } from './hooks/useTheme'
import { AnimatePresence, motion } from 'framer-motion'
import { useState, useEffect } from 'react'
import { api } from './api/client'
import Header from './components/Header'
import HomePage from './pages/HomePage'
import RFQDetailPage from './pages/RFQDetailPage'
import { PageTransition } from './animations'

function AppContent() {
  const location = useLocation()
  const { user, isLoading, error } = useVK()
  const [newQuoteAlert, setNewQuoteAlert] = useState<any>(null)

  useEffect(() => {
    if (!user?.vk_id) return
    
    const unsubscribe = api.subscribeSSE(
      (data) => {
        if (data.type === 'quote_received') {
          setNewQuoteAlert(data)
          setTimeout(() => setNewQuoteAlert(null), 5000)
        }
      },
      (error) => console.warn('SSE:', error.message)
    )
    
    return () => unsubscribe()
  }, [user?.vk_id])

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <motion.div 
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 20 }}
          className="text-center"
        >
          <motion.div 
            animate={{ rotate: 360 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
            className="w-16 h-16 rounded-2xl bg-accent flex items-center justify-center mx-auto mb-4"
          >
            <span className="text-accent-foreground font-bold text-2xl">A</span>
          </motion.div>
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: 200 }}
            transition={{ duration: 1.5, repeat: Infinity, repeatType: 'reverse' }}
            className="h-1 bg-accent rounded-full mx-auto"
          />
        </motion.div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center max-w-md px-4"
        >
          <motion.div 
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.2 }}
            className="w-20 h-20 rounded-2xl bg-danger flex items-center justify-center mx-auto mb-6"
          >
            <span className="text-white font-bold text-3xl">!</span>
          </motion.div>
          <h2 className="text-2xl font-bold text-foreground mb-3">Ошибка</h2>
          <p className="text-muted-foreground mb-6">{error}</p>
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="bg-card border border-border rounded-xl p-4 text-left"
          >
            <p className="text-sm text-muted-foreground mb-2">Для тестирования:</p>
            <code className="text-sm text-accent bg-background px-3 py-2 rounded-lg block">
              http://localhost:3000?vk_user_id=1061591442
            </code>
          </motion.div>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header 
        user={user} 
        onQuoteAlert={(alert) => {
          setNewQuoteAlert(alert)
          setTimeout(() => setNewQuoteAlert(null), 5000)
        }}
      />
      
      {/* Уведомление о новой котировке */}
      <AnimatePresence>
        {newQuoteAlert && (
          <motion.div
            initial={{ opacity: 0, y: -50, x: '-50%', scale: 0.9 }}
            animate={{ opacity: 1, y: 0, x: '-50%', scale: 1 }}
            exit={{ opacity: 0, y: -50, x: '-50%', scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className="fixed top-4 left-1/2 z-50 bg-card border border-success/30 text-success px-6 py-4 rounded-2xl shadow-2xl max-w-md w-full"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <motion.div 
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 500, delay: 0.1 }}
                  className="w-10 h-10 rounded-xl bg-success/20 flex items-center justify-center"
                >
                  <span className="text-xl">🎉</span>
                </motion.div>
                <div>
                  <p className="font-semibold text-foreground">Новая котировка!</p>
                  <p className="text-sm text-success/80">Цена {newQuoteAlert.price}₽ по позиции #{newQuoteAlert.item_id}</p>
                </div>
              </div>
              <button 
                onClick={() => setNewQuoteAlert(null)}
                className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground"
              >
                ✕
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-8">
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<PageTransition><HomePage /></PageTransition>} />
            <Route path="/rfqs/:id" element={<PageTransition><RFQDetailPage /></PageTransition>} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  )
}

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
