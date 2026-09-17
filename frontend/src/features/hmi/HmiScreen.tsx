import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError } from '../../api/client'
import { completeRun, getHmiConfig, startRun } from './api'
import {
  endPlannedDowntime,
  reportFaultToEngineer,
  startPlannedDowntime,
  submitHourlyUpdate,
  type EngineerReportResult,
  type HourlyUpdateResult,
  type PlannedDowntimeEvent,
} from './awaitingApiIntegration'
import { clearActiveRun, loadActiveRun, saveActiveRun } from './activeRunStorage'
import { DEFAULT_PLANNED_DOWNTIME_REASONS } from './constants'
import { formatKg, parsePackWeightLabel } from './packWeight'
import { resolveCurrentShift } from './shift'
import { HomeScreen, type HmiConfigState } from './screens/HomeScreen'
import { StartRunFormScreen } from './screens/StartRunFormScreen'
import { ReviewRunScreen } from './screens/ReviewRunScreen'
import { RunStartedScreen } from './screens/RunStartedScreen'
import { ActiveRunScreen } from './screens/ActiveRunScreen'
import { HourlyUpdateScreen } from './screens/HourlyUpdateScreen'
import { PlannedDowntimeScreen } from './screens/PlannedDowntimeScreen'
import { ReportToEngineerScreen } from './screens/ReportToEngineerScreen'
import { CompleteRunScreen } from './screens/CompleteRunScreen'
import { RunCompletedScreen } from './screens/RunCompletedScreen'
import { ExitRestartScreen } from './screens/ExitRestartScreen'
import { RecoverableErrorScreen } from './screens/RecoverableErrorScreen'
import { EMPTY_START_RUN_FORM, type ActiveRunRecord, type StartRunFormValues } from './types'
import { hasStartRunFormErrors, validateStartRunForm, type StartRunFormErrors } from './validation'
import './hmi.css'

type Screen =
  | 'home'
  | 'startRun'
  | 'reviewRun'
  | 'runStarted'
  | 'activeRun'
  | 'hourlyUpdate'
  | 'plannedDowntime'
  | 'reportToEngineer'
  | 'completeRun'
  | 'runCompleted'
  | 'exitRestart'
  | 'recoverableError'

function mapStartRunError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 409) return 'This line already has an active run.'
    return error.message
  }
  return 'Could not start the run. Please try again.'
}

function mapCompleteRunError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 404) return 'This run could not be found.'
    if (error.status === 409) return 'This run has already been completed.'
    if (error.status === 503) return 'The system is temporarily unavailable. Please try again.'
    return error.message
  }
  return 'Could not complete the run. Please try again.'
}

