import { render, screen, fireEvent } from '@testing-library/react'
import { afterEach, it, expect, vi } from 'vitest'
import { DeviceGate } from './DeviceGate'
import { apiClient } from '../../api/client'
afterEach(()=>{sessionStorage.clear();vi.restoreAllMocks()})
it('protects capture until tablet sign-in and locks after expiry',async()=>{
 vi.spyOn(apiClient,'post').mockResolvedValue({token:'device-token'})
 render(<DeviceGate><p>Production capture</p></DeviceGate>)
 expect(screen.queryByText('Production capture')).toBeNull()
 fireEvent.change(screen.getByLabelText('Tablet name'),{target:{value:'Rovema tablet'}})
 fireEvent.change(screen.getByLabelText('Tablet PIN'),{target:{value:'test-secret'}})
 fireEvent.click(screen.getByRole('button',{name:'Sign in to tablet'}))
 await screen.findByText('Production capture')
 fireEvent(window,new Event('pulse-tablet-expired'))
 expect(screen.queryByText('Production capture')).toBeNull()
 expect(screen.getByRole('alert')).toHaveTextContent('pending work is retained')
})
