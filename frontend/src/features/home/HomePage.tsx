import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiStatus } from '../../components/ApiStatus'
import { ManagementSessionBar } from '../management/ManagementSessionBar'
import { DESTINATIONS, QUICK_ACCESS, type Destination } from './navigation'
import { HomeIcon } from './HomeIcon'
import './home.css'

export function HomePage() {
  const [notice, setNotice] = useState<{ title: string; text: string } | null>(null)
  const [query, setQuery] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const search = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (!notice) return
    const trigger = document.activeElement as HTMLElement | null
    dialog.current?.showModal()
    return () => { trigger?.focus() }
  }, [notice])
  const close = () => { dialog.current?.close(); setNotice(null) }

  function card(item: Destination, quick = false) {
    const content = <>
      <span className="pulse-home__card-icon"><HomeIcon name={item.icon} /></span>
      <span className="pulse-home__card-copy"><span className="pulse-home__card-title">{item.title} {item.badge && <small>{item.badge}</small>}</span><span className="pulse-home__description">{item.description}</span></span>
      <span className="pulse-home__open" aria-hidden="true">{!quick && 'Open'} <span>&#8594;</span></span>
    </>
    const className = `pulse-home__card pulse-home__card--${item.tone}${item.id === 'performance' ? ' pulse-home__card--performance' : ''}${quick ? ' pulse-home__card--quick' : ''}`
    return item.to
      ? <Link key={item.id} to={item.to} className={className} aria-label={item.title}>{content}</Link>
      : <button key={item.id} type="button" className={className} aria-label={item.title} onClick={() => setNotice({ title: item.title, text: item.notice! })}>{content}</button>
  }

  return <div className="pulse-home">
    <a href="#home-destinations" className="pulse-home__skip">Skip to destinations</a>
    <aside className="pulse-home__sidebar">
      <Link to="/" className="pulse-home__brand" aria-label="TonnageFlow Pulse home"><img src="/tonnageflow-icon.svg" alt="" /><span>TonnageFlow<small>Pulse</small></span></Link>
      <nav aria-label="Home navigation">
        <Link to="/" aria-current="page"><HomeIcon name="home" />Home</Link>
        <button onClick={() => setNotice({ title: 'Notifications', text: 'A central notification inbox is under development. Current line status is available in HMI and Production; engineering jobs are in Engineering Workspace.' })}><HomeIcon name="notifications" />Notifications</button>
        <button onClick={() => { search.current?.scrollIntoView({ block: 'center' }); search.current?.focus() }}><HomeIcon name="search" />Search</button>
        <button onClick={() => setNotice({ title: 'Help', text: 'Choose HMI to run and update a line. Open Engineering Workspace for jobs and repairs. Management, Production, QA, Performance and Operational Intelligence use your existing Management sign-in. Planned areas show an information notice.' })}><HomeIcon name="help" />Help</button>
      </nav>
      <div className="pulse-home__sidebar-foot"><p>FOOD<br />BUILDS<br />A BRIGHTER<br />TOMORROW</p><span /><small>TonnageFlow Pulse<br />Smarter Food Production<br />Together</small></div>
    </aside>
    <main className="pulse-home__main">
      <header className="pulse-home__top"><span>PEOPLE / PROCESS / PRODUCT / A BRIGHTER TOMORROW</span><ApiStatus /></header>
      <ManagementSessionBar />
      <section className="pulse-home__hero" aria-labelledby="home-title"><h1 id="home-title">Welcome to <span>TonnageFlow Pulse</span></h1><p className="pulse-home__tagline">See the flow, know the cost. Grow.</p><p>Choose where you want to go and keep production flowing.</p></section>
      <section aria-labelledby="quick-title"><div className="pulse-home__section-title"><HomeIcon name="performance" /><div><h2 id="quick-title">Quick Access</h2><p>Your most used pages, right at your fingertips.</p></div></div><div className="pulse-home__quick">{QUICK_ACCESS.map((item) => card(item, true))}</div></section>
      <section id="home-destinations" aria-labelledby="destinations-title"><div className="pulse-home__section-title"><HomeIcon name="warehouse" /><div><h2 id="destinations-title">All Destinations</h2><p>Explore the full platform. Everything you need to run a smarter, more efficient operation.</p></div><label className="pulse-home__search"><span className="pulse-home__sr">Search destinations</span><input ref={search} type="search" placeholder="Search destinations" value={query} onChange={(event) => setQuery(event.target.value)} /></label></div><div className="pulse-home__destinations">{DESTINATIONS.filter((item) => `${item.title} ${item.description}`.toLowerCase().includes(query.trim().toLowerCase())).map((item) => card(item))}</div>{query && !DESTINATIONS.some((item) => `${item.title} ${item.description}`.toLowerCase().includes(query.trim().toLowerCase())) && <p role="status">No destinations match "{query}".</p>}</section>
      <footer className="pulse-home__footer">KEEP FOOD MOVING FOR A BRIGHTER TOMORROW.</footer>
    </main>
    <dialog ref={dialog} className="pulse-home__dialog" aria-labelledby="home-dialog-title" onKeyDown={(event) => {
        if (event.key === 'Tab') { event.preventDefault(); event.currentTarget.querySelector('button')?.focus() }
      }} onCancel={() => setNotice(null)} onClose={() => setNotice(null)}>
      <h2 id="home-dialog-title">{notice?.title}</h2><p>{notice?.text}</p><button type="button" onClick={close} autoFocus>Close</button>
    </dialog>
  </div>
}
