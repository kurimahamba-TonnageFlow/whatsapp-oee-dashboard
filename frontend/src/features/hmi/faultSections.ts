/** Tablet navigation only. Database machine/button IDs remain the reporting identity.
 * BV1/BV2 belong to SBS. Shared discharge, extraction and folding faults
 * must never be attributed to either bagger. Labels come from the paper
 * sheet supplied on 3 October and the user's equipment clarification.
 */
export function isSbsMachine(name: string): boolean {
  return /^SBS (Bagger BV[12]|Shared Equipment)$/i.test(name)
}
export function sbsEquipmentLabel(name: string): string {
  return /BV1$/i.test(name) ? 'BV1' : /BV2$/i.test(name) ? 'BV2' : 'Shared SBS equipment'
}
export function faultSection(name: string): string {
  const value = name.toLowerCase()
  if (value === 'film torn') return 'Film'
  if (value === 'bag crosswise') return 'Bagger forming section'
  if (['top seal', 'vertical seal', 'bottom seal'].includes(value)) return 'Sealing station'
  if (['label snapped', 'bag printer', 'ribbon tension'].includes(value)) return 'Printer and label'
  if (value === 'sbs discharge belt jam') return 'Discharge belts'
  if (value === 'secondary jaw cut-off extractor fault') return 'Secondary jaw extractor'
  if (value === 'top fold guide fault') return 'Pack folding'
  return 'Other faults'
}
