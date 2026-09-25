import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError } from '../../api/client'
import {
  completeChangeover,
  completeRun,
  endPlannedDowntime,
  getHmiConfig,
  getRunState,
  previewCompletion,
  reportFault,
  startChangeover,
  startPlannedDowntime,
  startRun,
  submitHourlyUpdate,
} from './api'
import { clearActiveRun, loadActiveRun, saveActiveRun } from './activeRunStorage'
import {
  beginAction,
  clearPendingAction,
  loadPendingAction,
  newIdempotencyKey,
  type PendingAction,
  type PendingActionKind,
} from './idempotency'
import { DEFAULT_PLANNED_DOWNTIME_REASONS } from './constants'
import { formatKg, parsePackWeightLabel } from './packWeight'
import { resolveCurrentShift } from './shift'
import { useLineStatePolling } from './useLineStatePolling'
import { HomeScreen, type HmiConfigState } from './screens/HomeScreen'
import { StartRunFormScreen } from './screens/StartRunFormScreen'
import { ReviewRunScreen } from './screens/ReviewRunScreen'
import { RunStartedScreen } from './screens/RunStartedScreen'
import { ActiveRunScreen } from './screens/ActiveRunScreen'
import { HourlyUpdateScreen } from './screens/HourlyUpdateScreen'
import { PlannedDowntimeScreen } from './screens/PlannedDowntimeScreen'
import { ChangeoverStartScreen } from './screens/ChangeoverStartScreen'
import { ChangeoverCompleteScreen } from './screens/ChangeoverCompleteScreen'
import { ReportToEngineerScreen } from './screens/ReportToEngineerScreen'
import { CompleteRunScreen } from './screens/CompleteRunScreen'
import { RunCompletedScreen } from './screens/RunCompletedScreen'
import { ExitRestartScreen } from './screens/ExitRestartScreen'
import { RecoverableErrorScreen } from './screens/RecoverableErrorScreen'
import {
  EMPTY_CHANGEOVER_FORM,
  EMPTY_COMPLETE_RUN_FORM,
  EMPTY_START_RUN_FORM,
  type ChangeoverFormValues,
  type CompleteRunFormValues,
  type CompletionPayload,
  type CompletionPreviewResponse,
  type FaultReportResponse,
  type HourlyUpdateResponse,
  type RunState,
  type StartRunFormValues,
  type StoredActiveRun,
} from './types'
import {
  completeRunFormErrors,
  hasStartRunFormErrors,
  validateStartRunForm,
  type StartRunFormErrors,
} from './validation'
import './hmi.css'

type Screen =
  | 'home'
  | 'startRun'
  | 'reviewRun'
  | 'runStarted'
  | 'activeRun'
  | 'hourlyUpdate'
  | 'plannedDowntime'
  | 'changeoverStart'
  | 'changeoverComplete'
  | 'reportToEngineer'
  | 'completeRun'
  | 'runCompleted'
  | 'exitRestart'
  | 'recoverableError'

const PLANNED_DOWNTIME_REASONS = DEFAULT_PLANNED_DOWNTIME_REASONS.filter(
  (reason) => reason !== 'Changeover',
)

const SCREENS_NEEDING_RUN_STATE: Screen[] = [
  'activeRun',
  'hourlyUpdate',
  'plannedDowntime',
  'changeoverStart',
  'changeoverComplete',
  'reportToEngineer',
  'completeRun',
]

function mapError(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 503 || error.status === 0) {
      return 'Pulse could not be reached. Nothing was saved - please try again.'
    }
    // 409 and 422 details are pre-written, operator-safe sentences.
    return error.message
  }
  return fallback
}

