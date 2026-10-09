import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

const FinancialContext = createContext<() => void>(() => undefined)
function Lock() {
  return <svg viewBox="0 0 16 18" width="12" height="14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="2" y="7" width="12" height="9" rx="2"/><path d="M5 7V4a3 3 0 0 1 6 0v3M8 10v3"/></svg>
}
export function Phase2FinancialMetric({ label, unit = '', compact = false }: { label: string; unit?: '/ t' | '/ week' | ''; compact?: boolean }) {
  const open = useContext(FinancialContext)
  return <button type="button" className={`oi-financial${compact ? ' oi-financial--compact' : ''}`} onClick={open} aria-label={`${label}: Phase 2 financial preview`}>
    <span className="oi-financial__value">{'\u00a30,000'} {unit}</span>
    <span className="oi-financial__lock"><Lock/> PHASE 2 <span className="oi-financial__placeholder">Placeholder</span></span>
  </button>
}
export function FinancialPreviewButton({ children, className = '', label }: { children: ReactNode; className?: string; label: string }) {
  const open = useContext(FinancialContext)
  return <button type="button" className={className} onClick={open} aria-label={label}>{children}</button>
}
export function FinancialIntelligenceProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [contact, setContact] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (!open) return
    const node = dialog.current!
    node.showModal()
    return () => { node.close(); trigger.current?.focus() }
  }, [open])
  function close() { setOpen(false); setContact(false) }
  return <FinancialContext.Provider value={() => { trigger.current = document.activeElement as HTMLElement; setOpen(true) }}>
    {children}
    {open && <dialog className="oi-modal" ref={dialog} aria-labelledby="oi-modal-title" onCancel={close} onClick={event => { if (event.target === event.currentTarget) close() }}>
      <div className="oi-modal__body">
        <span className="oi-phase"><Lock/> PHASE 2</span>
        <h2 id="oi-modal-title">Phase 2 {'\u2014'} Financial Intelligence</h2>
        <p>TonnageFlow Pulse currently measures production performance, downtime and output losses.</p>
        <p>Phase 2 will connect these measurements to financial data, helping your business understand the cost per tonne, the financial impact of losses and the potential value of operational improvements.</p>
        <ul>{['Actual production cost per tonne', 'Target cost per tonne', 'Financial impact of downtime', 'Cost of rework and quality losses', 'Labour and overtime cost impact', 'Financial cost of changeovers', 'Estimated improvement opportunities', 'Cost trends across production periods'].map(item => <li key={item}>{item}</li>)}</ul>
        <p className="oi-modal__terms">Phase 2 requires additional financial inputs and configuration. Availability, implementation scope and pricing will be agreed separately.</p>
        {contact && <p role="status" className="oi-modal__contact">Please contact your Tonnage Flow representative to discuss your financial inputs, integration scope and a separate commercial agreement.</p>}
        <div className="oi-modal__actions"><button type="button" className="oi-primary" onClick={() => setContact(true)}>Discuss Phase 2</button><button type="button" onClick={close}>Continue Viewing Dashboard</button></div>
      </div>
    </dialog>}
  </FinancialContext.Provider>
}
