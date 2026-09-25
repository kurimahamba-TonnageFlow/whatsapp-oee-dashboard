import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HmiScreen } from './HmiScreen'
import * as hmiApi from './api'
import { ApiRequestError } from '../../api/client'
import { saveActiveRun } from './activeRunStorage'
import { HMI_CONFIG, runState } from './hmiTestState'
import type { CompleteRunResponse, CompletionPreviewResponse } from './types'

vi.mock('./api')

const MOCKED = ['getHmiConfig', 'getRunState', 'previewCompletion', 'completeRun'] as const

afterEach(() => {
  MOCKED.forEach((name) => vi.mocked(hmiApi[name]).mockReset())
  window.localStorage.clear()
})

beforeEach(() => {
  vi.mocked(hmiApi.getHmiConfig).mockResolvedValue(HMI_CONFIG)
})

function preview(overrides: Partial<CompletionPreviewResponse> = {}): CompletionPreviewResponse {
  return {
    production_run_id: 99,
    production_line: 'Rovema',
    total_pallets_recorded: 11.75,
    final_pallets_produced: 1.25,
    palletised_pallets: 10,
    palletised_packs: 17600,
    count_available: true,
    xray_pack_count: 18000,
    post_xray_pack_difference: 400,
    estimated_post_xray_waste_percent: 2.2,
    waste_status: 'estimated',
    waste_unavailable_reason: null,
    data_quality_warning: null,
    calculation_status: 'estimated',
    method: 'Estimated post-X-ray waste ... does not include rejects removed before the X-ray.',
    can_complete: true,
    blocking_reason: null,
    saved: false,
    ...overrides,
  }
}

/** X-ray count below the palletised packs already confirmed - physically
 * impossible, so completion is refused. */
function inconsistentPreview(): CompletionPreviewResponse {
  const warning =
    'The X-ray pack count (17000) is lower than the palletised packs already confirmed ' +
    '(17600), a shortfall of 600 packs. Packs are counted by the X-ray before they are ' +
    'palletised, so this cannot happen: either the X-ray count or a pallet figure is wrong. ' +
    'No waste figure has been calculated.'

  return preview({
    xray_pack_count: 17000,
    post_xray_pack_difference: -600,
    estimated_post_xray_waste_percent: null,
    waste_status: 'data_quality_warning',
    data_quality_warning: warning,
    calculation_status: 'unavailable',
    can_complete: false,
    blocking_reason: warning,
  })
}

function completeResponse(): CompleteRunResponse {
  return {
    status: 'success',
    message: 'Run completed',
    run_id: 99,
    production_line: 'Rovema',
    run_status: 'Completed',
    xray: {
      xray_capture_id: 8,
      capture_point: 'run_completion',
      production_run_id: 99,
      production_line: 'Rovema',
      shift: 'Day',
      captured_at: '2026-01-12T14:00:00+00:00',
      final_hourly_update_id: 90,
      final_pallets_produced: 1.25,
      total_pallets_recorded: 11.75,
      count_available: true,
      xray_pack_count: 18000,
      unavailable_reason: null,
      palletised_pallets: 10,
      palletised_packs: 17600,
      post_xray_pack_difference: 400,
      estimated_post_xray_waste_percent: 2.2,
      waste_status: 'estimated',
      waste_unavailable_reason: null,
      data_quality_warning: null,
      calculation_status: 'estimated',
      method: 'Estimated post-X-ray waste ...',
    },
  }
}

