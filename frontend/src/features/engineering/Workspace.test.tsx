import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Workspace } from './Workspace'
import * as engineeringApi from './api'
import { ApiRequestError } from '../../api/client'
import { HANDOVER_ACTION_TEXT } from './constants'
import type { EngineeringFault, EngineeringFaultRepairUpdate } from './types'

vi.mock('./api')

afterEach(() => {
  // Scoped to this file's own mocks only - vi.resetAllMocks() is a
  // process-wide reset (Vitest's mock registry is shared across every
  // test file in a worker) and can intermittently wipe another file's
  // still-in-flight mock configuration during a full-suite run.
  vi.mocked(engineeringApi.getFaults).mockReset()
  vi.mocked(engineeringApi.acceptFault).mockReset()
  vi.mocked(engineeringApi.addRepairUpdate).mockReset()
  vi.mocked(engineeringApi.closeFault).mockReset()
  vi.mocked(engineeringApi.handOverFault).mockReset()
  vi.useRealTimers()
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
})

function fault(overrides: Partial<EngineeringFault> = {}): EngineeringFault {
  return {
    downtime_event_id: 1,
    production_run_id: 40,
    production_line: 'Rovema',
    fault_id: 3,
    machine: 'BV1',
    reason: 'Film Jam',
    reported_by: 'Marina',
    engineer: null,
    production_status: 'Ongoing',
    engineering_status: 'Not Started',
    opened_at: '2026-09-18T09:00:00+00:00',
    accepted_at: null,
    resolved_at: null,
    duration_minutes: 12,
    duration_is_active: true,
    repair_updates: [],
    ...overrides,
  }
}

function renderWorkspace(onSessionExpired = vi.fn(), onLogout = vi.fn()) {
  return render(
    <Workspace token="test-token" engineerName="Alfie" onLogout={onLogout} onSessionExpired={onSessionExpired} />,
  )
}

function repairUpdate(overrides: Partial<EngineeringFaultRepairUpdate> = {}): EngineeringFaultRepairUpdate {
  return {
    id: 1,
    engineer: 'Alfie',
    update_type: 'Follow Up',
    repair_classification: null,
    finding: 'Checked the sensor alignment.',
    action: 'Adjusted and will monitor.',
    notes: null,
    setting_name: null,
    previous_value: null,
    new_value: null,
    reason_for_change: null,
    affected_products_or_formats: null,
    engineering_status: 'Ongoing',
    created_at: '2026-09-18T09:15:00+00:00',
    ...overrides,
  }
}

// ==========================================================
// FAULT LOADING
// ==========================================================

describe('Engineering fault loading', () => {
  it('shows a loading state before the first response arrives', () => {
    vi.mocked(engineeringApi.getFaults).mockReturnValue(new Promise(() => {}))

    renderWorkspace()

    expect(screen.getByText(/loading engineering faults/i)).toBeInTheDocument()
  })

  it('shows an empty state when there are no faults', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderWorkspace()

    await waitFor(() =>
      expect(screen.getByText(/no open production faults right now/i)).toBeInTheDocument(),
    )
  })

  it('shows a safe error state with Retry on initial load failure', async () => {
    vi.mocked(engineeringApi.getFaults).mockRejectedValue(
      new ApiRequestError(503, 'Engineering data is temporarily unavailable. Please try again.'),
    )

    renderWorkspace()

    await waitFor(() =>
      expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('shows fault cards on success', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [fault()], total: 1 })

    renderWorkspace()

    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
  })

  it('renders three sections and filters correctly between them', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({
      items: [
        fault({ downtime_event_id: 1, machine: 'BV1', engineer: null }),
        fault({
          downtime_event_id: 2,
          machine: 'BV2',
          engineer: 'Alfie',
          engineering_status: 'Ongoing',
          accepted_at: '2026-09-18T09:05:00+00:00',
        }),
        fault({
          downtime_event_id: 3,
          machine: 'BV3',
          production_status: 'Resolved',
          engineering_status: 'Resolved',
          engineer: 'Dan',
          resolved_at: '2026-09-18T10:00:00+00:00',
        }),
      ],
      total: 3,
    })

    renderWorkspace()

    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    // Open tab (default) shows all Ongoing faults, mine or not.
    expect(screen.getByText(/BV2 — Film Jam/)).toBeInTheDocument()
    expect(screen.queryByText(/BV3 — Film Jam/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /my engineering jobs/i }))
    expect(screen.queryByText(/BV1 — Film Jam/)).not.toBeInTheDocument()
    expect(screen.getByText(/BV2 — Film Jam/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /resolved jobs/i }))
    expect(screen.queryByText(/BV2 — Film Jam/)).not.toBeInTheDocument()
    expect(screen.getByText(/BV3 — Film Jam/)).toBeInTheDocument()
  })

  it('manual Refresh calls GET /faults again', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderWorkspace()
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }))

    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))
  })

  it('polls again automatically after 30 seconds', async () => {
    vi.useFakeTimers()
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderWorkspace()
    await vi.waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(30_000)

    expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2)
  })

  it('pauses polling while the tab is hidden', async () => {
    vi.useFakeTimers()
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderWorkspace()
    await vi.waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(1))

    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))

    await vi.advanceTimersByTimeAsync(60_000)

    expect(engineeringApi.getFaults).toHaveBeenCalledTimes(1)
  })

  it('refreshes immediately and resumes polling when the tab becomes visible again', async () => {
    vi.useFakeTimers()
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderWorkspace()
    await vi.waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(1))

    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))

    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))

    await vi.waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))
  })

  it('a newer request replaces (cancels the effect of) a still-pending older one', async () => {
    let resolveFirst: (value: { items: EngineeringFault[]; total: number }) => void = () => {}
    let resolveSecond: (value: { items: EngineeringFault[]; total: number }) => void = () => {}

    vi.mocked(engineeringApi.getFaults)
      .mockReturnValueOnce(new Promise((resolve) => (resolveFirst = resolve)))
      .mockReturnValueOnce(new Promise((resolve) => (resolveSecond = resolve)))

    renderWorkspace()
    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }))

    // The second (newer) request resolves first, with fault BV2...
    resolveSecond({ items: [fault({ downtime_event_id: 2, machine: 'BV2' })], total: 1 })
    await waitFor(() => expect(screen.getByText(/BV2 — Film Jam/)).toBeInTheDocument())

    // ...the first (now-stale) request resolving afterwards must NOT
    // overwrite the newer result.
    resolveFirst({ items: [fault({ downtime_event_id: 1, machine: 'BV1' })], total: 1 })
    await new Promise((resolve) => setTimeout(resolve, 10))

    expect(screen.getByText(/BV2 — Film Jam/)).toBeInTheDocument()
    expect(screen.queryByText(/BV1 — Film Jam/)).not.toBeInTheDocument()
  })

  it('never issues overlapping requests - each abort signal is distinct', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [], total: 0 })

    renderWorkspace()
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }))
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))

    const [, signalA] = vi.mocked(engineeringApi.getFaults).mock.calls[0]
    const [, signalB] = vi.mocked(engineeringApi.getFaults).mock.calls[1]
    expect(signalA).not.toBe(signalB)
  })
})

