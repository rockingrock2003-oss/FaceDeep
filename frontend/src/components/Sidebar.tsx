'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import {
  LayoutDashboard,
  Users,
  Upload,
  Key,
  CreditCard,
  Settings,
  LogOut,
  Webhook,
  Building2,
  BookOpen,
  Activity,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Face Management', href: '/faces', icon: Users },
  { name: 'Bulk Import', href: '/bulk-import', icon: Upload },
  { name: 'API Keys', href: '/api-keys', icon: Key },
  { name: 'Webhooks', href: '/webhooks', icon: Webhook },
  { name: 'Organizations', href: '/organizations', icon: Building2 },
  { name: 'Billing', href: '/billing', icon: CreditCard },
  { name: 'API Docs', href: '/api-docs', icon: BookOpen },
  { name: 'Status', href: '/status', icon: Activity },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export default function Sidebar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()

  return (
    <div className="fixed left-0 top-0 h-full w-64 bg-gray-900 text-white">
      <div className="p-6">
        <h1 className="text-2xl font-bold">FaceDeep</h1>
        <p className="text-gray-400 text-sm mt-1">Enterprise Dashboard</p>
      </div>

      <nav className="mt-6 px-4 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>
        {navigation.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-lg mb-2 transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-800">
        <div className="px-4 mb-4">
          <p className="text-sm text-gray-400">Signed in as</p>
          <p className="text-sm font-medium truncate">{user?.username}</p>
          <p className="text-xs text-gray-500 truncate">{user?.email}</p>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-3 px-4 py-2 w-full text-gray-400 hover:bg-gray-800 hover:text-white rounded-lg transition-colors"
        >
          <LogOut className="w-5 h-5" />
          Sign out
        </button>
      </div>
    </div>
  )
}
