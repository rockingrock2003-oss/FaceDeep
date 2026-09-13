'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI } from '@/lib/api'

interface User {
  id: string
  username: string
  email: string
  plan: string
  entry_in_chroma_db: number
  number_of_api_use_for_service: number
}

interface AuthContextType {
  user: User | null
  token: string | null
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => void
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const storedToken = localStorage.getItem('access_token')
    if (storedToken) {
      setToken(storedToken)
      fetchUser()
    } else {
      setIsLoading(false)
    }
  }, [])

  const fetchUser = async () => {
    try {
      const response = await authAPI.getMe()
      setUser(response.data)
    } catch (error) {
      localStorage.removeItem('access_token')
      setToken(null)
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (username: string, password: string) => {
    const response = await authAPI.login({ username, password })
    const { access_token } = response.data
    localStorage.setItem('access_token', access_token)
    setToken(access_token)
    await fetchUser()
  }

  const register = async (username: string, email: string, password: string) => {
    const response = await authAPI.register({ username, email, password })
    const { access_token } = response.data
    localStorage.setItem('access_token', access_token)
    setToken(access_token)
    await fetchUser()
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    setToken(null)
    setUser(null)
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