// ==========================================================
// FAULT ACTIONS
// ==========================================================

describe('Engineering fault actions', () => {
  it('requires confirmation before accepting a job', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [fault()], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /accept job/i }))

    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(engineeringApi.acceptFault).not.toHaveBeenCalled()
  })

  it('accepts a job after confirmation and refreshes the list', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [fault()], total: 1 })
      .mockResolvedValueOnce({
        items: [fault({ engineer: 'Alfie', engineering_status: 'Ongoing' })],
        total: 1,
      })
    vi.mocked(engineeringApi.acceptFault).mockResolvedValue({
      status: 'success',
      downtime_event_id: 1,
      engineer: 'Alfie',
      engineering_status: 'Ongoing',
      accepted_at: '2026-09-18T09:10:00+00:00',
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /accept job/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /accept job/i }))

    await waitFor(() => expect(engineeringApi.acceptFault).toHaveBeenCalledWith('test-token', 1))
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))
  })

  it('shows a clear conflict message when another engineer accepted first', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [fault()], total: 1 })
    vi.mocked(engineeringApi.acceptFault).mockRejectedValue(
      new ApiRequestError(409, 'Fault 1 has already been accepted by another engineer.'),
    )

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /accept job/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /accept job/i }))

    await waitFor(() =>
      expect(screen.getByText(/already been accepted by another engineer/i)).toBeInTheDocument(),
    )
  })

  function acceptedByMe(overrides: Partial<EngineeringFault> = {}) {
    return fault({
      engineer: 'Alfie',
      engineering_status: 'Ongoing',
      accepted_at: '2026-09-18T09:05:00+00:00',
      ...overrides,
    })
  }

  it('submits a Mechanical repair update', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.addRepairUpdate).mockResolvedValue({
      status: 'success',
      downtime_event_id: 1,
      engineering_update_id: 9,
      created_at: '2026-09-18T09:20:00+00:00',
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const updateSection = screen.getByRole('heading', { name: 'Add Repair Update' }).closest('section') as HTMLElement
    fireEvent.click(within(updateSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(updateSection).getByLabelText(/finding/i), { target: { value: 'Sensor misaligned' } })
    fireEvent.change(within(updateSection).getByLabelText(/action taken/i), { target: { value: 'Realigned sensor' } })
    fireEvent.click(within(updateSection).getByRole('button', { name: /add repair update/i }))

    await waitFor(() =>
      expect(engineeringApi.addRepairUpdate).toHaveBeenCalledWith(
        'test-token',
        1,
        expect.objectContaining({ classification: 'Mechanical', finding: 'Sensor misaligned' }),
      ),
    )
    await waitFor(() => expect(screen.getByText(/repair update saved/i)).toBeInTheDocument())
  })

  it('shows Machine Setting fields only when that classification is selected, and validates them', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const updateSection = screen.getByRole('heading', { name: 'Add Repair Update' }).closest('section') as HTMLElement
    expect(within(updateSection).queryByLabelText(/setting name/i)).not.toBeInTheDocument()

    fireEvent.click(within(updateSection).getByRole('radio', { name: 'Machine Setting' }))
    expect(within(updateSection).getByLabelText(/setting name/i)).toBeInTheDocument()

    fireEvent.change(within(updateSection).getByLabelText(/finding/i), { target: { value: 'Seal failing' } })
    fireEvent.change(within(updateSection).getByLabelText(/action taken/i), { target: { value: 'Raised temperature' } })
    fireEvent.click(within(updateSection).getByRole('button', { name: /add repair update/i }))

    expect(await within(updateSection).findByText(/setting name is required/i)).toBeInTheDocument()
    expect(engineeringApi.addRepairUpdate).not.toHaveBeenCalled()
  })

  it('keeps entered text in the form when a repair update submission fails', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.addRepairUpdate).mockRejectedValue(
      new ApiRequestError(503, 'Could not complete the request. Please try again.'),
    )

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const updateSection = screen.getByRole('heading', { name: 'Add Repair Update' }).closest('section') as HTMLElement
    fireEvent.click(within(updateSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(updateSection).getByLabelText(/finding/i), { target: { value: 'Sensor misaligned' } })
    fireEvent.change(within(updateSection).getByLabelText(/action taken/i), { target: { value: 'Realigned sensor' } })
    fireEvent.click(within(updateSection).getByRole('button', { name: /add repair update/i }))

    await waitFor(() => expect(screen.getByText(/could not complete the request/i)).toBeInTheDocument())
    expect((within(updateSection).getByLabelText(/finding/i) as HTMLTextAreaElement).value).toBe('Sensor misaligned')
  })

  it('requires final confirmation before closing a fault', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'No' }))
    fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))

    expect(screen.getByText(/this will mark engineering status and production status as resolved/i)).toBeInTheDocument()
    expect(engineeringApi.closeFault).not.toHaveBeenCalled()
  })

  it('closes a fault after confirmation and moves it out of the open list', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockResolvedValueOnce({
        items: [
          acceptedByMe({ production_status: 'Resolved', engineering_status: 'Resolved', resolved_at: '2026-09-18T10:00:00+00:00' }),
        ],
        total: 1,
      })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue({
      status: 'success',
      downtime_event_id: 1,
      engineer: 'Alfie',
      engineering_status: 'Resolved',
      production_status: 'Resolved',
      resolved_at: '2026-09-18T10:00:00+00:00',
      maintenance_preventable: 'No',
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'No' }))
    fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))

    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))

    await waitFor(() => expect(engineeringApi.closeFault).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: /resolved jobs/i }))
    await waitFor(() => expect(faultCards(/BV1 — Film Jam/)).toHaveLength(1))
  })

  // --- State after a successful close ---

  const RESOLVED = acceptedByMe({
    production_status: 'Resolved',
    engineering_status: 'Resolved',
    resolved_at: '2026-09-18T10:00:00+00:00',
  })

  function closeResponse() {
    return {
      status: 'success',
      downtime_event_id: 1,
      engineer: 'Alfie',
      engineering_status: 'Resolved',
      production_status: 'Resolved',
      resolved_at: '2026-09-18T10:00:00+00:00',
      maintenance_preventable: 'No' as const,
    }
  }

  /** Only rendered fault CARDS - the success note names the same fault,
   * so a bare text query would match it too. */
  function faultCards(text: RegExp) {
    return Array.from(document.querySelectorAll('.engineering-fault-card')).filter((card) =>
      text.test(card.textContent ?? ''),
    )
  }

  function fillAndSubmitClose() {
    const section = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(section).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(section).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(section).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(section).getByRole('radio', { name: 'No' }))
    fireEvent.click(within(section).getByRole('button', { name: /close fault/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))
  }

  async function closeTheFault() {
    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fillAndSubmitClose()
    await waitFor(() => expect(engineeringApi.closeFault).toHaveBeenCalledTimes(1))
  }

  it('removes the closed fault from Open Production Faults', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockResolvedValue({ items: [RESOLVED], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    await closeTheFault()
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: /open production faults/i }))
    await waitFor(() =>
      expect(screen.getByText(/no open production faults right now/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/investigating/i)).not.toBeInTheDocument()
  })

  it('updates the Open, Mine and Resolved totals from the refreshed list', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockResolvedValue({ items: [RESOLVED], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    renderWorkspace()
    await waitFor(() => expect(screen.getByText('Open: 1')).toBeInTheDocument())
    expect(screen.getByText('Mine: 1')).toBeInTheDocument()
    expect(screen.getByText('Resolved: 0')).toBeInTheDocument()

    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fillAndSubmitClose()

    await waitFor(() => expect(screen.getByText('Open: 0')).toBeInTheDocument())
    expect(screen.getByText('Mine: 0')).toBeInTheDocument()
    expect(screen.getByText('Resolved: 1')).toBeInTheDocument()
  })

  it('shows the closed fault under Resolved Jobs without a further click', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockResolvedValue({ items: [RESOLVED], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    await closeTheFault()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /resolved jobs/i })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    )
    await waitFor(() => expect(faultCards(/BV1 — Film Jam/)).toHaveLength(1))
  })

  it('shows an accessible success confirmation and dismisses the panel', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockResolvedValue({ items: [RESOLVED], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    await closeTheFault()

    const note = await screen.findByRole('status')
    expect(note).toHaveTextContent(/fault closed/i)
    expect(note).toHaveTextContent(/BV1 — Film Jam is now Resolved/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps the close honest when the follow-up refresh fails', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockRejectedValue(new ApiRequestError(503, 'Engineering data is temporarily unavailable.'))
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    await closeTheFault()

    // The close succeeded and is still reported as such...
    expect(await screen.findByRole('status')).toHaveTextContent(/fault closed/i)
    // ...and the stale list is named as the problem, not the close.
    expect(
      await screen.findByText(/the fault was closed, but the list below could not be refreshed/i),
    ).toBeInTheDocument()
    expect(screen.queryByText(/could not close this fault/i)).not.toBeInTheDocument()
  })

  it('keeps the fault open and the form filled when the close request fails', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockRejectedValue(
      new ApiRequestError(503, 'Could not complete the request. Please try again.'),
    )

    await closeTheFault()

    expect(await screen.findByText(/could not complete the request/i)).toBeInTheDocument()
    expect(screen.queryByText(/fault closed/i)).not.toBeInTheDocument()

    const section = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    expect(within(section).getByLabelText(/finding/i)).toHaveValue('Fixed')
    expect(within(section).getByLabelText(/action taken/i)).toHaveValue('Replaced part')
    expect(within(section).getByRole('radio', { name: 'No' })).toBeChecked()
    expect(screen.getByText('Open: 1')).toBeInTheDocument()
  })

  it('does not duplicate the resolved entry when the close is replayed', async () => {
    // A retry of the same idempotent action replays the original
    // response; the authoritative read still returns exactly one row.
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedByMe()], total: 1 })
      .mockResolvedValue({ items: [RESOLVED], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    await closeTheFault()
    await waitFor(() => expect(screen.getByText('Resolved: 1')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }))

    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(3))
    expect(screen.getByText('Resolved: 1')).toBeInTheDocument()
    expect(faultCards(/BV1 — Film Jam/)).toHaveLength(1)
  })

  // --- Close Fault form completeness (backend CloseFaultRequest) ---

  /** Every label the backend contract requires for a Machine Setting
   * close (src/engineering_api.py: _SETTING_FIELD_NAMES). */
  const SETTING_LABELS = [
    /setting name/i,
    /previous value/i,
    /new value/i,
    /reason for change/i,
    /affected products or formats/i,
  ]

  async function openCloseSection() {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    return screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
  }

  it('shows only the Mechanical fields when Mechanical is selected', async () => {
    const section = await openCloseSection()
    fireEvent.click(within(section).getByRole('radio', { name: 'Mechanical' }))

    expect(within(section).getByLabelText(/finding/i)).toBeInTheDocument()
    expect(within(section).getByLabelText(/action taken/i)).toBeInTheDocument()
    expect(within(section).getByLabelText(/notes \(optional\)/i)).toBeInTheDocument()
    // The backend rejects a Mechanical update that carries setting fields.
    for (const label of SETTING_LABELS) {
      expect(within(section).queryByLabelText(label)).not.toBeInTheDocument()
    }
    // Preventability is asked for either classification.
    expect(
      within(section).getByText(/could this fault have been prevented by planned maintenance/i),
    ).toBeInTheDocument()
  })

  it('shows every conditional field when Machine Setting is selected', async () => {
    const section = await openCloseSection()
    fireEvent.click(within(section).getByRole('radio', { name: 'Machine Setting' }))

    for (const label of SETTING_LABELS) {
      const field = within(section).getByLabelText(label)
      expect(field).toBeInTheDocument()
      expect(field).toBeVisible()
    }
    // ...and the preventability question is still there, below them.
    expect(
      within(section).getByText(/could this fault have been prevented by planned maintenance/i),
    ).toBeInTheDocument()
    for (const answer of ['Yes', 'No', 'Unsure']) {
      expect(within(section).getByRole('radio', { name: answer })).toBeInTheDocument()
    }
  })

  it.each([['Mechanical'], ['Machine Setting']])(
    'requires the preventability answer for a %s close',
    async (classification) => {
      const section = await openCloseSection()
      fireEvent.click(within(section).getByRole('radio', { name: classification }))
      fireEvent.change(within(section).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
      fireEvent.change(within(section).getByLabelText(/action taken/i), { target: { value: 'Done' } })

      if (classification === 'Machine Setting') {
        fireEvent.change(within(section).getByLabelText(/setting name/i), { target: { value: 'Sealer' } })
        fireEvent.change(within(section).getByLabelText(/previous value/i), { target: { value: '185C' } })
        fireEvent.change(within(section).getByLabelText(/new value/i), { target: { value: '192C' } })
        fireEvent.change(within(section).getByLabelText(/reason for change/i), { target: { value: 'Seal' } })
        fireEvent.change(within(section).getByLabelText(/affected products or formats/i), {
          target: { value: '1kg' },
        })
      }

      fireEvent.click(within(section).getByRole('button', { name: /close fault/i }))

      expect(
        within(section).getByText(/answer whether planned maintenance could have prevented/i),
      ).toBeInTheDocument()
      expect(engineeringApi.closeFault).not.toHaveBeenCalled()
    },
  )

  it('blocks submission with accessible validation when setting fields are missing', async () => {
    const section = await openCloseSection()
    fireEvent.click(within(section).getByRole('radio', { name: 'Machine Setting' }))
    fireEvent.change(within(section).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(section).getByLabelText(/action taken/i), { target: { value: 'Done' } })
    fireEvent.click(within(section).getByRole('radio', { name: 'No' }))
    // Every setting field deliberately left blank.
    fireEvent.click(within(section).getByRole('button', { name: /close fault/i }))

    const messages = within(section).getAllByRole('alert').map((a) => a.textContent ?? '')
    expect(messages.some((m) => /setting name is required/i.test(m))).toBe(true)
    expect(messages.some((m) => /previous value is required/i.test(m))).toBe(true)
    expect(messages.some((m) => /new value is required/i.test(m))).toBe(true)
    expect(messages.some((m) => /reason for change is required/i.test(m))).toBe(true)
    expect(messages.some((m) => /affected products or formats is required/i.test(m))).toBe(true)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(engineeringApi.closeFault).not.toHaveBeenCalled()
  })

  it('submits every contract field for a Machine Setting close', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const section = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(section).getByRole('radio', { name: 'Machine Setting' }))
    fireEvent.change(within(section).getByLabelText(/finding/i), { target: { value: 'Seal drifted' } })
    fireEvent.change(within(section).getByLabelText(/action taken/i), { target: { value: 'Raised set point' } })
    fireEvent.change(within(section).getByLabelText(/setting name/i), { target: { value: 'Sealer temperature' } })
    fireEvent.change(within(section).getByLabelText(/previous value/i), { target: { value: '185C' } })
    fireEvent.change(within(section).getByLabelText(/new value/i), { target: { value: '192C' } })
    fireEvent.change(within(section).getByLabelText(/reason for change/i), { target: { value: 'Seal integrity' } })
    fireEvent.change(within(section).getByLabelText(/affected products or formats/i), {
      target: { value: '1 kg Pillow' },
    })
    fireEvent.click(within(section).getByRole('radio', { name: 'Unsure' }))
    fireEvent.click(within(section).getByRole('button', { name: /close fault/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))

    await waitFor(() => expect(engineeringApi.closeFault).toHaveBeenCalledTimes(1))
    expect(vi.mocked(engineeringApi.closeFault).mock.calls[0][2]).toEqual({
      classification: 'Machine Setting',
      finding: 'Seal drifted',
      action: 'Raised set point',
      notes: null,
      setting_name: 'Sealer temperature',
      previous_value: '185C',
      new_value: '192C',
      reason_for_change: 'Seal integrity',
      affected_products_or_formats: '1 kg Pillow',
      maintenance_preventable: 'Unsure',
    })
  })

  it('omits the Machine Setting fields entirely from a Mechanical close', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockResolvedValue(closeResponse())

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const section = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(section).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(section).getByLabelText(/finding/i), { target: { value: 'Worn roller' } })
    fireEvent.change(within(section).getByLabelText(/action taken/i), { target: { value: 'Replaced' } })
    fireEvent.click(within(section).getByRole('radio', { name: 'Yes' }))
    fireEvent.click(within(section).getByRole('button', { name: /close fault/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))

    await waitFor(() => expect(engineeringApi.closeFault).toHaveBeenCalledTimes(1))
    const payload = vi.mocked(engineeringApi.closeFault).mock.calls[0][2]
    // The backend rejects a Mechanical update carrying setting fields,
    // so they must be absent - not blank strings.
    for (const key of [
      'setting_name', 'previous_value', 'new_value',
      'reason_for_change', 'affected_products_or_formats',
    ]) {
      expect(payload).not.toHaveProperty(key)
    }
    expect(payload.maintenance_preventable).toBe('Yes')
  })

  // --- Maintenance preventability (Stage 6B2) ---

  it('asks the preventability question only when closing, with no preselected answer', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    expect(
      within(closeSection).getByText(/could this fault have been prevented by planned maintenance/i),
    ).toBeInTheDocument()
    for (const option of ['Yes', 'No', 'Unsure']) {
      expect(within(closeSection).getByRole('radio', { name: option })).not.toBeChecked()
    }

    // The interim repair-update form must not ask it - only /close takes it.
    const updateSection = screen.getByRole('heading', { name: 'Add Repair Update' }).closest('section') as HTMLElement
    expect(within(updateSection).queryByText(/prevented by planned maintenance/i)).not.toBeInTheDocument()
  })

  it('blocks the close until the preventability question is answered', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))

    expect(
      within(closeSection).getByText(/answer whether planned maintenance could have prevented/i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(engineeringApi.closeFault).not.toHaveBeenCalled()
  })

  it.each(['Yes', 'No', 'Unsure'] as const)(
    'sends "%s" with the close request, alongside the Machine Setting detail',
    async (answer) => {
      vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
      vi.mocked(engineeringApi.closeFault).mockResolvedValue({
        status: 'success',
        downtime_event_id: 1,
        engineer: 'Alfie',
        engineering_status: 'Resolved',
        production_status: 'Resolved',
        resolved_at: '2026-09-18T10:00:00+00:00',
        maintenance_preventable: answer,
      })

      renderWorkspace()
      await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
      fireEvent.click(screen.getByText(/BV1 — Film Jam/))

      const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
      fireEvent.click(within(closeSection).getByRole('radio', { name: 'Machine Setting' }))
      fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Seal failing' } })
      fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Raised temperature' } })
      fireEvent.change(within(closeSection).getByLabelText(/setting name/i), { target: { value: 'Sealer temperature' } })
      fireEvent.change(within(closeSection).getByLabelText(/previous value/i), { target: { value: '185C' } })
      fireEvent.change(within(closeSection).getByLabelText(/new value/i), { target: { value: '192C' } })
      fireEvent.change(within(closeSection).getByLabelText(/reason for change/i), { target: { value: 'Seal integrity' } })
      fireEvent.change(within(closeSection).getByLabelText(/affected products or formats/i), {
        target: { value: '1kg Pillow' },
      })
      fireEvent.click(within(closeSection).getByRole('radio', { name: answer }))
      fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))
      fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))

      await waitFor(() => expect(engineeringApi.closeFault).toHaveBeenCalledTimes(1))
      expect(vi.mocked(engineeringApi.closeFault).mock.calls[0][2]).toMatchObject({
        maintenance_preventable: answer,
        classification: 'Machine Setting',
        finding: 'Seal failing',
        action: 'Raised temperature',
        setting_name: 'Sealer temperature',
        previous_value: '185C',
        new_value: '192C',
        reason_for_change: 'Seal integrity',
        affected_products_or_formats: '1kg Pillow',
      })
    },
  )

  it('keeps the answer and the repair detail after a failed close', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockRejectedValue(
      new ApiRequestError(503, 'Could not complete the request. Please try again.'),
    )

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Unsure' }))
    fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))

    await waitFor(() => expect(screen.getByText(/could not complete the request/i)).toBeInTheDocument())

    const section = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    expect(within(section).getByLabelText(/finding/i)).toHaveValue('Fixed')
    expect(within(section).getByLabelText(/action taken/i)).toHaveValue('Replaced part')
    expect(within(section).getByRole('radio', { name: 'Unsure' })).toBeChecked()
  })

  it('shows a clear conflict message when closing an already-resolved fault', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedByMe()], total: 1 })
    vi.mocked(engineeringApi.closeFault).mockRejectedValue(
      new ApiRequestError(409, 'Fault 1 was already resolved by someone else.'),
    )

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'No' }))
    fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /close fault/i }))

    await waitFor(() =>
      expect(screen.getByText(/already resolved by someone else/i)).toBeInTheDocument(),
    )
  })

  it('disables the Accept confirmation button while the request is in flight, preventing duplicate submission', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [fault()], total: 1 })
    vi.mocked(engineeringApi.acceptFault).mockReturnValue(new Promise(() => {}))

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /accept job/i }))
    const confirmButton = within(screen.getByRole('alertdialog')).getByRole('button', {
      name: /accept job|please wait/i,
    })
    fireEvent.click(confirmButton)

    await waitFor(() => expect(confirmButton).toBeDisabled())
    expect(engineeringApi.acceptFault).toHaveBeenCalledTimes(1)
  })
})

