import { useEffect,useState } from "react";
import Museum from "./Museum.jsx";
import VoiceRoom from "./VoiceRoom.jsx";

async function api(path,options={}) {
 const r=await fetch(`/api${path}`,{credentials:"include",...options});
 const data=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(data.detail||"Request failed.");
 return data;
}
export default function App(){
 const [user,setUser]=useState(null),[museums,setMuseums]=useState([]),[museum,setMuseum]=useState(null);
 const [photos,setPhotos]=useState([]),[wall,setWall]=useState("#c6b9a6"),[name,setName]=useState("Our Memory Museum");
 const [message,setMessage]=useState(""),[voice,setVoice]=useState(false),[visitors,setVisitors]=useState([]);
 const [invite,setInvite]=useState(""),[busy,setBusy]=useState(false);
 async function load(){
  try{
   const u=await api("/me");setUser(u);
   const ms=await api("/museums");setMuseums(ms);
   const params=new URLSearchParams(location.search);
   const join=params.get("join");
   if(join){await api("/museums/join",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({invite_code:join})});history.replaceState({},"",location.pathname);setMessage("Joined museum.");}
   const all=await api("/museums");setMuseums(all);
   if(all.length){const m=all[0];await chooseMuseum(m.id)}
  }catch{setUser(null)}
 }
 async function chooseMuseum(id){
  try{const m=await api(`/museums/${id}`);setMuseum(m);setName(m.name);setWall(m.wall_color);setPhotos(m.photos||[])}catch(e){setMessage(e.message)}
 }
 useEffect(()=>{const p=new URLSearchParams(location.search);if(p.get("oauth")==="success")setMessage("Google Drive connected.");if(p.has("oauth"))history.replaceState({},"",location.pathname);load()},[]);
 async function createMuseum(){
  try{const m=await api("/museums",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:"Our Memory Museum"})});setMuseums(x=>[m,...x]);await chooseMuseum(m.id);setMessage("Museum created.")}catch(e){setMessage(e.message)}
 }
 async function saveStyle(nextName=name,nextWall=wall){
  if(!museum)return;
  try{const m=await api(`/museums/${museum.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:nextName,wall_color:nextWall})});setMuseum({...museum,...m});setMessage("Museum customization saved.")}catch(e){setMessage(e.message)}
 }
 async function upload(e){
  const file=e.target.files?.[0];e.target.value="";if(!file)return;
  setBusy(true);
  try{const form=new FormData();form.append("file",file);if(museum)form.append("museum_id",museum.id);
   const p=await api("/photos/upload",{method:"POST",body:form});setPhotos(old=>[...old,p]);setMessage("Photo saved to Google Drive.");
  }catch(err){setMessage(err.message)}finally{setBusy(false)}
 }
 async function inviteFriends(){
  try{const d=await api(`/museums/${museum.id}/invite`,{method:"POST"});await navigator.clipboard.writeText(d.invite_url);setMessage("Invitation link copied. Friends must sign in first.");}catch(e){setMessage(e.message)}
 }
 async function joinByCode(){
  try{const m=await api("/museums/join",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({invite_code:invite})});setInvite("");await load();await chooseMuseum(m.id);setMessage("Joined museum.");}catch(e){setMessage(e.message)}
 }
 useEffect(()=>{
  if(!museum)return;
  let live=true;
  const send=async(pos)=>{try{const d=await api(`/rooms/${museum.id}/presence`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(pos)});if(live)setVisitors(d.visitors||[])}catch{}};
  const onPos=e=>send(e.detail);
  window.addEventListener("memora-position",onPos);
  return()=>{live=false;window.removeEventListener("memora-position",onPos)};
 },[museum?.id]);
 // Poll presence to refresh the visitor list; serverless polling is a basic demo, not low-latency realtime networking.
 useEffect(()=>{if(!museum)return;let active=true;const tick=async()=>{try{const d=await api(`/rooms/${museum.id}/presence`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({x:0,y:1.7,z:0})});if(active)setVisitors(d.visitors||[])}catch{}};const id=setInterval(tick,5000);return()=>{active=false;clearInterval(id)}},[museum?.id]);
 async function logout(){await api("/auth/logout",{method:"POST"});setUser(null);setMuseum(null);setPhotos([]);setMuseums([])}
 return <main className="app">
  <header className="topbar"><div className="brand"><span>✦</span><div><h1>MEMORA</h1><small>YOUR WORLD OF MEMORIES</small></div></div>
   <div className="top-actions">{user?<><span className="status">{user.email}</span><button className="outline-btn" onClick={logout}>Sign out</button></>:<a className="outline-btn" href="/api/auth/google">Connect Google</a>}</div>
  </header>
  {!user?<section className="welcome"><span className="eyebrow">A WORLD MADE OF YOUR MEMORIES</span><h2>Walk through<br/><em>your story.</em></h2><p>Connect your Google account to create a private photo museum, invite friends and explore together.</p><a className="primary" href="/api/auth/google">Continue with Google</a>{message&&<p>{message}</p>}</section>:
  <section className="workspace">
   <div className="scene"><Museum wallColor={wall} photos={photos} onPosition={pos=>window.dispatchEvent(new CustomEvent("memora-position",{detail:pos}))}/>
    <div className="scene-title"><span>PRIVATE GALLERY</span><h2>{museum?.name||name}</h2><p>Click the room, then use WASD to walk.</p></div>
    <div className="movement-help"><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd><small>MOVE · CLICK TO LOOK</small></div>
   </div>
   <aside className="sidebar">
    <div className="panel-heading"><span>01 / YOUR MUSEUM</span><h2>Gallery studio</h2><p>Customize your room and share your memories.</p></div>
    <button className="primary full" onClick={createMuseum}>＋ Create museum</button>
    <label>Museums you can access</label>
    <select value={museum?.id||""} onChange={e=>chooseMuseum(e.target.value)}><option value="">Choose museum</option>{museums.map(m=><option value={m.id} key={m.id}>{m.name}</option>)}</select>
    <label>Museum title</label><input value={name} maxLength={120} onChange={e=>setName(e.target.value)}/>
    <div className="section-label">WALL ATMOSPHERE</div>
    <div className="palette">{["#c6b9a6","#a7777b","#353541","#7b8c7c","#e4d9c7"].map(c=><button key={c} className={`swatch ${wall===c?"selected":""}`} style={{background:c}} onClick={()=>{setWall(c);saveStyle(name,c)}}/>)}</div>
    <button className="outline-btn full" onClick={()=>saveStyle()}>Save customization</button>
    <div className="section-label">PHOTOGRAPHS</div>
    <label className="upload-box"><strong>{busy?"Uploading…":"＋ Upload photo"}</strong><small>JPG, PNG, WebP · Max 8 MB</small><input type="file" accept="image/jpeg,image/png,image/webp,image/gif" disabled={busy} onChange={upload}/></label>
    <div className="photo-list">{photos.map(p=><div className="photo-item" key={p.id}><img src={`/api/photos/${p.id}/content`} alt=""/><span title={p.filename}>{p.filename}</span><button onClick={async()=>{try{await api(`/photos/${p.id}`,{method:"DELETE"});setPhotos(x=>x.filter(q=>q.id!==p.id))}catch(e){setMessage(e.message)}}}>×</button></div>)}</div>
    {museum&&<><div className="section-label">INVITE FRIENDS</div><button className="primary full" onClick={inviteFriends}>Copy invitation link</button><div className="join"><input placeholder="Enter invite code" value={invite} onChange={e=>setInvite(e.target.value)}/><button className="outline-btn" onClick={joinByCode}>Join</button></div><div className="section-label">VISITORS · {visitors.length}</div><div className="visitor-list">{visitors.map(v=><span key={v.user_id}>● {v.name}</span>)}</div><button className="primary full" onClick={()=>setVoice(true)}>♫ Join voice chat</button></>}
    {message&&<p className="notice">{message}</p>}
   </aside>
  </section>}
  {voice&&museum&&<VoiceRoom museumId={museum.id} onClose={()=>setVoice(false)}/>}
  <footer className="footer"><span>MEMORA © 2026</span><span>PRIVATE BY DEFAULT</span><span>3D MUSEUM · PHASE 2 INTEGRATION</span></footer>
 </main>
}
