'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { billingAPI } from '@/lib/api'
import { Check, X } from 'lucide-react'

const plans = [
  {
    name: 'Free',
    price: 0,
    features: [
      '100 API calls/day',
      '1,000 faces storage',
      'Basic support',
    ],
    limits: { daily: 100, storage: 1000 },
  },
  {
    name: 'Starter',
    price: 29,
    features: [
      '10,000 API calls/day',
      '50,000 faces storage',
      'Email support',
      'Webhooks',
    ],
    limits: { daily: 10000, storage: 50000 },
  },
  {
    name: 'Pro',
    price: 99,
    features: [
      '100,000 API calls/day',
      '500,000 faces storage',
      'Priority support',
      'Webhooks',
      'Advanced analytics',
    ],
    limits: { daily: 100000, storage: 500000 },
  },
  {
    name: 'Enterprise',
    price: 299,
    features: [
      'Unlimited API calls',
      'Unlimited faces storage',
      'Dedicated support',
      'Custom integrations',
      'SLA guarantee',
    ],
    limits: { daily: -1, storage: -1 },
  },
]

export default function BillingPage() {
  const { user } = useAuth()
  const [usage, setUsage] = useState<any>(null)

  useEffect(() => {
    fetchUsage()
  }, [])

  const fetchUsage = async () => {
    try {
      const response = await billingAPI.getUsage()
      setUsage(response.data)
    } catch (error) {
      console.error('Failed to fetch usage:', error)
    }
  }

  const currentPlan = plans.find((p) => p.name.toLowerCase() === user?.plan) || plans[0]

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Billing & Plans</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-xl font-semibold mb-4">Current Usage</h2>
        <div className="grid grid-cols-3 gap-4">
          <div className="p-4 bg-blue-50 rounded-lg">
            <p className="text-sm text-gray-500">API Calls Today</p>
            <p className="text-2xl font-bold text-blue-600">
              {usage?.daily_requests_used || 0}
            </p>
          </div>
          <div className="p-4 bg-green-50 rounded-lg">
            <p className="text-sm text-gray-500">Total Faces</p>
            <p className="text-2xl font-bold text-green-600">
              {user?.entry_in_chroma_db || 0}
            </p>
          </div>
          <div className="p-4 bg-purple-50 rounded-lg">
            <p className="text-sm text-gray-500">Current Plan</p>
            <p className="text-2xl font-bold text-purple-600 capitalize">
              {user?.plan || 'free'}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {plans.map((plan) => {
          const isCurrent = plan.name.toLowerCase() === user?.plan
          return (
            <div
              key={plan.name}
              className={`bg-white rounded-lg shadow p-6 ${
                isCurrent ? 'ring-2 ring-blue-500' : ''
              }`}
            >
              {isCurrent && (
                <span className="bg-blue-500 text-white text-xs px-2 py-1 rounded-full">
                  Current
                </span>
              )}
              <h3 className="text-xl font-bold mt-2">{plan.name}</h3>
              <p className="text-3xl font-bold mt-2">
                ${plan.price}
                <span className="text-sm font-normal text-gray-500">/month</span>
              </p>
              <ul className="mt-4 space-y-2">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm">
                    <Check className="w-4 h-4 text-green-500" />
                    {feature}
                  </li>
                ))}
              </ul>
              <button
                className={`w-full mt-6 py-2 rounded-lg ${
                  isCurrent
                    ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
                disabled={isCurrent}
              >
                {isCurrent ? 'Current Plan' : 'Upgrade'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
