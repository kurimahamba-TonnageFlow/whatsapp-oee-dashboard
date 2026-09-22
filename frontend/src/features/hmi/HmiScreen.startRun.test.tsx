import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { CUSTOMERS, LINE_TECHNICIANS, PRODUCTION_LINES, PRODUCTS } from './constants'

vi.mock('./api')

afterEach(() => {
  // Scoped to this file's own mocks only - vi.resetAllMocks() is a
  // process-wide reset (Vitest's mock registry is shared across every
  // test file in a worker) and can intermittently wipe another file's
  // still-in-flight mock configuration during a full-suite run.
  vi.mocked(hmiApi.getHmiConfig).mockReset()
  vi.mocked(hmiApi.startRun).mockReset()
  window.localStorage.clear()
})

const READY_CONFIG = {
  lines: PRODUCTION_LINES.map((name, index) => ({ id: index + 1, name, machines: [] })),
}

function renderHmi() {
  return render(
    <MemoryRouter initialEntries={['/hmi']}>
      <Routes>
        <Route path="/hmi" element={<HmiScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function openStartRunForm(lineName = 'Rovema') {
  vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
  renderHmi()
  await waitFor(() => expect(screen.getByText(lineName)).toBeInTheDocument())
  const card = screen.getByText(lineName).closest('article') as HTMLElement
  fireEvent.click(within(card).getByRole('button', { name: /start run/i }))
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText(/line technician/i), { target: { value: 'Liam' } })
  fireEvent.change(screen.getByLabelText(/^shift/i), { target: { value: 'Days' } })
  fireEvent.change(screen.getByLabelText(/^customer/i), { target: { value: 'Asda' } })
  fireEvent.change(screen.getByLabelText(/^product/i), { target: { value: 'White Basmati' } })
  fireEvent.change(screen.getByLabelText(/pack weight label/i), { target: { value: '1kg' } })
  fireEvent.change(screen.getByLabelText(/pack weight \(kg\)/i), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText(/packs per case/i), { target: { value: '8' } })
  fireEvent.change(screen.getByLabelText(/^format/i), { target: { value: '1 kg × 8' } })
  fireEvent.change(screen.getByLabelText(/target speed/i), { target: { value: '120' } })
  fireEvent.change(screen.getByLabelText(/cases per pallet/i), { target: { value: '220' } })
  fireEvent.change(screen.getByLabelText(/pallets remaining/i), { target: { value: '38' } })
  fireEvent.change(screen.getByLabelText(/previous run completed/i), { target: { value: '0' } })
}

describe('HmiScreen Start Run form', () => {
  it('opens the Start Run form for the selected line', async () => {
    await openStartRunForm('Rovema')
    expect(screen.getByRole('heading', { name: /start run — rovema/i })).toBeInTheDocument()
  })

  it('offers all 12 technicians, and the same set on every line', async () => {
    for (const line of PRODUCTION_LINES) {
      const { unmount } = await (async () => {
        vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(READY_CONFIG)
        const result = renderHmi()
        await waitFor(() => expect(screen.getByText(line)).toBeInTheDocument())
        const card = screen.getByText(line).closest('article') as HTMLElement
        fireEvent.click(within(card).getByRole('button', { name: /start run/i }))
        return result
      })()

      const select = screen.getByLabelText(/line technician/i) as HTMLSelectElement
      const optionValues = Array.from(select.options).map((o) => o.value).filter(Boolean)
      expect(optionValues).toEqual([...LINE_TECHNICIANS])

      unmount()
    }
  })

  it('offers Waitrose as a customer', async () => {
    await openStartRunForm()
    const select = screen.getByLabelText(/^customer/i) as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value)
    expect(values).toContain('Waitrose')
    expect(CUSTOMERS).toContain('Waitrose')
  })

  it('offers every confirmed product', async () => {
    await openStartRunForm()
    const select = screen.getByLabelText(/^product/i) as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value).filter(Boolean)
    expect(values).toEqual([...PRODUCTS])
  })

  it('accepts the format example "1×10"', async () => {
    await openStartRunForm()
    const formatField = screen.getByLabelText(/^format/i)
    fireEvent.change(formatField, { target: { value: '1×10' } })
    expect(formatField).toHaveValue('1×10')
  })

  it('keeps cases per pallet editable', async () => {
    await openStartRunForm()
    const field = screen.getByLabelText(/cases per pallet/i)
    expect(field).not.toBeDisabled()
    fireEvent.change(field, { target: { value: '180' } })
    expect(field).toHaveValue(180)
  })

  it('shows required-field validation beside the field', async () => {
    await openStartRunForm()
    fireEvent.click(screen.getByRole('button', { name: /review run/i }))
    expect(screen.getAllByText('Required.').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /start run/i })).toBeInTheDocument()
  })

  it('shows numeric validation for non-positive values', async () => {
    await openStartRunForm()
    fillValidForm()
    fireEvent.change(screen.getByLabelText(/pack weight \(kg\)/i), { target: { value: '0' } })

    fireEvent.click(screen.getByRole('button', { name: /review run/i }))

    expect(screen.getAllByText(/pack weight \(kg\) greater than 0/i).length).toBeGreaterThan(0)
  })

  it('blocks Review Run when the pack weight label and kg value do not match', async () => {
    await openStartRunForm()
    fillValidForm()
    fireEvent.change(screen.getByLabelText(/pack weight label/i), { target: { value: '500g' } })
    fireEvent.change(screen.getByLabelText(/pack weight \(kg\)/i), { target: { value: '500' } })

    fireEvent.click(screen.getByRole('button', { name: /review run/i }))

    expect(
      screen.getAllByText('Pack weight does not match. 500g must equal 0.5 kg.').length,
    ).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: /start run/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /review run/i })).not.toBeInTheDocument()
  })

  it('shows the entered details on the Review screen', async () => {
    await openStartRunForm()
    fillValidForm()
    fireEvent.click(screen.getByRole('button', { name: /review run/i }))

    expect(screen.getByRole('heading', { name: /review run/i })).toBeInTheDocument()
    expect(screen.getByText('Liam')).toBeInTheDocument()
    expect(screen.getByText('Asda')).toBeInTheDocument()
    expect(screen.getByText('White Basmati')).toBeInTheDocument()
  })

  it('shows the readable pack weight label and the converted kg value separately on the Review screen', async () => {
    await openStartRunForm()
    fillValidForm()
    fireEvent.change(screen.getByLabelText(/pack weight label/i), { target: { value: '500g' } })

    fireEvent.click(screen.getByRole('button', { name: /review run/i }))

    expect(screen.getByRole('heading', { name: /review run/i })).toBeInTheDocument()
    expect(screen.getByText('500g')).toBeInTheDocument()
    expect(screen.getByText('0.5')).toBeInTheDocument()
  })

  it('auto-fills the pack weight (kg) field from a valid pack weight label', async () => {
    await openStartRunForm()
    fireEvent.change(screen.getByLabelText(/pack weight label/i), { target: { value: '500g' } })

    expect(screen.getByLabelText(/pack weight \(kg\)/i)).toHaveValue(0.5)
  })

  it('shows the Run Started confirmation with technician, target speed, pallets remaining and shift', async () => {
    vi.mocked(hmiApi.startRun).mockResolvedValue({
      status: 'success',
      message: 'Run started',
      run_id: 42,
      production_line: 'Rovema',
      line_technician: 'Liam',
      pallets_remaining: 38,
    })

    await openStartRunForm()
    fillValidForm()
    fireEvent.click(screen.getByRole('button', { name: /review run/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm start run/i }))

    await waitFor(() => expect(screen.getByText('✓ RUN STARTED')).toBeInTheDocument())
    expect(screen.getByText('Liam')).toBeInTheDocument()
    expect(screen.getByText('120 packs/min')).toBeInTheDocument()
    expect(screen.getByText('38')).toBeInTheDocument()
    expect(screen.getByText('Days')).toBeInTheDocument()
  })

  it('prevents double submission of Start Run', async () => {
    let resolveStart: (value: Awaited<ReturnType<typeof hmiApi.startRun>>) => void = () => {}
    vi.mocked(hmiApi.startRun).mockReturnValue(
      new Promise((resolve) => {
        resolveStart = resolve
      }),
    )

    await openStartRunForm()
    fillValidForm()
    fireEvent.click(screen.getByRole('button', { name: /review run/i }))

    const confirmButton = screen.getByRole('button', { name: /confirm start run/i })
    fireEvent.click(confirmButton)
    fireEvent.click(confirmButton)
    fireEvent.click(confirmButton)

    expect(hmiApi.startRun).toHaveBeenCalledTimes(1)

    resolveStart({
      status: 'success',
      message: 'Run started',
      run_id: 1,
      production_line: 'Rovema',
      line_technician: 'Liam',
      pallets_remaining: 38,
    })
    await waitFor(() => expect(screen.getByText('✓ RUN STARTED')).toBeInTheDocument())
  })

  it('shows a clear message for a duplicate active-run response, not a raw server error', async () => {
    const { ApiRequestError } = await import('../../api/client')
    vi.mocked(hmiApi.startRun).mockRejectedValue(
      new ApiRequestError(409, "Production Line 'Rovema' already has an active Production Run."),
    )

    await openStartRunForm()
    fillValidForm()
    fireEvent.click(screen.getByRole('button', { name: /review run/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirm start run/i }))

    await waitFor(() =>
      expect(screen.getByText('This line already has an active run.')).toBeInTheDocument(),
    )
    expect(screen.queryByText(/production line 'rovema'/i)).not.toBeInTheDocument()
  })
})
