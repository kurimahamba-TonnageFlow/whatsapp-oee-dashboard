import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fixtures from '../../../../preview/intelligence-fixtures.json'
import { OperationalIntelligenceView } from './OperationalIntelligence'
import type { IntelligenceSnapshot } from './types'

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(cleanup)
function open(mode: keyof typeof fixtures = 'normal', change?: (data: IntelligenceSnapshot) => void) {
  const data = structuredClone(fixtures[mode]) as unknown as IntelligenceSnapshot
  change?.(data)
  render(<MemoryRouter><OperationalIntelligenceView data={data} error={null} loading={false} refresh={vi.fn()} period="production_week" onPeriod={vi.fn()} line="" onLine={vi.fn()}/></MemoryRouter>)
}
describe('Financial preview', () => {
  it('every locked metric and the trend opens one modal and returns focus to the trigger', () => {
    open()
    const triggers = [...screen.getAllByRole('button', { name: /Phase 2 financial preview/ }), screen.getByRole('button', { name: 'Unlock Financial Trends in Phase 2' })]
    expect(triggers.length).toBeGreaterThan(20)
    for (const trigger of triggers) {
      trigger.focus()
      fireEvent.click(trigger)
      const dialog = screen.getByRole('dialog')
      expect(dialog).toHaveTextContent('Availability, implementation scope and pricing will be agreed separately.')
      expect(within(dialog).getAllByRole('listitem')).toHaveLength(8)
      fireEvent.click(within(dialog).getByRole('button', { name: 'Continue Viewing Dashboard' }))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(trigger).toHaveFocus()
    }
  })
  it('offers a contact message without inventing a booking URL or price', () => {
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Cost per Tonne: Phase 2 financial preview' }))
    fireEvent.click(screen.getByRole('button', { name: 'Discuss Phase 2' }))
    expect(screen.getByRole('status')).toHaveTextContent('Please contact your Tonnage Flow representative')
    expect(within(screen.getByRole('dialog')).queryByRole('link')).not.toBeInTheDocument()
    fireEvent(screen.getByRole('dialog'), new Event('cancel'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('never reveals financial amounts even if a client-side flag changes', () => {
    open('normal', data => { data.capabilities.financial_intelligence = true })
    expect(screen.getAllByText(/\u00a30,000/)).toHaveLength(20)
    expect(screen.getAllByText('Placeholder').length).toBeGreaterThan(15)
  })
})
describe('Operational empty and exceptional states', () => {
  it('never turns missing production into zero, recovery claims or connected upstream stages', () => {
    open('empty')
    expect(screen.getByRole('article', { name: 'Actual Tonnes This Week' })).toHaveTextContent('No data')
    expect(screen.getByRole('article', { name: 'Weekly Tonnage Target' })).toHaveTextContent('Not set')
    expect(screen.getByRole('region', { name: 'Improvement Priorities' })).toHaveTextContent('when production-stop evidence is recorded')
    expect(screen.getAllByText('Data not connected')).toHaveLength(4)
    expect(screen.getByRole('region', { name: 'Planned vs Unplanned Downtime' })).toHaveTextContent('No downtime recorded')
  })
  it('keeps entirely Not Scheduled hours out of achievement', () => {
    open('unscheduled')
    const table = screen.getByRole('table', { name: 'Line Profitability Snapshot' })
    const gic = within(table).getAllByRole('row').find(row => row.textContent?.startsWith('GIC'))!
    expect(gic).toHaveTextContent('Not scheduled')
    expect(gic).not.toHaveTextContent('0.0%')
  })
  it('retains over-target progress text while restricting visual fill to its track', () => {
    open('normal', data => { data.weekly.progress_percent = 145.6 })
    expect(screen.getByRole('article', { name: 'Weekly Tonnage Target' })).toHaveTextContent('145.6% complete')
    expect(screen.getByRole('img', { name: 'Weekly target: 145.6% complete' }).firstElementChild).toHaveStyle({ width: '100%' })
  })
})
