import {useState} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {DashboardLayout} from '../src/features/dashboard/shell/DashboardLayout'
import {LiveOperationsView} from '../src/features/dashboard/LiveOperations'
import type {LiveSnapshot} from '../src/features/dashboard/liveTypes'
import {ManagementSessionContext,type ManagementSessionContextValue} from '../src/features/management/session/managementSessionContext'
import {apiClient} from '../src/api/client'
import fixtures from './live-fixtures.json'
import '../src/styles/global.css'
if(!['127.0.0.1','localhost'].includes(location.hostname))throw new Error('Local synthetic preview only')
apiClient.get=async <T,>():Promise<T>=>({status:'ok'} as T)
const session:ManagementSessionContextValue={session:{token:'synthetic-preview',managerName:'Preview manager',expiresAt:'2099-01-01T00:00:00Z'},isRestoring:false,endReason:null,notice:null,signIn:()=>undefined,signOut:()=>undefined,expireSession:()=>undefined,acknowledgeSignOut:()=>undefined,handleAuthError:()=>false}
export function Preview(){
 const [mode,setMode]=useState('normal')
 const data=(fixtures[mode==='stale'?'normal':mode as keyof typeof fixtures]) as unknown as LiveSnapshot
 return <><style>{'.pd{min-height:calc(100vh - 38px)}.pd-side__inner{height:calc(100vh - 38px)}'}</style><div style={{padding:'6px 12px',background:'#242a30',color:'#fff',display:'flex',gap:10,alignItems:'center',fontSize:12}}><strong>LOCAL PREVIEW - synthetic records</strong>{['normal','empty','missing','above','unscheduled','stale'].map(m=><button style={{minHeight:26,height:26,padding:'0 10px'}} key={m} onClick={()=>setMode(m)} aria-pressed={m===mode}>{m}</button>)}</div><ManagementSessionContext.Provider value={session}><MemoryRouter><Routes><Route element={<DashboardLayout/>}><Route path="*" element={<LiveOperationsView data={data} error={mode==='stale'?'Connection unavailable':null} loading={false} refresh={()=>setMode('normal')} now={new Date(data.generated_at).getTime()+(mode==='stale'?180000:0)} week="" onWeek={()=>undefined}/>}/></Route></Routes></MemoryRouter></ManagementSessionContext.Provider></>
}
createRoot(document.getElementById('root')!).render(<Preview/>)
