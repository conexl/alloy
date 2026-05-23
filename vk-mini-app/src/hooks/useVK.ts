import { useState, useEffect } from 'react'
import bridge from '@vkontakte/vk-bridge'
import type { User } from '../types'

// Получить vk_user_id из URL (для разработки)
function getVkIdFromUrl(): number | null {
  const params = new URLSearchParams(window.location.search)
  const vkId = params.get('vk_user_id')
  if (vkId) return parseInt(vkId, 10)
  
  // Проверяем hash
  const hash = window.location.hash.replace('#', '')
  const hashParams = new URLSearchParams(hash)
  const hashVkId = hashParams.get('vk_user_id')
  if (hashVkId) return parseInt(hashVkId, 10)
  
  return null
}

// Promise с таймаутом
function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Timeout')), ms)
    promise
      .then(resolve)
      .catch(reject)
      .finally(() => clearTimeout(timeout))
  })
}

export function useVK() {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isFallback, setIsFallback] = useState(false)

  useEffect(() => {
    async function init() {
      // Проверяем fallback ID из URL сразу
      const fallbackId = getVkIdFromUrl()
      
      try {
        // Пробуем инициализировать VK Bridge с таймаутом 3 сек
        await withTimeout(bridge.send('VKWebAppInit'), 3000)
        
        // Получаем параметры запуска
        const launchParams = await withTimeout(bridge.send('VKWebAppGetLaunchParams'), 3000)
        if ((launchParams as any).result) {
          localStorage.setItem('vk_params', JSON.stringify(launchParams))
        }
        
        // Получаем данные пользователя
        const userInfo = await withTimeout(bridge.send('VKWebAppGetUserInfo'), 3000)
        const userData = userInfo as any
        if (userData.id) {
          const user: User = {
            vk_id: userData.id,
            first_name: userData.first_name || 'Пользователь',
            last_name: userData.last_name || '',
            photo_200: userData.photo_200,
          }
          setUser(user)
          localStorage.setItem('vk_user_id', String(user.vk_id))
        }
      } catch (err) {
        console.warn('VK Bridge не инициализирован:', err)
        
        // Fallback режим для разработки
        const vkId = fallbackId || parseInt(localStorage.getItem('vk_user_id') || '0', 10)
        
        if (vkId) {
          console.log(`Fallback режим: используем vk_id=${vkId}`)
          setUser({
            vk_id: vkId,
            first_name: 'Dev',
            last_name: `User (${vkId})`,
          })
          localStorage.setItem('vk_user_id', String(vkId))
          setIsFallback(true)
        } else {
          setError('Приложение должно быть открыто через VK. Или добавьте ?vk_user_id=123 в URL')
        }
      } finally {
        setIsLoading(false)
      }
    }
    
    init()
  }, [])

  return { user, isLoading, error, isFallback }
}
