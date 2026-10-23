import { useEffect, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { PointerLockControls, Text } from "@react-three/drei";
import * as THREE from "three";

function Painting({photo,z=-4.86}) {
 return <group position={[photo.pos_x ?? 0,2.1,z]}>
  <mesh><boxGeometry args={[1.8,1.8,.12]}/><meshStandardMaterial color="#c39a58" metalness={.5} roughness={.3}/></mesh>
  <mesh position={[0,0,.07]}><planeGeometry args={[1.58,1.58]}/><meshBasicMaterial color={photo.tint || "#b9a48d"}/></mesh>
  <Text position={[0,-1.08,.08]} fontSize={.15} color="#fff0d0" anchorX="center">{photo.filename || photo.title || "A Memory"}</Text>
 </group>
}
function Scene({wallColor,photos,onPosition}) {
 const keys=useRef({});
 const timer=useRef(0);
 useEffect(()=>{
  const d=e=>{keys.current[e.code]=true},u=e=>{keys.current[e.code]=false};
  window.addEventListener("keydown",d);window.addEventListener("keyup",u);
  return()=>{window.removeEventListener("keydown",d);window.removeEventListener("keyup",u)};
 },[]);
 useFrame((state,dt)=>{
  const k=keys.current,c=state.camera,speed=3*Math.min(dt,.05);
  const f=Number(k.KeyW||k.ArrowUp)-Number(k.KeyS||k.ArrowDown);
  const side=Number(k.KeyD||k.ArrowRight)-Number(k.KeyA||k.ArrowLeft);
  const forward=new THREE.Vector3();c.getWorldDirection(forward);forward.y=0;forward.normalize();
  const right=new THREE.Vector3().crossVectors(forward,c.up).normalize();
  c.position.addScaledVector(forward,-f*speed).addScaledVector(right,side*speed);
  c.position.x=THREE.MathUtils.clamp(c.position.x,-5.4,5.4);
  c.position.z=THREE.MathUtils.clamp(c.position.z,-5.4,5.4);c.position.y=1.7;
  timer.current+=dt;
  if(timer.current>1.0){timer.current=0;onPosition?.({x:c.position.x,y:c.position.y,z:c.position.z})}
 });
 return <>
  <mesh rotation={[-Math.PI/2,0,0]}><planeGeometry args={[12,12]}/><meshStandardMaterial color="#6f6259"/></mesh>
  {[[0,2.5,-5,12,5,.2],[-6,2.5,0,.2,5,12],[6,2.5,0,.2,5,12],[0,5,0,12,.2,12]].map((a,i)=><mesh key={i} position={a.slice(0,3)}><boxGeometry args={a.slice(3)}/><meshStandardMaterial color={i===3?"#eee9e0":wallColor}/></mesh>)}
  {photos.map((p,i)=><Painting key={p.id||i} photo={{...p,pos_x:p.pos_x??(-3.2+i*3.2)}}/>)}
  <ambientLight intensity={1.3}/><pointLight position={[0,4.4,-3.5]} intensity={25} color="#ffe0a4"/>
  <PointerLockControls/>
 </>;
}
export default function Museum({wallColor,photos,onPosition}) {
 return <Canvas camera={{position:[0,1.7,3.5],fov:70}} dpr={[1,1.5]}><color attach="background" args={["#181513"]}/><Scene wallColor={wallColor} photos={photos} onPosition={onPosition}/></Canvas>;
}