// ==========================================================
// HAND OVER JOB
// ==========================================================

describe('Hand Over Job', () => {
  function acceptedBy(engineer: string, overrides: Partial<EngineeringFault> = {}) {
    return fault({
      engineer,
      engineering_status: 'Ongoing',
      accepted_at: '2026-09-18T09:05:00+00:00',
      ...overrides,
    })
  }

  it('shows the Hand Over Job button only for the engineer who owns the job', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.getByRole('heading', { name: 'Hand Over Job' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^hand over job$/i })).toBeInTheDocument()
    expect(screen.getByText('Release this job so another engineer can accept it.')).toBeInTheDocument()
  })

  it('places Hand Over Job directly below the fault summary, before Repair-update history and Add Repair Update', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const panel = screen.getByRole('dialog')
    const sectionHeadings = within(panel)
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent)

    // Hand Over Job must come immediately after the fault summary (the
    // <dl>, an <h2>, not an <h3> - so it's simply the FIRST h3) and
    // before Repair-update history and Add Repair Update, regardless of
    // where Close Fault ends up.
    expect(sectionHeadings[0]).toBe('Hand Over Job')
    expect(sectionHeadings.indexOf('Hand Over Job')).toBeLessThan(sectionHeadings.indexOf('Repair-update history'))
    expect(sectionHeadings.indexOf('Hand Over Job')).toBeLessThan(sectionHeadings.indexOf('Add Repair Update'))
  })

  it('hides the Hand Over Job button and section from an engineer who does not own the job', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Dan')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.queryByRole('heading', { name: 'Hand Over Job' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^hand over job$/i })).not.toBeInTheDocument()
    expect(screen.getByText(/assigned to Dan/i)).toBeInTheDocument()
    expect(screen.getByText(/add updates, hand it over, or close it/i)).toBeInTheDocument()
  })

  it('hides the Hand Over Job controls when accepted_at is null (legacy-assigned fault)', async () => {
    // A fault can have engineer set (e.g. legacy data written outside
    // the normal Accept flow) without ever having been genuinely
    // accepted. The backend's guarded UPDATE requires accepted_at IS
    // NOT NULL, so the control must not appear here either - it would
    // otherwise always be rejected with a 409.
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({
      items: [acceptedBy('Alfie', { accepted_at: null })],
      total: 1,
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.queryByRole('heading', { name: 'Hand Over Job' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^hand over job$/i })).not.toBeInTheDocument()
  })

  it('hides the Hand Over Job controls when production_status is not Ongoing', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({
      items: [acceptedBy('Alfie', { production_status: 'Resolved', resolved_at: '2026-09-18T10:00:00+00:00' })],
      total: 1,
    })

    renderWorkspace()
    fireEvent.click(screen.getByRole('button', { name: /resolved jobs/i }))
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.queryByRole('heading', { name: 'Hand Over Job' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^hand over job$/i })).not.toBeInTheDocument()
  })

  it('hides the Hand Over Job controls when engineering_status is not Ongoing', async () => {
    // e.g. 'Not Started' - the fault is still Ongoing in production
    // terms but has not genuinely been accepted at the engineering-status
    // level, so the guarded UPDATE would reject it.
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({
      items: [acceptedBy('Alfie', { engineering_status: 'Not Started' })],
      total: 1,
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.queryByRole('heading', { name: 'Hand Over Job' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^hand over job$/i })).not.toBeInTheDocument()
  })

  it('requires a non-empty note before the handover can proceed', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))
    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))

    expect(await within(handoverSection).findByText(/handover note is required/i)).toBeInTheDocument()
    expect(engineeringApi.handOverFault).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('rejects a note longer than the maximum length', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    const textarea = within(handoverSection).getByLabelText(/handover note/i) as HTMLTextAreaElement
    // maxLength on the textarea itself already stops typing past the
    // limit in a real browser - fireEvent.change bypasses that, so this
    // proves the validator itself also rejects an over-length value.
    fireEvent.change(textarea, { target: { value: 'x'.repeat(501) } })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))

    expect(await within(handoverSection).findByText(/500 characters or fewer/i)).toBeInTheDocument()
    expect(engineeringApi.handOverFault).not.toHaveBeenCalled()
  })

  it('requires confirmation, explaining the job becomes unassigned, before calling the API', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))

    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(
      within(screen.getByRole('alertdialog')).getByText(
        /this job will become unassigned and return to open production faults/i,
      ),
    ).toBeInTheDocument()
    expect(engineeringApi.handOverFault).not.toHaveBeenCalled()
  })

  it('cancelling the confirmation dialog does not call the API', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /cancel/i }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(engineeringApi.handOverFault).not.toHaveBeenCalled()
  })

  it('hands over the job after confirmation, refreshes, returns to Open Production Faults, and shows success', async () => {
    vi.mocked(engineeringApi.getFaults)
      .mockResolvedValueOnce({ items: [acceptedBy('Alfie')], total: 1 })
      .mockResolvedValueOnce({ items: [fault({ engineer: null, engineering_status: 'Not Started' })], total: 1 })
    vi.mocked(engineeringApi.handOverFault).mockResolvedValue({
      status: 'success',
      downtime_event_id: 1,
      engineer: null,
      engineering_status: 'Not Started',
      production_status: 'Ongoing',
      accepted_at: null,
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /^hand over job$/i }))

    await waitFor(() =>
      expect(engineeringApi.handOverFault).toHaveBeenCalledWith(
        'test-token',
        1,
        { note: 'Escalating to shift lead.' },
      ),
    )
    await waitFor(() => expect(engineeringApi.getFaults).toHaveBeenCalledTimes(2))

    // Panel closed, back on the (default, active) Open Production Faults tab.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open production faults/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByText(/job handed over/i)).toBeInTheDocument()
  })

  it('redirects to session-expired handling on a 401 response', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })
    vi.mocked(engineeringApi.handOverFault).mockRejectedValue(new ApiRequestError(401, 'Session expired.'))
    const onSessionExpired = vi.fn()

    renderWorkspace(onSessionExpired)
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /^hand over job$/i }))

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1))
  })

  it('shows a clear message for a stale/conflicting fault (409)', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })
    vi.mocked(engineeringApi.handOverFault).mockRejectedValue(
      new ApiRequestError(409, 'Fault 1 is no longer assigned to you, or has already been resolved.'),
    )

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /^hand over job$/i }))

    await waitFor(() =>
      expect(screen.getByText(/no longer assigned to you, or has already been resolved/i)).toBeInTheDocument(),
    )
  })

  it('shows a clear message for a database failure (503)', async () => {
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })
    vi.mocked(engineeringApi.handOverFault).mockRejectedValue(
      new ApiRequestError(503, 'Could not complete the request. Please try again.'),
    )

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))

    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /^hand over job$/i }))

    await waitFor(() => expect(screen.getByText(/could not complete the request/i)).toBeInTheDocument())
  })

  it('prevents a duplicate handover request while one is already in flight', async () => {
    // Confirming dismisses the dialog immediately (same established
    // pattern as Close Fault) rather than keeping it open and disabled
    // like Accept does. Duplicate submission is still prevented: the
    // Handover form shares the same isSubmittingHandover flag, so
    // reopening it while the first request is still pending immediately
    // renders its submit button disabled and relabelled "Please wait…" -
    // there is no way to reach a second confirm click at all.
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })
    vi.mocked(engineeringApi.handOverFault).mockReturnValue(new Promise(() => {}))

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))
    let handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'First attempt.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /^hand over job$/i }))

    await waitFor(() => expect(engineeringApi.handOverFault).toHaveBeenCalledTimes(1))

    // Reopen: the request from the first attempt is still unresolved.
    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))
    handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    const reopenedSubmitButton = within(handoverSection).getByRole('button', { name: /please wait/i })
    expect(reopenedSubmitButton).toBeDisabled()

    fireEvent.click(reopenedSubmitButton)
    expect(engineeringApi.handOverFault).toHaveBeenCalledTimes(1)
  })

  it('cancelling out of the handover form leaves Close Fault fully usable, and vice versa', async () => {
    // Regression guard for the pendingAction refactor: filling in both
    // the Close and Handover forms must never show two confirmation
    // dialogs at once, and cancelling one must not disturb the other.
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({ items: [acceptedBy('Alfie')], total: 1 })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    const closeSection = screen.getByRole('heading', { name: 'Close Fault' }).closest('section') as HTMLElement
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'Mechanical' }))
    fireEvent.change(within(closeSection).getByLabelText(/finding/i), { target: { value: 'Fixed' } })
    fireEvent.change(within(closeSection).getByLabelText(/action taken/i), { target: { value: 'Replaced part' } })
    fireEvent.click(within(closeSection).getByRole('radio', { name: 'No' }))
    fireEvent.click(within(closeSection).getByRole('button', { name: /close fault/i }))
    expect(screen.getAllByRole('alertdialog')).toHaveLength(1)

    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /cancel/i }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^hand over job$/i }))
    const handoverSection = screen.getByRole('heading', { name: 'Hand Over Job' }).closest('section') as HTMLElement
    fireEvent.change(within(handoverSection).getByLabelText(/handover note/i), {
      target: { value: 'Escalating to shift lead.' },
    })
    fireEvent.click(within(handoverSection).getByRole('button', { name: /^hand over job$/i }))

    expect(screen.getAllByRole('alertdialog')).toHaveLength(1)
    expect(
      within(screen.getByRole('alertdialog')).getByText(/this job will become unassigned/i),
    ).toBeInTheDocument()
  })
})