async function openCompleteRun() {
  saveActiveRun({ runId: 99, productionLine: 'Rovema' })
  vi.mocked(hmiApi.getRunState).mockResolvedValue(runState())

  render(
    <MemoryRouter initialEntries={['/hmi']}>
      <Routes>
        <Route path="/hmi" element={<HmiScreen />} />
      </Routes>
    </MemoryRouter>,
  )

  await waitFor(() => expect(screen.getByRole('heading', { name: 'Rovema' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: /complete run/i }))
}

function answerNoFinalProduction() {
  fireEvent.click(screen.getByRole('radio', { name: 'No' }))
}

describe('Complete Run', () => {
  it('asks about final production before anything else', async () => {
    await openCompleteRun()

    expect(
      screen.getByText(/has any production been made since the last saved hourly update/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Yes' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'No' })).not.toBeChecked()
    expect(screen.queryByLabelText(/final pallets produced/i)).not.toBeInTheDocument()
  })

  it('will not review until the question is answered', async () => {
    await openCompleteRun()

    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    expect(
      await screen.findByText(/answer whether anything has been produced/i),
    ).toBeInTheDocument()
    expect(hmiApi.previewCompletion).not.toHaveBeenCalled()
  })

  it('completes with no final production', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(
      preview({ final_pallets_produced: 0, total_pallets_recorded: 10.5 }),
    )
    vi.mocked(hmiApi.completeRun).mockResolvedValue(completeResponse())
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )
    expect(vi.mocked(hmiApi.previewCompletion).mock.calls[0][1]).toEqual({
      line_technician: 'Liam',
      production_since_last_update: false,
      final_pallets_produced: null,
      count_unavailable: false,
      xray_pack_count: 18000,
      unavailable_reason: null,
    })

    fireEvent.click(screen.getByRole('button', { name: /confirm complete run/i }))
    await waitFor(() => expect(screen.getByText('✓ RUN COMPLETED')).toBeInTheDocument())
  })

  it('sends decimal final production as an exact string', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(preview())
    await openCompleteRun()

    fireEvent.click(screen.getByRole('radio', { name: 'Yes' }))
    fireEvent.change(screen.getByLabelText(/final pallets produced/i), {
      target: { value: '1.25' },
    })
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    await waitFor(() => expect(hmiApi.previewCompletion).toHaveBeenCalled())
    expect(vi.mocked(hmiApi.previewCompletion).mock.calls[0][1].final_pallets_produced).toBe('1.25')
  })

  it.each(['0', '-2', 'abc'])('rejects an invalid final production value (%s)', async (value) => {
    await openCompleteRun()

    fireEvent.click(screen.getByRole('radio', { name: 'Yes' }))
    fireEvent.change(screen.getByLabelText(/final pallets produced/i), { target: { value } })
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(hmiApi.previewCompletion).not.toHaveBeenCalled()
  })

  it.each(['', '-1', '12.5'])('rejects an invalid X-ray count (%s)', async (value) => {
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(hmiApi.previewCompletion).not.toHaveBeenCalled()
  })

  it('requires a reason when the count is unavailable', async () => {
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.click(screen.getByLabelText(/count unavailable/i))
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    expect(
      await screen.findByText(/give a reason why the x-ray count is unavailable/i),
    ).toBeInTheDocument()
    expect(hmiApi.previewCompletion).not.toHaveBeenCalled()
  })

  it('completes with the count unavailable and a reason, and calculates no waste', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(
      preview({
        count_available: false,
        xray_pack_count: null,
        post_xray_pack_difference: null,
        estimated_post_xray_waste_percent: null,
        waste_status: 'unavailable',
        waste_unavailable_reason: 'X-ray count unavailable - no waste figure is calculated.',
        calculation_status: 'unavailable',
      }),
    )
    vi.mocked(hmiApi.completeRun).mockResolvedValue(completeResponse())
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.click(screen.getByLabelText(/count unavailable/i))
    fireEvent.change(screen.getByLabelText(/why is the x-ray count unavailable/i), {
      target: { value: 'Counter reset mid-shift' },
    })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )
    expect(screen.getByText('Count unavailable')).toBeInTheDocument()
    expect(screen.getByText(/no waste figure is calculated/i)).toBeInTheDocument()
    expect(vi.mocked(hmiApi.previewCompletion).mock.calls[0][1]).toMatchObject({
      count_unavailable: true,
      xray_pack_count: null,
      unavailable_reason: 'Counter reset mid-shift',
    })
  })

  it('shows the backend summary with an estimated label', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(preview())
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )
    expect(screen.getByText('11.75')).toBeInTheDocument()
    expect(screen.getByText('17600')).toBeInTheDocument()
    expect(screen.getByText('18000')).toBeInTheDocument()
    expect(screen.getByText('400')).toBeInTheDocument()
    expect(screen.getByText('2.2%')).toBeInTheDocument()
    // The figure itself carries the "(estimated)" label; the method line
    // explains how it was derived without repeating the word twice.
    expect(screen.getByText(/post-x-ray waste \(estimated\)/i)).toBeInTheDocument()
    expect(
      screen.getByText(/how this is calculated: estimated post-x-ray waste/i),
    ).toBeInTheDocument()
  })

  it('shows the data-quality warning when palletised output exceeds the X-ray count', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(
      preview({
        xray_pack_count: 17000,
        post_xray_pack_difference: -600,
        estimated_post_xray_waste_percent: null,
        waste_status: 'data_quality_warning',
        data_quality_warning: 'Palletised packs exceed the X-ray pack count.',
        calculation_status: 'unavailable',
      }),
    )
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '17000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))

    await waitFor(() =>
      expect(screen.getByText(/palletised packs exceed the x-ray pack count/i)).toBeInTheDocument(),
    )
    expect(screen.getByText('-600')).toBeInTheDocument()
    // Not silently forced to zero.
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
  })

  it('a double tap on confirm completes the run once', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(preview())
    let resolve: (value: CompleteRunResponse) => void = () => {}
    vi.mocked(hmiApi.completeRun).mockReturnValue(
      new Promise<CompleteRunResponse>((r) => {
        resolve = r
      }),
    )
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )

    const confirm = screen.getByRole('button', { name: /confirm complete run/i })
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(hmiApi.completeRun).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolve(completeResponse())
      await Promise.resolve()
    })
  })

  it('a failed completion keeps the review and does not close the run', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(preview())
    vi.mocked(hmiApi.completeRun).mockRejectedValue(new ApiRequestError(503, 'down'))
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByRole('button', { name: /confirm complete run/i }))

    await waitFor(() => expect(screen.getByText(/nothing was saved/i)).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument()
    expect(screen.queryByText('✓ RUN COMPLETED')).not.toBeInTheDocument()
    expect(window.localStorage.getItem('pulse.hmi.activeRun.v2')).not.toBeNull()
  })

  it('a successful completion clears the run from this tablet', async () => {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(preview())
    vi.mocked(hmiApi.completeRun).mockResolvedValue(completeResponse())
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: '18000' } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByRole('button', { name: /confirm complete run/i }))

    await waitFor(() => expect(screen.getByText('✓ RUN COMPLETED')).toBeInTheDocument())
    const [runId, payload, key] = vi.mocked(hmiApi.completeRun).mock.calls[0]
    expect(runId).toBe(99)
    expect(payload.xray_pack_count).toBe(18000)
    expect(key).toBeTruthy()
    expect(window.localStorage.getItem('pulse.hmi.activeRun.v2')).toBeNull()
  })

  // --------------------------------------------------------
  // Inconsistent X-ray figures block completion
  // --------------------------------------------------------

  async function reviewWith(previewResponse: CompletionPreviewResponse, xray = '17000') {
    vi.mocked(hmiApi.previewCompletion).mockResolvedValue(previewResponse)
    await openCompleteRun()

    answerNoFinalProduction()
    fireEvent.change(screen.getByLabelText(/x-ray pack count/i), { target: { value: xray } })
    fireEvent.click(screen.getByRole('button', { name: /review/i }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /complete run — review/i })).toBeInTheDocument(),
    )
  }

  it('refuses to complete when the X-ray count is below the palletised packs', async () => {
    await reviewWith(inconsistentPreview())

    expect(screen.getByRole('button', { name: /confirm complete run/i })).toBeDisabled()
    expect(screen.getByText(/the run cannot be completed with these figures/i)).toBeInTheDocument()
    expect(hmiApi.completeRun).not.toHaveBeenCalled()
  })

  it('explains the shortfall and shows both recorded figures', async () => {
    await reviewWith(inconsistentPreview())

    expect(screen.getByText(/is lower than the palletised packs already confirmed/i)).toBeInTheDocument()
    // Both figures stay on screen so the operator can see which to correct.
    expect(screen.getByText('17000')).toBeInTheDocument()
    expect(screen.getByText('17600')).toBeInTheDocument()
  })

  it('shows the shortfall signed, never as ordinary waste', async () => {
    await reviewWith(inconsistentPreview())

    expect(screen.getByText('-600')).toBeInTheDocument()
    expect(screen.queryByText('600')).not.toBeInTheDocument()
    // No percentage is offered at all.
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument()
  })

  it('lets the operator go back and correct the figures', async () => {
    await reviewWith(inconsistentPreview())

    fireEvent.click(screen.getByRole('button', { name: /^back$/i }))

    // Back on the form, with the entered count still there to correct.
    expect(screen.getByLabelText(/x-ray pack count/i)).toHaveValue('17000')
    expect(hmiApi.completeRun).not.toHaveBeenCalled()
  })

  it('allows completion once the figures are consistent', async () => {
    await reviewWith(preview(), '18000')

    expect(screen.getByRole('button', { name: /confirm complete run/i })).toBeEnabled()
    expect(screen.queryByText(/cannot be completed with these figures/i)).not.toBeInTheDocument()
  })

  it('reports the difference as X-ray minus palletised packs', async () => {
    await reviewWith(preview(), '18000')

    // 18000 X-ray - 17600 palletised = +400 packs, 2.2% of the X-ray count.
    expect(screen.getByText('400')).toBeInTheDocument()
    expect(screen.getByText('2.2%')).toBeInTheDocument()
  })
})