export function HmiScreen() {
  const navigate = useNavigate()

  const [screen, setScreen] = useState<Screen>('home')
  const [configState, setConfigState] = useState<HmiConfigState>({ status: 'loading' })
  const [activeRun, setActiveRun] = useState<ActiveRunRecord | null>(null)

  const [formValues, setFormValues] = useState<StartRunFormValues>(EMPTY_START_RUN_FORM)
  const [formErrors, setFormErrors] = useState<StartRunFormErrors>({})
  const [isStartingRun, setIsStartingRun] = useState(false)
  const [startRunError, setStartRunError] = useState<string | null>(null)

  const [isCompletingRun, setIsCompletingRun] = useState(false)
  const [completeRunError, setCompleteRunError] = useState<string | null>(null)

  const [hourlyUpdateResult, setHourlyUpdateResult] = useState<HourlyUpdateResult | null>(null)
  const [isSubmittingHourlyUpdate, setIsSubmittingHourlyUpdate] = useState(false)
  const [hourlyUpdateError, setHourlyUpdateError] = useState<string | null>(null)

  const [plannedDowntimeEvent, setPlannedDowntimeEvent] = useState<PlannedDowntimeEvent | null>(
    null,
  )
  const [isSubmittingPlannedDowntime, setIsSubmittingPlannedDowntime] = useState(false)

  const [engineerReportResult, setEngineerReportResult] = useState<EngineerReportResult | null>(
    null,
  )
  const [isSubmittingEngineerReport, setIsSubmittingEngineerReport] = useState(false)
  const [engineerReportError, setEngineerReportError] = useState<string | null>(null)

  const [recoverableErrorMessage, setRecoverableErrorMessage] = useState<string | null>(null)

  function loadConfig(signal?: AbortSignal) {
    setConfigState({ status: 'loading' })
    getHmiConfig(signal)
      .then((data) => setConfigState({ status: 'ready', lines: data.lines }))
      .catch(() => setConfigState({ status: 'error' }))
  }

  useEffect(() => {
    const controller = new AbortController()
    loadConfig(controller.signal)

    const restored = loadActiveRun()
    if (restored) {
      setActiveRun(restored)
      setScreen('activeRun')
    }

    return () => controller.abort()
  }, [])

  // ------------------------------------------------------------
  // Home
  // ------------------------------------------------------------

  function handleStartRunFromHome(lineName: string) {
    setFormValues({
      ...EMPTY_START_RUN_FORM,
      productionLine: lineName,
      shift: resolveCurrentShift().name,
    })
    setFormErrors({})
    setStartRunError(null)
    setScreen('startRun')
  }

  // ------------------------------------------------------------
  // Start Run form -> Review -> Confirm
  // ------------------------------------------------------------

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

    startRun({
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
    })
      .then((response) => {
        const record: ActiveRunRecord = {
          runId: response.run_id,
          startedAtIso: new Date().toISOString(),
          form: formValues,
          totalPalletsCompleted: Number(formValues.previousRunCompleted || '0'),
          plannedDowntimeMinutes: 0,
          unplannedDowntimeMinutes: 0,
        }
        saveActiveRun(record)
        setActiveRun(record)
        setScreen('runStarted')
      })
      .catch((error: unknown) => setStartRunError(mapStartRunError(error)))
      .finally(() => setIsStartingRun(false))
  }

  // ------------------------------------------------------------
  // Active run workflows
  // ------------------------------------------------------------

  function handleHourlyUpdateSubmit(palletsProducedThisPeriod: number) {
    if (!activeRun || isSubmittingHourlyUpdate) return
    setIsSubmittingHourlyUpdate(true)
    setHourlyUpdateError(null)

    submitHourlyUpdate(activeRun.form, activeRun.totalPalletsCompleted, {
      palletsProducedThisPeriod,
    })
      .then((result) => {
        const updated: ActiveRunRecord = { ...activeRun, totalPalletsCompleted: result.newTotal }
        saveActiveRun(updated)
        setActiveRun(updated)
        setHourlyUpdateResult(result)
      })
      .catch(() => setHourlyUpdateError('Could not save the update. Please try again.'))
      .finally(() => setIsSubmittingHourlyUpdate(false))
  }

  function handleStartPlannedDowntime(reason: string) {
    if (isSubmittingPlannedDowntime) return
    setIsSubmittingPlannedDowntime(true)
    startPlannedDowntime(reason)
      .then(setPlannedDowntimeEvent)
      .finally(() => setIsSubmittingPlannedDowntime(false))
  }

  function handleEndPlannedDowntime() {
    if (!activeRun || !plannedDowntimeEvent || isSubmittingPlannedDowntime) return
    setIsSubmittingPlannedDowntime(true)
    endPlannedDowntime(plannedDowntimeEvent.startedAtIso)
      .then((result) => {
        const updated: ActiveRunRecord = {
          ...activeRun,
          plannedDowntimeMinutes: activeRun.plannedDowntimeMinutes + result.minutes,
        }
        saveActiveRun(updated)
        setActiveRun(updated)
        setPlannedDowntimeEvent(null)
        setScreen('activeRun')
      })
      .finally(() => setIsSubmittingPlannedDowntime(false))
  }

  function handleReportToEngineerSubmit(input: {
    machine: string
    faultReason: string
    note: string
  }) {
    if (!activeRun || isSubmittingEngineerReport) return
    setIsSubmittingEngineerReport(true)
    setEngineerReportError(null)

    reportFaultToEngineer({ productionLine: activeRun.form.productionLine, ...input })
      .then(setEngineerReportResult)
      .catch(() => setEngineerReportError('Could not report the fault. Please try again.'))
      .finally(() => setIsSubmittingEngineerReport(false))
  }

  function handleConfirmCompleteRun() {
    if (!activeRun || isCompletingRun) return
    setIsCompletingRun(true)
    setCompleteRunError(null)

    completeRun(activeRun.runId)
      .then(() => {
        clearActiveRun()
        setScreen('runCompleted')
      })
      .catch((error: unknown) => setCompleteRunError(mapCompleteRunError(error)))
      .finally(() => setIsCompletingRun(false))
  }

  function handleConfirmExit() {
    clearActiveRun()
    setActiveRun(null)
    setPlannedDowntimeEvent(null)
    setScreen('home')
  }

  function handleBackToHomeAfterCompletion() {
    setActiveRun(null)
    setScreen('home')
  }

  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------

  switch (screen) {
    case 'home':
      return (
        <HomeScreen
          configState={configState}
          activeRun={activeRun}
          onRetry={() => loadConfig()}
          onStartRun={handleStartRunFromHome}
          onResumeActiveRun={() => setScreen('activeRun')}
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
      if (!activeRun) {
        setRecoverableErrorMessage('No active run was found.')
        setScreen('recoverableError')
        return null
      }
      return (
        <ActiveRunScreen
          run={activeRun}
          onHourlyUpdate={() => {
            setHourlyUpdateResult(null)
            setHourlyUpdateError(null)
            setScreen('hourlyUpdate')
          }}
          onPlannedDowntime={() => setScreen('plannedDowntime')}
          onReportToEngineer={() => {
            setEngineerReportResult(null)
            setEngineerReportError(null)
            setScreen('reportToEngineer')
          }}
          onCompleteRun={() => {
            setCompleteRunError(null)
            setScreen('completeRun')
          }}
          onExitRestart={() => setScreen('exitRestart')}
        />
      )

    case 'hourlyUpdate':
      if (!activeRun) return null
      return (
        <HourlyUpdateScreen
          run={activeRun}
          isSubmitting={isSubmittingHourlyUpdate}
          result={hourlyUpdateResult}
          errorMessage={hourlyUpdateError}
          onCancel={() => setScreen('activeRun')}
          onSubmit={handleHourlyUpdateSubmit}
          onDone={() => {
            setHourlyUpdateResult(null)
            setScreen('activeRun')
          }}
        />
      )

    case 'plannedDowntime':
      return (
        <PlannedDowntimeScreen
          reasons={[...DEFAULT_PLANNED_DOWNTIME_REASONS]}
          activeEvent={plannedDowntimeEvent}
          isSubmitting={isSubmittingPlannedDowntime}
          onStart={handleStartPlannedDowntime}
          onEnd={handleEndPlannedDowntime}
          onCancel={() => setScreen('activeRun')}
        />
      )

    case 'reportToEngineer': {
      if (!activeRun) return null
      const configLine =
        configState.status === 'ready'
          ? configState.lines.find((line) => line.name === activeRun.form.productionLine)
          : undefined
      return (
        <ReportToEngineerScreen
          productionLine={activeRun.form.productionLine}
          machines={configLine?.machines ?? []}
          isSubmitting={isSubmittingEngineerReport}
          result={engineerReportResult}
          errorMessage={engineerReportError}
          onSubmit={handleReportToEngineerSubmit}
          onCancel={() => setScreen('activeRun')}
          onDone={() => {
            setEngineerReportResult(null)
            setScreen('activeRun')
          }}
        />
      )
    }

    case 'completeRun':
      if (!activeRun) return null
      return (
        <CompleteRunScreen
          run={activeRun}
          isSubmitting={isCompletingRun}
          errorMessage={completeRunError}
          onCancel={() => setScreen('activeRun')}
          onConfirm={handleConfirmCompleteRun}
        />
      )

    case 'runCompleted':
      return (
        <RunCompletedScreen
          productionLine={activeRun?.form.productionLine ?? ''}
          onBackToHome={handleBackToHomeAfterCompletion}
        />
      )

    case 'exitRestart':
      if (!activeRun) return null
      return (
        <ExitRestartScreen
          productionLine={activeRun.form.productionLine}
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
            setScreen('home')
            loadConfig()
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
