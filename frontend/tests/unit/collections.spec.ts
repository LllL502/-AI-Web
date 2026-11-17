import {it,expect,vi} from 'vitest'
import {apiCollection} from '../../src/api/collections'
const mock=vi.hoisted(()=>vi.fn())
vi.mock('../../src/api/client',()=>({api:mock}))
it('loads later collection pages for selectors instead of silently truncating at 100',async()=>{mock.mockResolvedValueOnce({data:{items:[{id:1}],total:3,page:1,page_size:1}}).mockResolvedValueOnce({data:{items:[{id:2}]}}).mockResolvedValueOnce({data:{items:[{id:3}]}});const result=await apiCollection<{data:{items:{id:number}[];total:number}}>('/items/?mine=true&page_size=1');expect(result.data.items.map(row=>row.id)).toEqual([1,2,3]);expect(mock.mock.calls[2][0]).toContain('page=3')})
