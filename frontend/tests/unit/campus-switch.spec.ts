import { expect,it,vi } from 'vitest'
import type { Router } from 'vue-router'
import { ref } from 'vue'
import { switchCampus,campusRevision,campusSwitching } from '../../src/stores/campus'

it('hides the old campus while navigating and refreshes page scope without a reload',async()=>{
  localStorage.clear()
  let finish!:()=>void
  const replace=vi.fn(()=>new Promise<void>(resolve=>{finish=resolve}))
  const router={
    currentRoute:ref({path:'/items/item-1'}),
    replace,
  } as unknown as Router
  const initial=campusRevision.value
  const pending=switchCampus('42',router)
  expect(campusSwitching.value).toBe(true)
  expect(localStorage.getItem('campustrace-campus')).toBe('42')
  finish();await pending
  expect(campusSwitching.value).toBe(false)
  expect(campusRevision.value).toBe(initial+1)
  await switchCampus('42',router)
  expect(replace).toHaveBeenCalledTimes(1)
})
