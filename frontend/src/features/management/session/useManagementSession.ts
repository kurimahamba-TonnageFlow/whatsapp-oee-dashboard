import { useContext } from 'react'
import { ManagementSessionContext, type ManagementSessionContextValue } from './managementSessionContext'

/** The shared Management session. Only usable inside
 * ManagementSessionProvider (mounted by ManagementLayout around
 * /management, /management/performance and /dashboard). */
export function useManagementSession(): ManagementSessionContextValue {
  const value = useContext(ManagementSessionContext)
  if (!value) {
    throw new Error('useManagementSession must be used inside ManagementSessionProvider.')
  }
  return value
}
