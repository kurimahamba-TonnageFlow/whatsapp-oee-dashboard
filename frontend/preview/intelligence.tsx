import {useState} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {DashboardLayout} from '../src/features/dashboard/shell/DashboardLayout'
import {OperationalIntelligenceView} from '../src/features/dashboard/intelligence/OperationalIntelligence'
import type {IntelligenceSnapshot} from '../src/features/dashboard/intelligence/types'
import {ManagementSessionContext,type ManagementSessionContextValue} from '../src/features/management/session/managementSessionContext'
import {apiClient} from '../src/api/client'
import fixtures from './intelligence-fixtures.json'
import '../src/styles/global.css'
if(!['127.0.0.1','localhost'].includes(location.hostname))throw new Error('Local synthetic preview only')
apiClient.get=async <T,>():Promise<T>=>({status:'ok'} as T)
const session:ManagementSessionContextValue={session:{token:'synthetic-preview',managerName:'Preview manager',expiresAt:'2099-01-01T00:00:00Z'},isRestoring:false,endReason:null,notice:null,signIn:()=>undefined,signOut:()=>undefined,expireSession:()=>undefined,acknowledgeSignOut:()=>undefined,handleAuthError:()=>false}
export function Preview(){
 const [mode,setMode]=useState('normal')
 const data=(fixtures[mode==='stale'?'normal':mode as keyof typeof fixtures]) as unknown as IntelligenceSnapshot
 return <><style>{'.pd{min-height:calc(100vh - 38px)}.pd-side__inner{height:calc(100vh - 38px)}'}</style><div style={{padding:'6px 12px',background:'#242a30',color:'#fff',display:'flex',gap:10,alignItems:'center',fontSize:12}}><strong>LOCAL PREVIEW - synthetic records</strong>{['normal','empty','unscheduled','stale'].map(m=><button style={{minHeight:26,height:26,padding:'0 10px'}} key={m} onClick={()=>setMode(m)} aria-pressed={m===mode}>{m}</button>)}</div><ManagementSessionContext.Provider value={session}><MemoryRouter initialEntries={['/dashboard/operational-intelligence']}><Routes><Route element={<DashboardLayout/>}><Route path="*" element={<OperationalIntelligenceView data={data} error={mode==='stale'?'Connection unavailable':null} loading={false} refresh={()=>setMode('normal')} period="production_week" onPeriod={()=>undefined} line="" onLine={()=>undefined}/>}/></Route></Routes></MemoryRouter></ManagementSessionContext.Provider></>
}
createRoot(document.getElementById('root')!).render(<Preview/>)
