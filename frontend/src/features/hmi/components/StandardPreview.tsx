import { useEffect, useState } from 'react'
import { apiClient } from '../../../api/client'
import type { StartRunFormValues } from '../types'

export function StandardPreview({values}: {values:StartRunFormValues}) {
 const {productionLine,product,packType,packWeightKg,packsPerCase,casesPerPallet}=values
 const [result,setResult]=useState('Complete the product and pack configuration to see its management standard.')
 useEffect(()=>{
  if (!product || !packType || !(Number(packWeightKg)>0) || !(Number(packsPerCase)>0) || !(Number(casesPerPallet)>0)) {
   setResult('Complete the product and pack configuration to see its management standard.'); return
  }
  const controller=new AbortController()
  setResult('Checking management standard...')
  const timer=setTimeout(()=>{
   apiClient.post<{id:number;standard_speed_ppm:number;effective_at:string}>('/api/v1/production-standards/resolve',{
    production_line:productionLine,product,pack_type:packType,pack_weight_kg:packWeightKg,
    packs_per_case:Number(packsPerCase),cases_per_pallet:Number(casesPerPallet)
   },{signal:controller.signal}).then(r=>{
    if (!controller.signal.aborted) setResult(`Management standard: ${r.standard_speed_ppm} packs/min (version ${r.id}, effective ${new Date(r.effective_at).toLocaleString()}). Start Run checks the applicable version again.`)
   }).catch(error=>{if (!controller.signal.aborted) setResult(error instanceof Error ? error.message : 'Standard unavailable. Please retry.')})
  },300)
  return ()=>{clearTimeout(timer);controller.abort()}
 },[productionLine,product,packType,packWeightKg,packsPerCase,casesPerPallet])
 return <p role="status">{result}</p>
}