export function HmiScreen() {
  const navigate = useNavigate()

  const [screen, setScreen] = useState<Screen>('home')
  const [configState, setConfigState] = useState<HmiConfigState>({ status: 'loading' })
  // Authoritative, cross-device: which lines are already running. Never
  // inferred from this device's localStorage.
  const { lineState, refresh: refreshLineState } = useLineStatePolling()
  const [openingLine, setOpeningLine] = useState<string | null>(null)
  const [storedRun, setStoredRun] = useState<StoredActiveRun | null>(null)
  const [runState, setRunState] = useState<RunState | null>(null)
  const [isRestoring, setIsRestoring] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  const [formValues, setFormValues] = useState<StartRunFormValues>(EMPTY_START_RUN_FORM)
  const [formErrors, setFormErrors] = useState<StartRunFormErrors>({})
  const [isStartingRun, setIsStartingRun] = useState(false)
  const [startRunError, setStartRunError] = useState<string | null>(null)
  const startRunKeyRef = useRef<string | null>(null)

  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const [hourlyResult, setHourlyResult] = useState<HourlyUpdateResponse | null>(null)
  const [hourlyError, setHourlyError] = useState<string | null>(null)

  const [plannedDowntimeError, setPlannedDowntimeError] = useState<string | null>(null)

  const [changeoverForm, setChangeoverForm] = useState<ChangeoverFormValues>(EMPTY_CHANGEOVER_FORM)
  const [changeoverError, setChangeoverError] = useState<string | null>(null)

  const [faultResult, setFaultResult] = useState<FaultReportResponse | null>(null)
  const [faultError, setFaultError] = useState<string | null>(null)

  const [completeForm, setCompleteForm] = useState<CompleteRunFormValues>(EMPTY_COMPLETE_RUN_FORM)
  const [completePreview, setCompletePreview] = useState<CompletionPreviewResponse | null>(null)
  const [showCompleteErrors, setShowCompleteErrors] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [completeError, setCompleteError] = useState<string | null>(null)

  const [recoverableErrorMessage, setRecoverableErrorMessage] = useState<string | null>(null)

  function loadConfig(signal?: AbortSignal) {
    setConfigState({ status: 'loading' })
    getHmiConfig(signal)
      .then((data) => setConfigState({ status: 'ready', lines: data.lines }))
      .catch(() => setConfigState({ status: 'error' }))
  }

  /** Reads the authoritative state of the stored run. Never creates a
   * run, and never falls back to locally cached progress. */
  const refreshRunState = useCallback(
    async (runId: number, options: { background?: boolean } = {}) => {
      if (options.background) setIsRefreshing(true)
      try {
        const state = await getRunState(runId)
        setRunState(state)
        setRefreshError(null)

        if (state.run.status !== 'Active') {
          clearActiveRun()
          clearPendingAction()
          setStoredRun(null)
          setPendingAction(null)
          setRunState(null)
          setScreen('home')
        }
        return state
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 404) {
          clearActiveRun()
          clearPendingAction()
          setStoredRun(null)
          setPendingAction(null)
          setRunState(null)
          setRecoverableErrorMessage('That run no longer exists. Start a new run when ready.')
          setScreen('recoverableError')
          return null
        }
        if (options.background) {
          setRefreshError('Could not refresh from Pulse. The figures below may be out of date.')
          return null
        }
        throw error
      } finally {
        if (options.background) setIsRefreshing(false)
      }
    },
    [],
  )

  const restoreActiveRun = useCallback(
    async (stored: StoredActiveRun) => {
      setIsRestoring(true)
      try {
        const state = await refreshRunState(stored.runId)
        if (state && state.run.status === 'Active') setScreen('activeRun')
      } catch {
        setRecoverableErrorMessage(
          'Could not reach Pulse to restore the active run. The run is safe - try again.',
        )
        setScreen('recoverableError')
      } finally {
        setIsRestoring(false)
      }
    },
    [refreshRunState],
  )

  /** Opens a run this device may never have seen - the full state comes
   * from the backend, and the run is adopted locally only once that
   * read succeeds. */
  const openActiveRun = useCallback(
    async (runId: number, productionLine: string) => {
      setOpeningLine(productionLine)
      try {
        const state = await refreshRunState(runId)
        if (!state || state.run.status !== 'Active') {
          await refreshLineState()
          return
        }
        const stored: StoredActiveRun = { runId, productionLine }
        saveActiveRun(stored)
        setStoredRun(stored)
        setPendingAction(loadPendingAction())
        setScreen('activeRun')
      } catch {
        setRecoverableErrorMessage(
          'Could not reach Pulse to open that run. The run is safe - try again.',
        )
        setScreen('recoverableError')
      } finally {
        setOpeningLine(null)
      }
    },
    [refreshRunState, refreshLineState],
  )

  useEffect(() => {
    const controller = new AbortController()
    loadConfig(controller.signal)

    const stored = loadActiveRun()
    if (stored) {
      setStoredRun(stored)
      setPendingAction(loadPendingAction())
      void restoreActiveRun(stored)
    }

    return () => controller.abort()
  }, [restoreActiveRun])

  // ------------------------------------------------------------
  // Idempotent writes
  // ------------------------------------------------------------

  async function runWrite<T>(
    kind: PendingActionKind,
    label: string,
    payload: unknown,
    call: (key: string) => Promise<T>,
  ): Promise<T> {
    if (!storedRun) throw new Error('No active run')

    const action = beginAction(pendingAction, kind, storedRun.runId, label, payload)
    setPendingAction(action)
    setIsSubmitting(true)

    try {
      const result = await call(action.key)
      clearPendingAction()
      setPendingAction(null)
      return result
    } finally {
      setIsSubmitting(false)
    }
  }

  function cancelPending() {
    clearPendingAction()
    setPendingAction(null)
  }

  // ------------------------------------------------------------
  // Home / Start Run
  // ------------------------------------------------------------

  function handleStartRunFromHome(lineName: string) {
    setFormValues({
      ...EMPTY_START_RUN_FORM,
      productionLine: lineName,
      shift: resolveCurrentShift().name,
    })
    setFormErrors({})
    setStartRunError(null)
    startRunKeyRef.current = null
    setScreen('startRun')
  }

  function handleFormChange(field: keyof StartRunFormValues, value: string) {
    setFormValues((prev) => {
      const next = { ...prev, [field]: value }

      // Auto-fill the calculation field from a valid label, so the two
      // stay in sync by default. The operator can still edit "Pack
      // weight (kg)" afterwards - validation always checks the final
      // combination at Review time regardless of how it got there.
      if (field === 'packWeightLabel') {
        const convertedKg = parsePackWeightLabel(value)
        if (convertedKg !== null) {
          next.packWeightKg = formatKg(convertedKg)
        }
      }

      return next
    })
  }

  function handleReview() {
    const errors = validateStartRunForm(formValues)
    setFormErrors(errors)
    if (!hasStartRunFormErrors(errors)) {
      setStartRunError(null)
      setScreen('reviewRun')
    }
  }

  function handleClearForm() {
    setFormValues({
      ...EMPTY_START_RUN_FORM,
      productionLine: formValues.productionLine,
      shift: resolveCurrentShift().name,
    })
    setFormErrors({})
  }

  function handleConfirmStartRun() {
    if (isStartingRun) return
    setIsStartingRun(true)
    setStartRunError(null)

    // The same key for every retry of THIS Start Run, so a timeout
    // retry returns the original run instead of a duplicate or a
    // misleading "line already active".
    startRunKeyRef.current = startRunKeyRef.current ?? newIdempotencyKey()

    startRun(
      {
        production_line: formValues.productionLine,
        line_technician: formValues.lineTechnician,
        shift: formValues.shift,
        customer: formValues.customer,
        product: formValues.product,
        pack_weight: formValues.packWeightLabel,
        pack_weight_kg: Number(formValues.packWeightKg),
        packs_per_case: Number(formValues.packsPerCase),
        pack_type: formValues.packType,
        target_speed_ppm: Number(formValues.targetSpeedPpm),
        cases_per_pallet: Number(formValues.casesPerPallet),
        pallets_remaining: Number(formValues.palletsRemaining),
        previous_run_completed: Number(formValues.previousRunCompleted || '0'),
      },
      startRunKeyRef.current,
    )
      .then(async (response) => {
        const stored: StoredActiveRun = {
          runId: response.run_id,
          productionLine: response.production_line,
        }
        saveActiveRun(stored)
        setStoredRun(stored)
        startRunKeyRef.current = null
        await refreshRunState(stored.runId).catch(() => null)
        setScreen('runStarted')
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.status === 409) {
          // The database constraint is the final authority: Home's line
          // state can only ever be a moment out of date, so a race is
          // still possible and is settled here. Re-read the real state
          // so Home immediately shows the line as running.
          setStartRunError(
            'Another device started a run on this line first. Nothing was saved here. ' +
              'Go back to Home and open the active run.',
          )
          void refreshLineState()
          return
        }
        setStartRunError(mapError(error, 'Could not start the run. Please try again.'))
      })
      .finally(() => setIsStartingRun(false))
  }

  // ------------------------------------------------------------
  // Hourly update
  // ------------------------------------------------------------

  function submitHourly(palletsProduced: string) {
    if (!storedRun || !runState || isSubmitting) return
    setHourlyError(null)

    runWrite(
      'hourlyUpdate',
      `An hourly update of ${palletsProduced} pallets`,
      { palletsProduced },
      (key) =>
        submitHourlyUpdate(
          storedRun.runId,
          {
            line_technician: runState.run.line_technician,
            pallets_produced: palletsProduced,
          },
          key,
        ),
    )
      .then(async (result) => {
        // Only now does the progress display change - it is refreshed
        // from the server, never incremented locally.
        setHourlyResult(result)
        await refreshRunState(storedRun.runId, { background: true })
      })
      .catch((error: unknown) =>
        setHourlyError(mapError(error, 'Could not save the update. Please try again.')),
      )
  }

  // ------------------------------------------------------------
  // Planned downtime
  // ------------------------------------------------------------

  function beginPlannedDowntime(reason: string) {
    if (!storedRun || !runState || isSubmitting) return
    setPlannedDowntimeError(null)

    runWrite('plannedDowntimeStart', `Starting ${reason} planned downtime`, { reason }, (key) =>
      startPlannedDowntime(
        storedRun.runId,
        { reason, started_by: runState.run.line_technician },
        key,
      ),
    )
      .then(() => refreshRunState(storedRun.runId, { background: true }))
      .catch((error: unknown) =>
        setPlannedDowntimeError(
          mapError(error, 'Could not start planned downtime. Please try again.'),
        ),
      )
  }

  function finishPlannedDowntime() {
    if (!storedRun || !runState?.open_planned_downtime || isSubmitting) return
    const event = runState.open_planned_downtime
    setPlannedDowntimeError(null)

    runWrite(
      'plannedDowntimeEnd',
      `Ending ${event.reason} planned downtime`,
      { id: event.planned_downtime_id },
      (key) =>
        endPlannedDowntime(
          event.planned_downtime_id,
          { ended_by: runState.run.line_technician },
          key,
        ),
    )
      .then(async () => {
        await refreshRunState(storedRun.runId, { background: true })
        setScreen('activeRun')
      })
      .catch((error: unknown) =>
        setPlannedDowntimeError(
          mapError(error, 'Could not end planned downtime. Please try again.'),
        ),
      )
  }

  // ------------------------------------------------------------
  // Changeover
  // ------------------------------------------------------------

  function beginChangeover() {
    if (!storedRun || !runState || isSubmitting) return
    setChangeoverError(null)

    const payload = {
      line_technician: runState.run.line_technician,
      new_customer: changeoverForm.newCustomer.trim(),
      new_product: changeoverForm.newProduct.trim(),
      new_pack_weight_kg: changeoverForm.newPackWeightKg.trim(),
      new_format: changeoverForm.newFormat.trim(),
      note: changeoverForm.note.trim() || null,
    }

    runWrite('changeoverStart', 'Starting the changeover', payload, (key) =>
      startChangeover(storedRun.runId, payload, key),
    )
      .then(async () => {
        setChangeoverForm(EMPTY_CHANGEOVER_FORM)
        await refreshRunState(storedRun.runId, { background: true })
        setScreen('activeRun')
      })
      .catch((error: unknown) =>
        setChangeoverError(mapError(error, 'Could not start the changeover. Please try again.')),
      )
  }

  function finishChangeover() {
    if (!storedRun || !runState?.open_changeover || isSubmitting) return
    const changeover = runState.open_changeover
    setChangeoverError(null)

    runWrite(
      'changeoverComplete',
      'Completing the changeover',
      { id: changeover.changeover_id },
      (key) =>
        completeChangeover(
          changeover.changeover_id,
          {
            completed_by: runState.run.line_technician,
            first_acceptable_packs_confirmed: true,
          },
          key,
        ),
    )
      .then(async () => {
        await refreshRunState(storedRun.runId, { background: true })
        setScreen('activeRun')
      })
      .catch((error: unknown) =>
        setChangeoverError(mapError(error, 'Could not complete the changeover. Please try again.')),
      )
  }

  // ------------------------------------------------------------
  // Report to Engineer
  // ------------------------------------------------------------

  function submitFaultReport(input: {
    machine: string
    machineId: number | null
    buttonId: number | null
    reason: string
    note: string
  }) {
    if (!storedRun || !runState || isSubmitting) return
    setFaultError(null)

    const payload = {
      reported_by: runState.run.line_technician,
      machine: input.machine,
      reason: input.reason,
      machine_id: input.machineId,
      button_id: input.buttonId,
      note: input.note || null,
    }

    runWrite('faultReport', `Reporting ${input.reason} on ${input.machine}`, payload, (key) =>
      reportFault(storedRun.runId, payload, key),
    )
      .then(async (result) => {
        setFaultResult(result)
        await refreshRunState(storedRun.runId, { background: true })
      })
      .catch((error: unknown) =>
        setFaultError(mapError(error, 'Could not report the fault. Please try again.')),
      )
  }

  // ------------------------------------------------------------
  // Complete Run
  // ------------------------------------------------------------

  function completionPayload(): CompletionPayload | null {
    if (!runState) return null

    const productionMade = completeForm.productionSinceLastUpdate === 'yes'

    return {
      line_technician: runState.run.line_technician,
      production_since_last_update: productionMade,
      final_pallets_produced: productionMade ? completeForm.finalPallets.trim() : null,
      count_unavailable: completeForm.countUnavailable,
      xray_pack_count: completeForm.countUnavailable
        ? null
        : Number(completeForm.xrayPackCount.trim()),
      unavailable_reason: completeForm.countUnavailable
        ? completeForm.unavailableReason.trim()
        : null,
    }
  }

  function reviewCompletion() {
    if (!storedRun || isPreviewing) return

    setShowCompleteErrors(true)
    if (Object.keys(completeRunFormErrors(completeForm)).length > 0) return

    const payload = completionPayload()
    if (!payload) return

    setIsPreviewing(true)
    setCompleteError(null)

    previewCompletion(storedRun.runId, payload)
      .then(setCompletePreview)
      .catch((error: unknown) =>
        setCompleteError(mapError(error, 'Could not check these figures. Please try again.')),
      )
      .finally(() => setIsPreviewing(false))
  }

  function confirmCompleteRun() {
    if (!storedRun || isSubmitting) return
    const payload = completionPayload()
    if (!payload) return

    setCompleteError(null)

    runWrite('completeRun', 'Completing the run', payload, (key) =>
      completeRun(storedRun.runId, payload, key),
    )
      .then(() => {
        clearActiveRun()
        setStoredRun(null)
        setRunState(null)
        setCompleteForm(EMPTY_COMPLETE_RUN_FORM)
        setCompletePreview(null)
        setScreen('runCompleted')
      })
      .catch((error: unknown) =>
        setCompleteError(mapError(error, 'Could not complete the run. Please try again.')),
      )
  }

  // ------------------------------------------------------------
  // Unconfirmed action recovery
  // ------------------------------------------------------------

  function resolvePendingAction() {
    if (!pendingAction) return

    switch (pendingAction.kind) {
      case 'hourlyUpdate':
        setHourlyResult(null)
        setHourlyError(null)
        setScreen('hourlyUpdate')
        break
      case 'plannedDowntimeStart':
      case 'plannedDowntimeEnd':
        setScreen('plannedDowntime')
        break
      case 'changeoverStart':
        setScreen('changeoverStart')
        break
      case 'changeoverComplete':
        setScreen('changeoverComplete')
        break
      case 'faultReport':
        setFaultResult(null)
        setFaultError(null)
        setScreen('reportToEngineer')
        break
      case 'completeRun':
        setCompletePreview(null)
        setScreen('completeRun')
        break
    }
  }

  // ------------------------------------------------------------
  // Exit
  // ------------------------------------------------------------

  function handleConfirmExit() {
    clearActiveRun()
    clearPendingAction()
    setStoredRun(null)
    setRunState(null)
    setPendingAction(null)
    setScreen('home')
  }

  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------

  if (SCREENS_NEEDING_RUN_STATE.includes(screen) && !runState) {
    return (
      <div className="hmi-screen" role="status">
        <p>{isRestoring ? 'Restoring the active run…' : 'Loading…'}</p>
      </div>
    )
  }

  switch (screen) {
    case 'home':
      return (
        <HomeScreen
          configState={configState}
          lineState={lineState}
          activeRun={storedRun}
          isRestoring={isRestoring}
          openingLine={openingLine}
          onRetry={() => loadConfig()}
          onRetryLineState={() => void refreshLineState()}
          onStartRun={handleStartRunFromHome}
          onOpenActiveRun={(runId, lineName) => void openActiveRun(runId, lineName)}
          onEngineering={() => navigate('/engineering')}
          onManagement={() => navigate('/management')}
        />
      )

    case 'startRun':
      return (
        <StartRunFormScreen
          values={formValues}
          errors={formErrors}
          onChange={handleFormChange}
          onBack={() => setScreen('home')}
          onClear={handleClearForm}
          onReview={handleReview}
        />
      )

    case 'reviewRun':
      return (
        <ReviewRunScreen
          values={formValues}
          isSubmitting={isStartingRun}
          errorMessage={startRunError}
          onBack={() => setScreen('startRun')}
          onConfirm={handleConfirmStartRun}
        />
      )

    case 'runStarted':
      return <RunStartedScreen values={formValues} onContinue={() => setScreen('activeRun')} />

    case 'activeRun':
      return (
        <ActiveRunScreen
          state={runState!}
          isRefreshing={isRefreshing}
          refreshError={refreshError}
          pendingAction={pendingAction}
          onRefresh={() => storedRun && refreshRunState(storedRun.runId, { background: true })}
          onResolvePending={resolvePendingAction}
          onDiscardPending={cancelPending}
          onHourlyUpdate={() => {
            setHourlyResult(null)
            setHourlyError(null)
            setScreen('hourlyUpdate')
          }}
          onPlannedDowntime={() => {
            setPlannedDowntimeError(null)
            setScreen(runState!.open_changeover ? 'changeoverComplete' : 'plannedDowntime')
          }}
          onReportToEngineer={() => {
            setFaultResult(null)
            setFaultError(null)
            setScreen('reportToEngineer')
          }}
          onCompleteRun={() => {
            setCompleteError(null)
            setCompletePreview(null)
            setShowCompleteErrors(false)
            setScreen('completeRun')
          }}
          onExitRestart={() => setScreen('exitRestart')}
        />
      )

    case 'hourlyUpdate':
      return (
        <HourlyUpdateScreen
          state={runState!}
          isSubmitting={isSubmitting}
          result={hourlyResult}
          errorMessage={hourlyError}
          onCancel={() => {
            cancelPending()
            setScreen('activeRun')
          }}
          onSubmit={submitHourly}
          onDone={() => {
            setHourlyResult(null)
            setScreen('activeRun')
          }}
        />
      )

    case 'plannedDowntime':
      return (
        <PlannedDowntimeScreen
          reasons={[...PLANNED_DOWNTIME_REASONS]}
          activeEvent={runState!.open_planned_downtime}
          isSubmitting={isSubmitting}
          errorMessage={plannedDowntimeError}
          onStart={beginPlannedDowntime}
          onEnd={finishPlannedDowntime}
          onStartChangeover={() => {
            setChangeoverError(null)
            setScreen('changeoverStart')
          }}
          onCancel={() => setScreen('activeRun')}
        />
      )

    case 'changeoverStart':
      return (
        <ChangeoverStartScreen
          state={runState!}
          values={changeoverForm}
          isSubmitting={isSubmitting}
          errorMessage={changeoverError}
          onChange={(field, value) => setChangeoverForm((prev) => ({ ...prev, [field]: value }))}
          onCancel={() => setScreen('plannedDowntime')}
          onStart={beginChangeover}
        />
      )

    case 'changeoverComplete':
      if (!runState!.open_changeover) {
        setScreen('activeRun')
        return null
      }
      return (
        <ChangeoverCompleteScreen
          changeover={runState!.open_changeover}
          isSubmitting={isSubmitting}
          errorMessage={changeoverError}
          onCancel={() => setScreen('activeRun')}
          onComplete={finishChangeover}
        />
      )

    case 'reportToEngineer': {
      const configLine =
        configState.status === 'ready'
          ? configState.lines.find((line) => line.name === runState!.run.production_line)
          : undefined
      return (
        <ReportToEngineerScreen
          productionLine={runState!.run.production_line}
          machines={configLine?.machines ?? []}
          isSubmitting={isSubmitting}
          result={faultResult}
          errorMessage={faultError}
          onSubmit={submitFaultReport}
          onCancel={() => {
            cancelPending()
            setScreen('activeRun')
          }}
          onDone={() => {
            setFaultResult(null)
            setScreen('activeRun')
          }}
        />
      )
    }

    case 'completeRun':
      return (
        <CompleteRunScreen
          state={runState!}
          values={completeForm}
          preview={completePreview}
          isPreviewing={isPreviewing}
          isSubmitting={isSubmitting}
          errorMessage={completeError}
          showErrors={showCompleteErrors}
          onChange={(field, value) => setCompleteForm((prev) => ({ ...prev, [field]: value }))}
          onCancel={() => {
            cancelPending()
            setScreen('activeRun')
          }}
          onReview={reviewCompletion}
          onBackToEdit={() => setCompletePreview(null)}
          onConfirm={confirmCompleteRun}
        />
      )

    case 'runCompleted':
      return (
        <RunCompletedScreen
          productionLine={formValues.productionLine || ''}
          onBackToHome={() => setScreen('home')}
        />
      )

    case 'exitRestart':
      return (
        <ExitRestartScreen
          productionLine={storedRun?.productionLine ?? ''}
          onCancel={() => setScreen('activeRun')}
          onConfirmExit={handleConfirmExit}
        />
      )

    case 'recoverableError':
      return (
        <RecoverableErrorScreen
          message={recoverableErrorMessage ?? 'Something went wrong.'}
          onRetry={() => {
            setRecoverableErrorMessage(null)
            const stored = loadActiveRun()
            if (stored) {
              setStoredRun(stored)
              void restoreActiveRun(stored)
            } else {
              setScreen('home')
              loadConfig()
            }
          }}
          onBackToHome={() => {
            setRecoverableErrorMessage(null)
            setScreen('home')
          }}
        />
      )

    default:
      return null
  }
}
