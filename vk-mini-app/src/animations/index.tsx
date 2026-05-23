import { motion, Variants } from 'framer-motion'
import { ReactNode } from 'react'

// Spring конфиг для естественного движения
export const spring = {
  type: 'spring' as const,
  stiffness: 300,
  damping: 30,
}

export const springSlow = {
  type: 'spring' as const,
  stiffness: 200,
  damping: 25,
}

export const springBouncy = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 15,
}

// Fade In Up
export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 30 },
  visible: { 
    opacity: 1, 
    y: 0,
    transition: springSlow
  }
}

// Fade In
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { 
    opacity: 1,
    transition: { duration: 0.4 }
  }
}

// Scale In
export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.9 },
  visible: { 
    opacity: 1, 
    scale: 1,
    transition: spring
  }
}

// Slide In Right
export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 40 },
  visible: { 
    opacity: 1, 
    x: 0,
    transition: springSlow
  },
  exit: { 
    opacity: 0, 
    x: -40,
    transition: { duration: 0.2 }
  }
}

// Stagger container
export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    }
  }
}

// Stagger item
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: springSlow
  }
}

// Hover scale
export const hoverScale = {
  scale: 1.02,
  transition: spring
}

// Hover lift
export const hoverLift = {
  y: -4,
  transition: spring
}

// Tap scale
export const tapScale = {
  scale: 0.98
}

interface AnimatedPageProps {
  children: ReactNode
  className?: string
}

export function AnimatedPage({ children, className = '' }: AnimatedPageProps) {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      exit="exit"
      variants={fadeIn}
      className={className}
    >
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {children}
      </motion.div>
    </motion.div>
  )
}

interface AnimatedCardProps {
  children: ReactNode
  className?: string
  hover?: boolean
  onClick?: () => void
}

export function AnimatedCard({ children, className = '', hover = true, onClick }: AnimatedCardProps) {
  return (
    <motion.div
      variants={staggerItem}
      whileHover={hover ? { y: -4, scale: 1.01, transition: spring } : undefined}
      whileTap={onClick ? tapScale : undefined}
      onClick={onClick}
      className={className}
      style={{ cursor: onClick ? 'pointer' : undefined }}
    >
      {children}
    </motion.div>
  )
}

interface AnimatedListProps {
  children: ReactNode
  className?: string
}

export function AnimatedList({ children, className = '' }: AnimatedListProps) {
  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      className={className}
    >
      {children}
    </motion.div>
  )
}

interface AnimatedListItemProps {
  children: ReactNode
  className?: string
}

export function AnimatedListItem({ children, className = '' }: AnimatedListItemProps) {
  return (
    <motion.div variants={staggerItem} className={className}>
      {children}
    </motion.div>
  )
}

// Layout animation wrapper
export function LayoutAnimation({ children, className = '' }: AnimatedPageProps) {
  return (
    <motion.div
      layout
      transition={springSlow}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// Number counter animation
export function AnimatedNumber({ value, className = '' }: { value: number; className?: string }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={springBouncy}
      className={className}
    >
      {value}
    </motion.span>
  )
}

// Page transition wrapper
export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, filter: 'blur(10px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      exit={{ opacity: 0, y: -20, filter: 'blur(10px)' }}
      transition={{ duration: 0.4, ease: 'easeInOut' }}
    >
      {children}
    </motion.div>
  )
}
