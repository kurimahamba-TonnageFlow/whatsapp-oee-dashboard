import { AppShell } from '../layouts/AppShell'
import { HmiScreen } from '../features/hmi/HmiScreen'

export function HmiPage() {
  return (
    <AppShell>
      <HmiScreen />
    </AppShell>
  )
}
