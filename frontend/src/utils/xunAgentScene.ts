import * as THREE from 'three'

export type XunGesture = 'idle'|'wave'|'spin'|'wink'
export function createXunRig(logoTexture?: THREE.Texture) {
  const root=new THREE.Group(), head=new THREE.Group(), leftArm=new THREE.Group(), rightArm=new THREE.Group()
  const white=new THREE.MeshStandardMaterial({color:0xf1f8ff,roughness:.85,metalness:0})
  const blue=new THREE.MeshStandardMaterial({color:0x70a9ee,roughness:.85})
  const dark=new THREE.MeshBasicMaterial({color:0x183c58})
  const mint=new THREE.MeshBasicMaterial({color:0x8df2ed})
  const pink=new THREE.MeshBasicMaterial({color:0xf3a9c4})
  const sparkle=new THREE.MeshBasicMaterial({color:0xffffff})
  
  const sphere=new THREE.SphereGeometry(1,32,24)
  function orb(parent:THREE.Object3D,material:THREE.Material,x:number,y:number,z:number,sx:number,sy:number,sz:number){
    const mesh=new THREE.Mesh(sphere,material);mesh.position.set(x,y,z);mesh.scale.set(sx,sy,sz);parent.add(mesh);return mesh
  }
  const leftFoot=orb(root,white,-.28,.19,.10,.24,.15,.30),rightFoot=orb(root,white,.28,.19,.10,.24,.15,.30)
  orb(root,white,0,.75,0,.50,.46,.34)
  // The badge uses the same source asset as the website header.
  if(logoTexture){
    logoTexture.colorSpace=THREE.SRGBColorSpace
    const crest=new THREE.Mesh(new THREE.PlaneGeometry(.34,.34),new THREE.MeshBasicMaterial({map:logoTexture,transparent:true,toneMapped:false}))
    crest.position.set(0,.78,.355);root.add(crest)
  }
  orb(root,blue,0,.78,-.37,.38,.38,.15)
  orb(root,blue,0,1.12,0,.48,.095,.36)
  const scarf=orb(root,blue,.27,.99,.30,.10,.22,.06);scarf.rotation.z=.22
  head.position.set(0,1.84,0);root.add(head)
  orb(head,white,0,0,0,1.0,.76,.50)
  orb(head,dark,0,-.035,.50,.80,.45,.115)
  orb(head,blue,-1.0,-.01,0,.11,.20,.15);orb(head,blue,1.0,-.01,0,.11,.20,.15)
  const leftEye=orb(head,mint,-.28,.055,.632,.10,.145,.025),rightEye=orb(head,mint,.28,.055,.632,.10,.145,.025)
  for(const eye of [leftEye,rightEye])orb(eye,sparkle,-.23,.30,.91,.22,.18,.26)
  orb(head,pink,-.50,-.17,.593,.09,.045,.022);orb(head,pink,.50,-.17,.593,.09,.045,.022)
  const smile=new THREE.CatmullRomCurve3([new THREE.Vector3(-.12,-.205,.615),new THREE.Vector3(0,-.275,.613),new THREE.Vector3(.12,-.205,.615)])
  const mouth=new THREE.Mesh(new THREE.TubeGeometry(smile,16,.016,8,false),mint);head.add(mouth)
  const ears=new THREE.Group();head.add(ears)
  const leftEar=new THREE.Group();leftEar.position.set(-.43,.60,0);leftEar.rotation.z=.17;ears.add(leftEar)
  orb(leftEar,white,0,.39,0,.18,.50,.14);orb(leftEar,mint,0,.40,.13,.085,.32,.025)
  const rightEar=new THREE.Group();rightEar.position.set(.44,.60,0);rightEar.rotation.z=-.32;ears.add(rightEar)
  orb(rightEar,white,0,.24,0,.18,.33,.14);orb(rightEar,mint,0,.26,.13,.085,.19,.025)
  const tip=new THREE.Group();tip.position.set(0,.46,0);tip.rotation.z=-.65;rightEar.add(tip)
  orb(tip,white,0,.15,0,.17,.23,.14);orb(tip,mint,0,.15,.13,.08,.14,.025)
  const light=leftEar
  // The rear housing, side ears and curved shells remain visible while turning.
  orb(head,blue,0,-.025,-.49,.40,.25,.035)
  for(const y of [-.10,0,.10]){
    const vent=new THREE.Mesh(new THREE.BoxGeometry(.27,.022,.025),dark);vent.position.set(0,y,-.53);head.add(vent)
  }
  leftArm.position.set(-.48,1.01,0);rightArm.position.set(.48,1.01,0);root.add(leftArm,rightArm)
  orb(leftArm,blue,-.12,-.14,0,.12,.20,.13);orb(rightArm,blue,.12,-.14,0,.12,.20,.13)
  orb(leftArm,white,-.19,-.31,.04,.18,.17,.16);orb(rightArm,white,.19,-.31,.04,.18,.17,.16)
  root.position.y=.04
  return {root,head,leftArm,rightArm,leftFoot,rightFoot,leftEye,rightEye,mouth,light}
}
export type XunRig=ReturnType<typeof createXunRig>

