import { useEffect, useState, type ReactNode, type FormEvent } from 'react'
import { apiClient } from '../../api/client'
export function DeviceGate({children}: {children: ReactNode}) {
 const [ready,setReady] = useState(false)
 const [checking,setChecking] = useState(true)
 const [error,setError] = useState('')
 const [busy,setBusy] = useState(false)
 useEffect(() => {
  let active=true
  const expired=()=>{setReady(false);setError('Tablet session ended. Sign in to continue. Your pending work is retained.')}
  window.addEventListener('pulse-tablet-expired',expired)
  if (sessionStorage.getItem('pulse.tablet.session')) {
   apiClient.get('/api/v1/hmi-access/session').then(()=>{if(active)setReady(true)}).catch(()=>{if(active)setError('Sign in to continue.')}).finally(()=>{if(active)setChecking(false)})
  } else setChecking(false)
  return ()=>{active=false;window.removeEventListener('pulse-tablet-expired',expired)}
 },[])
 async function login(event: FormEvent<HTMLFormElement>) {
  event.preventDefault(); if(busy)return
  const form=new FormData(event.currentTarget);setBusy(true);setError('')
  try {
   const result=await apiClient.post<{token:string}>('/api/v1/hmi-access/login',{device_name:form.get('device'),pin:form.get('pin')})
   sessionStorage.setItem('pulse.tablet.session',result.token);setReady(true)
  } catch(e){setError(e instanceof Error ? e.message : 'Could not sign in.')} finally{setBusy(false)}
 }
 if(checking)return <p>Checking tablet access?</p>
 if(ready)return <><button type="button" onClick={async()=>{try{await apiClient.post('/api/v1/hmi-access/logout')}catch{setError('Tablet locked locally. Server sign-out could not be confirmed; the server session will expire automatically.')}finally{sessionStorage.removeItem('pulse.tablet.session');setReady(false)}}}>Lock tablet</button>{children}</>
 return <section className="hmi-screen"><h1>Tablet sign in</h1><p>Authorise this tablet before recording production. Operator names are recorded separately.</p><form onSubmit={login}>
 <label className="hmi-field">Tablet name<input name="device" required maxLength={100}/></label>
 <label className="hmi-field">Tablet PIN<input name="pin" type="password" required autoComplete="off" maxLength={200}/></label>
 <button type="submit" disabled={busy}>Sign in to tablet</button></form>{error&&<p role="alert">{error}</p>}</section>
}
