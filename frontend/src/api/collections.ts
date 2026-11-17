import {api} from './client'
/** Complete collections for selectors and locally paged lists. Public search stays server-paged. */
export async function apiCollection<T>(path:string):Promise<T>{
 const first=await api<T>(path)
 const result=first as {data?:{items?:unknown[];total?:number;page?:number;page_size?:number}}
 const data=result.data
 if(!data||!Array.isArray(data.items)||!data.total||data.items.length>=data.total)return first
 const items=[...data.items],seen=new Set(items.map((row:any)=>row.id))
 const url=new URL(path,'http://local');let page=(data.page??1)+1
 while(items.length<data.total){url.searchParams.set('page',String(page++));const response=await api<{data:{items:unknown[]}}>(url.pathname+url.search);const rows=response.data.items;if(!rows.length)break;let added=0;for(const row of rows as any[]){if(!seen.has(row.id)){seen.add(row.id);items.push(row);added++}}if(!added)throw new Error('列表分页未前进，请重试')}
 return {...first,data:{...data,items}} as T
}
