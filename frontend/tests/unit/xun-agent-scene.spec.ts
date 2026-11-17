import { expect,it,vi } from 'vitest'
import * as THREE from 'three'
import { createXunRig,poseXun,disposeXunScene } from '../../src/utils/xunAgentScene'

it('dances with actual world-space rotation and articulated feet, including a visible back',()=>{
  const rig=createXunRig()
  poseXun(rig,'spin',.9,0)
  expect(rig.root.rotation.y).toBeGreaterThan(0)
  expect(Math.abs(rig.leftFoot.rotation.x)).toBeGreaterThan(.01)
  expect(rig.rightFoot.rotation.x).toBe(-rig.leftFoot.rotation.x)
  poseXun(rig,'spin',1.4,0)
  expect(rig.root.rotation.y).toBeCloseTo(Math.PI)
  expect(rig.head.children.some(child=>child.position.z<-.5)).toBe(true)
  poseXun(rig,'spin',2.8,0)
  expect(rig.root.rotation.y).toBeCloseTo(Math.PI*2)
  poseXun(rig,'idle',0,0)
  expect(rig.root.rotation.y).toBe(0)
  const scene=new THREE.Scene();scene.add(rig.root);disposeXunScene(scene)
})

it('keeps reduced-motion still and disposes shared mesh resources once',()=>{
  const rig=createXunRig(),scene=new THREE.Scene();scene.add(rig.root)
  poseXun(rig,'spin',1.4,1,true,true)
  expect(rig.root.rotation.y).toBe(0)
  const shared=(rig.head.children.find(child=>child instanceof THREE.Mesh) as THREE.Mesh).geometry
  const dispose=vi.spyOn(shared,'dispose')
  disposeXunScene(scene)
  expect(dispose).toHaveBeenCalledTimes(1)
})
