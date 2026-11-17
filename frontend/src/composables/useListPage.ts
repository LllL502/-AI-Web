import {computed,ref,watch,type Ref,type ComputedRef} from 'vue'
export function useListPage<T>(source:Ref<T[]>|ComputedRef<T[]>,size=20){const page=ref(1);const rows=computed(()=>source.value.slice((page.value-1)*size,page.value*size));watch(()=>source.value,()=>{page.value=Math.min(page.value,Math.max(1,Math.ceil(source.value.length/size)))});return {page,rows}}
