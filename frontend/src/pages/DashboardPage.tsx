import { Link, useSearchParams } from 'react-router-dom'
import { ProductionDashboard } from '../features/dashboard/ProductionDashboard'
import { LiveOperations } from '../features/dashboard/LiveOperations'
export function DashboardPage(){
 const [params]=useSearchParams()
 return params.get('view')==='reports'?<><Link className="pd-button" to="/dashboard">Back to Live Operations</Link><ProductionDashboard/></>:<LiveOperations/>
}
