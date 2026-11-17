import { ref } from 'vue'
import type { Router } from 'vue-router'
import { clearApiCache } from '../api/client'
export const campusRevision = ref(0)
export const campusSwitching = ref(false)
export async function switchCampus(id:string, router:Router) {
  if(localStorage.getItem('campustrace-campus')===id)return
  // 先卸载旧页面，阻止旧校园响应出现在新校园；不重启登录会话。
  campusSwitching.value=true
  clearApiCache()
  localStorage.setItem('campustrace-campus',id)
  try {
    // 管理员切换数据范围时留在原后台模块；页面由
    // campusRevision 重新挂载并携带新的 X-Campus-ID 读取数据。
    // 普通物品详情可能不属于新校区，前台仍回到首页。
    if (!router.currentRoute.value.path.startsWith('/admin')) await router.replace('/home')
  }
  finally { campusRevision.value++;campusSwitching.value=false }
}