export function poseXun(rig:XunRig,gesture:XunGesture,elapsed:number,seconds:number,speaking=false,reduced=false){
  const t=Math.max(0,Math.min(1,elapsed/2.8)),envelope=Math.sin(Math.PI*t)
  rig.root.position.set(0,.04+(reduced?0:.008*Math.sin(seconds*1.8)),0)
  rig.root.rotation.set(0,0,0);rig.head.rotation.set(0,0,0)
  rig.leftArm.rotation.set(0,0,-.12);rig.rightArm.rotation.set(0,0,.12)
  rig.leftFoot.rotation.set(0,0,0);rig.rightFoot.rotation.set(0,0,0)
  const blink=!reduced&&seconds%5.4>4.3&&seconds%5.4<4.46?.14:1
  rig.leftEye.scale.y=.145*blink;rig.rightEye.scale.y=.145*blink
  rig.mouth.scale.y=speaking&&!reduced?1+.25*Math.sin(seconds*18):1
  if(reduced)return
  if(gesture==='spin'){
    // Real skeletal motion in world space: a full turn, light hops, alternating
    // steps and arms extended for balance. The camera and DOM never rotate.
    rig.root.rotation.y=Math.PI*2*(t*t*(3-2*t))
    rig.root.rotation.z=.075*Math.sin(t*Math.PI*4)*envelope
    rig.root.position.x=.09*Math.sin(t*Math.PI*2)*envelope
    rig.root.position.y+=.16*envelope*envelope+.04*Math.pow(Math.sin(t*Math.PI*6),2)
    rig.leftArm.rotation.z=-.12-.85*envelope;rig.rightArm.rotation.z=.12+.85*envelope
    rig.leftFoot.rotation.x=.32*Math.sin(t*Math.PI*6)*envelope
    rig.rightFoot.rotation.x=-rig.leftFoot.rotation.x
    rig.head.rotation.z=-rig.root.rotation.z*.55
  }else if(gesture==='wave'){
    rig.rightArm.rotation.z=.12+envelope*(.9+.25*Math.sin(t*Math.PI*8))
    rig.head.rotation.z=-.08*envelope
  }else if(gesture==='wink'&&elapsed>.35&&elapsed<1.5){
    rig.rightEye.scale.y=.012;rig.head.rotation.z=-.07
  }
}

export function disposeXunScene(scene:THREE.Scene){
  const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>()
  scene.traverse(object=>{if(object instanceof THREE.Mesh){geometries.add(object.geometry);for(const material of Array.isArray(object.material)?object.material:[object.material])materials.add(material)}})
  geometries.forEach(g=>g.dispose());const textures=new Set<THREE.Texture>();materials.forEach(m=>{const map=(m as THREE.MeshBasicMaterial).map;if(map)textures.add(map);m.dispose()});textures.forEach(t=>t.dispose())
}