// ==========================================================
// REPAIR-UPDATE HISTORY LABELLING
// ==========================================================

describe('Repair-update history labelling', () => {
  it('does not mislabel an ordinary unclassified Follow Up as a handover', async () => {
    // repair_classification: null alone must NOT be read as a handover -
    // only the exact HANDOVER_ACTION_TEXT identifies one. An ordinary
    // Follow Up with no classification (this API never requires one for
    // "Follow Up" writes outside /handover) must still show as a normal
    // Finding/Action entry.
    const ordinaryFollowUp = repairUpdate({
      id: 5,
      action: 'Kept monitoring, no change made yet.',
      finding: 'Sensor still intermittent.',
    })
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({
      items: [fault({ engineer: 'Alfie', engineering_status: 'Ongoing', repair_updates: [ordinaryFollowUp] })],
      total: 1,
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.queryByText(/handed over/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/handover note:/i)).not.toBeInTheDocument()
    expect(screen.getByText(/finding: sensor still intermittent\./i)).toBeInTheDocument()
    expect(screen.getByText(/action: kept monitoring, no change made yet\./i)).toBeInTheDocument()
  })

  it('labels a genuine handover history entry correctly', async () => {
    const handoverEntry = repairUpdate({
      id: 6,
      action: HANDOVER_ACTION_TEXT,
      finding: 'Escalating to shift lead - need electrical support.',
    })
    vi.mocked(engineeringApi.getFaults).mockResolvedValue({
      items: [fault({ engineer: 'Alfie', engineering_status: 'Ongoing', repair_updates: [handoverEntry] })],
      total: 1,
    })

    renderWorkspace()
    await waitFor(() => expect(screen.getByText(/BV1 — Film Jam/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/BV1 — Film Jam/))

    expect(screen.getByText('Handed over')).toBeInTheDocument()
    expect(
      screen.getByText(/handover note: escalating to shift lead - need electrical support\./i),
    ).toBeInTheDocument()
    // Never shown as a plain Finding/Action pair once it's identified
    // as a handover - the raw fixed action text is not user-facing copy.
    expect(screen.queryByText(/^action:/i)).not.toBeInTheDocument()
  })
})
