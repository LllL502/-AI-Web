import { defineStore } from 'pinia'
import { api, initializeCsrf } from '../api/client'

export type UserRole = 'USER' | 'STAFF' | 'ADMIN'
export interface SessionUser {
  id: number
  username: string
  display_name: string
  email: string
  role: UserRole
}

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null as SessionUser | null, ready: false }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
    isManagement: (state) => state.user?.role === 'STAFF' || state.user?.role === 'ADMIN',
  },
  actions: {
    async bootstrap() {
      try {
        await initializeCsrf()
        const response = await api<{ data: SessionUser }>('/auth/me/')
        this.user = response.data
      } catch {
        this.user = null
      } finally {
        this.ready = true
      }
    },
    async login(username: string, password: string) {
      await initializeCsrf()
      const response = await api<{ data: SessionUser }>('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      this.user = response.data
    },
    async logout() {
      await api('/auth/logout/', { method: 'POST' })
      this.user = null
    },
  },
})
