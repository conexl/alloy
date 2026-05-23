import { useState } from 'react'
import { Plus, User } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import CreateRFQPanel from './CreateRFQPanel'
import ProfileModal from './ProfileModal'
import type { User as UserType } from '../types'

interface HeaderProps {
  user: UserType | null
  onQuoteAlert?: (alert: any) => void
}

export default function Header({ user }: HeaderProps) {
  const [showCreatePanel, setShowCreatePanel] = useState(false)
  const [showProfile, setShowProfile] = useState(false)

  return (
    <>
      <motion.header 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="fixed top-0 left-0 right-0 z-40 bg-background/80 backdrop-blur-md border-b border-border"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <motion.div 
              className="flex items-center gap-2"
              whileHover={{ scale: 1.02 }}
            >
              <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
                <span className="text-accent-foreground font-bold text-sm">A</span>
              </div>
              <span className="text-xl font-bold text-foreground">Alloy</span>
            </motion.div>

            {/* Actions */}
            <div className="flex items-center gap-3">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setShowCreatePanel(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-accent-foreground text-sm font-semibold hover:bg-accent/90 transition-colors"
              >
                <Plus size={16} />
                <span className="hidden sm:inline">Заявка</span>
              </motion.button>

              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setShowProfile(true)}
                className="w-9 h-9 rounded-full bg-muted border border-border overflow-hidden flex items-center justify-center hover:border-accent/50 transition-colors"
              >
                {user?.photo_200 ? (
                  <img 
                    src={user.photo_200} 
                    alt="Profile" 
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <User size={18} className="text-muted-foreground" />
                )}
              </motion.button>
            </div>
          </div>
        </div>
      </motion.header>

      <AnimatePresence>
        {showCreatePanel && (
          <CreateRFQPanel onClose={() => setShowCreatePanel(false)} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showProfile && (
          <ProfileModal 
            user={user} 
            onClose={() => setShowProfile(false)} 
          />
        )}
      </AnimatePresence>
    </>
  )
}
