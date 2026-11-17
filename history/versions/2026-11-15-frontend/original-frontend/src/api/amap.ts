let pending:Promise<any>|null=null
export function loadAMap(key:string,serviceHost:string):Promise<any>{
  const global=window as any
  if(global.AMap)return Promise.resolve(global.AMap)
  if(pending)return pending
  global._AMapSecurityConfig={serviceHost:window.location.origin+serviceHost}
  pending=new Promise((resolve,reject)=>{
    const script=document.createElement('script')
    let settled=false
    const fail=()=>{if(settled)return;settled=true;clearTimeout(timer);script.remove();pending=null;reject(new Error('地图加载失败，请检查网络后重试'))}
    const timer=setTimeout(fail,15000)
    script.src=`https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}&plugin=AMap.PlaceSearch,AMap.Scale,AMap.ToolBar`
    script.async=true
    script.onload=()=>{if(settled)return;if(!global.AMap){fail();return};settled=true;clearTimeout(timer);resolve(global.AMap)}
    script.onerror=fail
    document.head.appendChild(script)
  })
  return pending
}
