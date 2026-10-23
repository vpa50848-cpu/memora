import { useEffect, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, StartAudio } from "@livekit/components-react";
import "@livekit/components-styles";

export default function VoiceRoom({museumId,onClose}) {
 const [session,setSession]=useState(null),[error,setError]=useState("");
 useEffect(()=>{
  let alive=true;
  fetch(`/api/rooms/${museumId}/voice-token`,{method:"POST",credentials:"include"})
   .then(async r=>{const d=await r.json();if(!r.ok)throw new Error(d.detail||"Could not join voice chat.");return d})
   .then(d=>{if(alive)setSession(d)})
   .catch(e=>{if(alive)setError(e.message)});
  return()=>{alive=false};
 },[museumId]);
 if(error)return <div className="voice-box">Voice chat: {error} <button onClick={onClose}>Close</button></div>;
 if(!session)return <div className="voice-box">Connecting to voice chat…</div>;
 return <div className="voice-box">
  <button className="voice-close" onClick={onClose}>Close voice</button>
  <LiveKitRoom serverUrl={session.server_url} token={session.token} connect audio video={false} onDisconnected={onClose}>
   <RoomAudioRenderer/><StartAudio label="Enable voice audio"/>
   <div>Voice room connected. Allow microphone access when prompted.</div>
  </LiveKitRoom>
 </div>;
}
