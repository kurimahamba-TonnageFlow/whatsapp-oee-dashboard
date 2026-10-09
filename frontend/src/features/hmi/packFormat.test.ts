import {expect,it} from 'vitest'
import {parsePackFormat} from './packWeight'
it.each([['1x10','1kg','10'],['500g x 8','500g','8'],['0.5kg x 8','500g','8'],['1\u00d710','1kg','10']])('derives %s without duplicate entry',(format,weight,packs)=>{
 expect(parsePackFormat(format,weight)).toEqual({packsPerCase:packs,error:null})
})
it.each(['1x1.5','1x0','pillow','1x10x2','500g x 10'])('rejects invalid or mismatched format %s',format=>{
 expect(parsePackFormat(format,'1kg').packsPerCase).toBe('')
 expect(parsePackFormat(format,'1kg').error).not.toBeNull()
})
