import io, os, time, uuid, secrets, string
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from livekit import api as livekit_api
from sqlalchemy import DateTime, ForeignKey, String, Float, BigInteger, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SCOPES = ["openid", "email", "profile", "https://www.googleapis.com/auth/drive.file"]
COOKIE = "memora_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
ENV = {k: os.getenv(k, "") for k in [
 "DATABASE_URL","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GOOGLE_REDIRECT_URI",
 "APP_ORIGIN","SESSION_SECRET","TOKEN_ENCRYPTION_KEY","LIVEKIT_URL",
 "LIVEKIT_API_KEY","LIVEKIT_API_SECRET"
]}
APP_ORIGIN = ENV["APP_ORIGIN"].rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE","true").lower() == "true"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB","8"))

app = FastAPI(title="MEMORA API", version="2.0.0")

class Base(DeclarativeBase): pass
class User(Base):
 __tablename__="memora_users"
 id: Mapped[str]=mapped_column(String(36),primary_key=True)
 google_sub: Mapped[str]=mapped_column(String(255),unique=True,index=True)
 email: Mapped[str]=mapped_column(String(320),index=True)
 name: Mapped[str]=mapped_column(String(255),default="")
 drive_folder_id: Mapped[str]=mapped_column(String(255),default="")
 refresh_token_encrypted: Mapped[Optional[str]]=mapped_column(String,nullable=True)
 created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Museum(Base):
 __tablename__="memora_museums"
 id: Mapped[str]=mapped_column(String(36),primary_key=True)
 owner_id: Mapped[str]=mapped_column(ForeignKey("memora_users.id",ondelete="CASCADE"),index=True)
 name: Mapped[str]=mapped_column(String(120))
 wall_color: Mapped[str]=mapped_column(String(30),default="#c6b9a6")
 invite_code: Mapped[str]=mapped_column(String(32),unique=True,index=True)
 created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Membership(Base):
 __tablename__="memora_memberships"
 id: Mapped[str]=mapped_column(String(36),primary_key=True)
 museum_id: Mapped[str]=mapped_column(ForeignKey("memora_museums.id",ondelete="CASCADE"),index=True)
 user_id: Mapped[str]=mapped_column(ForeignKey("memora_users.id",ondelete="CASCADE"),index=True)
 role: Mapped[str]=mapped_column(String(20),default="viewer")
 joined_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Photo(Base):
 __tablename__="memora_photos"
 id: Mapped[str]=mapped_column(String(36),primary_key=True)
 owner_id: Mapped[str]=mapped_column(ForeignKey("memora_users.id",ondelete="CASCADE"),index=True)
 museum_id: Mapped[Optional[str]]=mapped_column(ForeignKey("memora_museums.id",ondelete="CASCADE"),nullable=True,index=True)
 drive_file_id: Mapped[str]=mapped_column(String(255),unique=True,index=True)
 filename: Mapped[str]=mapped_column(String(255))
 mime_type: Mapped[str]=mapped_column(String(100))
 size_bytes: Mapped[int]=mapped_column(BigInteger)
 pos_x: Mapped[float]=mapped_column(Float,default=0)
 wall: Mapped[str]=mapped_column(String(20),default="back")
 created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Presence(Base):
 __tablename__="memora_presence"
 museum_id: Mapped[str]=mapped_column(ForeignKey("memora_museums.id",ondelete="CASCADE"),primary_key=True)
 user_id: Mapped[str]=mapped_column(ForeignKey("memora_users.id",ondelete="CASCADE"),primary_key=True)
 display_name: Mapped[str]=mapped_column(String(255),default="")
 x: Mapped[float]=mapped_column(Float,default=0)
 y: Mapped[float]=mapped_column(Float,default=1.7)
 z: Mapped[float]=mapped_column(Float,default=0)
 updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

engine=None; SessionLocal=None
if ENV["DATABASE_URL"]:
 engine=__import__("sqlalchemy").create_engine(ENV["DATABASE_URL"],pool_pre_ping=True,pool_recycle=300,pool_size=1,max_overflow=0)
 SessionLocal=sessionmaker(bind=engine,expire_on_commit=False,class_=Session)

def need(*names):
 missing=[n for n in names if not ENV.get(n)]
 if missing: raise HTTPException(503,detail="Missing server configuration: "+", ".join(missing))
def get_db():
 if SessionLocal is None: raise HTTPException(503,detail="DATABASE_URL is not configured.")
 with SessionLocal() as db: yield db
def fernet():
 try: return Fernet(ENV["TOKEN_ENCRYPTION_KEY"].encode())
 except Exception: raise HTTPException(503,detail="TOKEN_ENCRYPTION_KEY is invalid.")
def state_serializer():
 return URLSafeTimedSerializer(ENV["SESSION_SECRET"],salt="memora-oauth-state")
def flow(state=None):
 need("GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GOOGLE_REDIRECT_URI","SESSION_SECRET","TOKEN_ENCRYPTION_KEY")
 cfg={"web":{"client_id":ENV["GOOGLE_CLIENT_ID"],"client_secret":ENV["GOOGLE_CLIENT_SECRET"],
 "auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token",
 "redirect_uris":[ENV["GOOGLE_REDIRECT_URI"]]}}
 f=Flow.from_client_config(cfg,scopes=SCOPES,state=state); f.redirect_uri=ENV["GOOGLE_REDIRECT_URI"]; return f
def cookie_token(uid):
 now=int(time.time()); return jwt.encode({"sub":uid,"iat":now,"exp":now+SESSION_SECONDS},ENV["SESSION_SECRET"],algorithm="HS256")
def current_user(request:Request,db:Session=Depends(get_db)):
 need("SESSION_SECRET","TOKEN_ENCRYPTION_KEY")
 token=request.cookies.get(COOKIE)
 if not token: raise HTTPException(401,detail="Sign in with Google first.")
 try: uid=jwt.decode(token,ENV["SESSION_SECRET"],algorithms=["HS256"]).get("sub")
 except jwt.PyJWTError: raise HTTPException(401,detail="Session expired. Sign in again.")
 user=db.get(User,uid)
 if not user: raise HTTPException(401,detail="User session not found.")
 return user
def origin_check(request):
 origin=request.headers.get("origin","").rstrip("/")
 if not APP_ORIGIN or origin != APP_ORIGIN: raise HTTPException(403,detail="Invalid request origin.")
def drive_service(user):
 if not user.refresh_token_encrypted: raise HTTPException(401,detail="Reconnect Google Drive.")
 try: refresh=fernet().decrypt(user.refresh_token_encrypted.encode()).decode()
 except (InvalidToken,ValueError): raise HTTPException(500,detail="Stored Google token could not be decrypted.")
 creds=Credentials(None,refresh_token=refresh,token_uri="https://oauth2.googleapis.com/token",
 client_id=ENV["GOOGLE_CLIENT_ID"],client_secret=ENV["GOOGLE_CLIENT_SECRET"],scopes=SCOPES)
 try: creds.refresh(GoogleRequest())
 except Exception: raise HTTPException(401,detail="Google authorization expired. Reconnect Drive.")
 return build("drive","v3",credentials=creds,cache_discovery=False)
def ensure_folder(service):
 q="name='MEMORA' and mimeType='application/vnd.google-apps.folder' and trashed=false"
 r=service.files().list(q=q,spaces="drive",pageSize=100,fields="files(id,name,createdTime)",orderBy="createdTime").execute()
 if r.get("files"): return r["files"][0]["id"]
 return service.files().create(body={"name":"MEMORA","mimeType":"application/vnd.google-apps.folder"},fields="id").execute()["id"]
def membership(db,museum_id,user_id):
 return db.scalar(select(Membership).where(Membership.museum_id==museum_id,Membership.user_id==user_id))
def museum_access(db,museum_id,user):
 m=db.get(Museum,museum_id)
 if not m or not membership(db,museum_id,user.id): raise HTTPException(404,detail="Museum not found or access denied.")
 return m
def make_photo_json(p):
 return {"id":p.id,"filename":p.filename,"mime_type":p.mime_type,"size_bytes":p.size_bytes,
 "pos_x":p.pos_x,"wall":p.wall,"created_at":p.created_at.isoformat() if p.created_at else None,
 "content_url":f"/api/photos/{p.id}/content"}

@app.get("/api/health")
def health(): return {"status":"ok","service":"memora-api"}

@app.get("/api/auth/google")
def google_login():
 need("APP_ORIGIN","SESSION_SECRET")
 state=state_serializer().dumps({"nonce":secrets.token_urlsafe(24),"created":int(time.time())})
 f=flow(state=state)
 url,_=f.authorization_url(access_type="offline",include_granted_scopes="true",prompt="consent")
 return RedirectResponse(url,302)

@app.get("/api/auth/google/callback")
def google_callback(code:str="",state:str="",error:str="",db:Session=Depends(get_db)):
 need("APP_ORIGIN","SESSION_SECRET","TOKEN_ENCRYPTION_KEY")
 if error: return RedirectResponse(APP_ORIGIN+"/?oauth=cancelled",303)
 if not code or not state: raise HTTPException(400,detail="Missing OAuth code/state.")
 try: state_serializer().loads(state,max_age=600)
 except (BadSignature,SignatureExpired): raise HTTPException(400,detail="OAuth state invalid or expired.")
 f=flow(state=state)
 try:
  f.fetch_token(code=code); creds=f.credentials
  svc=build("oauth2","v2",credentials=creds,cache_discovery=False)
  profile=svc.userinfo().get().execute()
  sub,email=profile.get("id"),profile.get("email")
  if not sub or not email: raise HTTPException(400,detail="Google identity unavailable.")
  user=db.scalar(select(User).where(User.google_sub==sub))
  if not user:
   user=User(id=str(uuid.uuid4()),google_sub=sub,email=email,name=profile.get("name",""),drive_folder_id="")
   db.add(user); db.flush()
  user.email=email; user.name=profile.get("name",user.name)
  if creds.refresh_token: user.refresh_token_encrypted=fernet().encrypt(creds.refresh_token.encode()).decode()
  db.commit(); db.refresh(user)
  service=drive_service(user)
  if not user.drive_folder_id:
   user.drive_folder_id=ensure_folder(service); db.commit()
  response=RedirectResponse(APP_ORIGIN+"/?oauth=success",303)
  response.set_cookie(COOKIE,cookie_token(user.id),httponly=True,secure=COOKIE_SECURE,samesite="lax",max_age=SESSION_SECONDS,path="/")
  return response
 except HTTPException: raise
 except Exception as exc:
  db.rollback()
  raise HTTPException(502,detail="Google sign-in or Drive folder creation failed. Check OAuth scopes and credentials.") from exc

@app.get("/api/me")
def me(user:User=Depends(current_user)):
 return {"id":user.id,"email":user.email,"name":user.name,"drive_connected":bool(user.drive_folder_id and user.refresh_token_encrypted)}

@app.post("/api/auth/logout")
def logout(request:Request):
 origin_check(request); r=Response('{"ok":true}',media_type="application/json")
 r.delete_cookie(COOKIE,path="/",secure=COOKIE_SECURE,httponly=True,samesite="lax"); return r

@app.post("/api/museums")
def create_museum(body:dict,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request)
 name=str(body.get("name","My Memory Museum")).strip()[:120] or "My Memory Museum"
 code=secrets.token_urlsafe(9).replace("-","").replace("_","")[:12].upper()
 m=Museum(id=str(uuid.uuid4()),owner_id=user.id,name=name,wall_color="#c6b9a6",invite_code=code)
 db.add(m); db.flush()
 db.add(Membership(id=str(uuid.uuid4()),museum_id=m.id,user_id=user.id,role="owner"))
 db.commit()
 return {"id":m.id,"name":m.name,"wall_color":m.wall_color,"invite_code":m.invite_code,"role":"owner"}

@app.get("/api/museums")
def list_museums(user:User=Depends(current_user),db:Session=Depends(get_db)):
 rows=db.scalars(select(Membership).where(Membership.user_id==user.id)).all()
 result=[]
 for mem in rows:
  m=db.get(Museum,mem.museum_id)
  if m: result.append({"id":m.id,"name":m.name,"wall_color":m.wall_color,"invite_code":m.invite_code,"role":mem.role})
 return result

@app.get("/api/museums/{museum_id}")
def get_museum(museum_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
 m=museum_access(db,museum_id,user)
 photos=db.scalars(select(Photo).where(Photo.museum_id==m.id).order_by(Photo.created_at)).all()
 return {"id":m.id,"name":m.name,"wall_color":m.wall_color,"invite_code":m.invite_code,
 "photos":[make_photo_json(p) for p in photos]}

@app.patch("/api/museums/{museum_id}")
def update_museum(museum_id:str,body:dict,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request); m=museum_access(db,museum_id,user)
 mem=membership(db,museum_id,user.id)
 if mem.role!="owner": raise HTTPException(403,detail="Only the museum owner can customize this museum.")
 if "name" in body: m.name=str(body["name"]).strip()[:120] or m.name
 if "wall_color" in body:
  color=str(body["wall_color"])
  if len(color)>30: raise HTTPException(400,detail="Invalid wall color.")
  m.wall_color=color
 db.commit()
 return {"id":m.id,"name":m.name,"wall_color":m.wall_color}

@app.post("/api/museums/{museum_id}/invite")
def create_invite(museum_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request); m=museum_access(db,museum_id,user)
 if membership(db,museum_id,user.id).role!="owner": raise HTTPException(403,detail="Only the owner can create invites.")
 return {"invite_code":m.invite_code,"invite_url":f"{APP_ORIGIN}/?join={m.invite_code}"}

@app.post("/api/museums/join")
def join_museum(body:dict,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request); code=str(body.get("invite_code","")).strip().upper()
 m=db.scalar(select(Museum).where(Museum.invite_code==code))
 if not m: raise HTTPException(404,detail="Invitation code is invalid.")
 if not membership(db,m.id,user.id):
  db.add(Membership(id=str(uuid.uuid4()),museum_id=m.id,user_id=user.id,role="viewer")); db.commit()
 return {"id":m.id,"name":m.name,"wall_color":m.wall_color,"role":membership(db,m.id,user.id).role}

@app.post("/api/photos/upload")
async def upload_photo(request:Request,file:UploadFile=File(...),museum_id:Optional[str]=None,
 user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request)
 allowed={"image/jpeg","image/png","image/webp","image/gif"}
 if file.content_type not in allowed: raise HTTPException(415,detail="Use JPG, PNG, WebP or GIF.")
 data=await file.read(MAX_UPLOAD_MB*1024*1024+1)
 if not data: raise HTTPException(400,detail="File is empty.")
 if len(data)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,detail=f"Max upload size is {MAX_UPLOAD_MB} MB.")
 if museum_id:
  museum_access(db,museum_id,user)
 service=drive_service(user)
 safe=(file.filename or "photo").replace("\\","_").replace("/","_")[:200]
 try:
  media=MediaIoBaseUpload(io.BytesIO(data),mimetype=file.content_type,resumable=False)
  uploaded=service.files().create(body={"name":safe,"parents":[user.drive_folder_id],"description":"MEMORA museum photo"},
    media_body=media,fields="id,name,mimeType,size").execute()
  p=Photo(id=str(uuid.uuid4()),owner_id=user.id,museum_id=museum_id,drive_file_id=uploaded["id"],
    filename=uploaded.get("name",safe),mime_type=uploaded.get("mimeType",file.content_type),size_bytes=int(uploaded.get("size",len(data))))
  db.add(p); db.commit(); db.refresh(p)
  return make_photo_json(p)
 except Exception as exc:
  db.rollback()
  raise HTTPException(502,detail="Photo upload failed. Check Google Drive authorization and database connectivity.") from exc

@app.get("/api/photos")
def photos(museum_id:Optional[str]=None,user:User=Depends(current_user),db:Session=Depends(get_db)):
 if museum_id:
  museum_access(db,museum_id,user)
  rows=db.scalars(select(Photo).where(Photo.museum_id==museum_id).order_by(Photo.created_at.desc())).all()
 else:
  rows=db.scalars(select(Photo).where(Photo.owner_id==user.id).order_by(Photo.created_at.desc())).all()
 return [make_photo_json(p) for p in rows]

@app.get("/api/photos/{photo_id}/content")
def photo_content(photo_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
 p=db.get(Photo,photo_id)
 if not p: raise HTTPException(404,detail="Photo not found.")
 if p.museum_id: museum_access(db,p.museum_id,user)
 elif p.owner_id!=user.id: raise HTTPException(404,detail="Photo not found.")
 try:
  raw=drive_service(user if p.owner_id==user.id else db.get(User,p.owner_id)).files().get_media(fileId=p.drive_file_id).execute()
  return Response(content=raw,media_type=p.mime_type,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
 except Exception as exc: raise HTTPException(502,detail="Could not load image from Drive.") from exc

@app.delete("/api/photos/{photo_id}")
def delete_photo(photo_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request); p=db.get(Photo,photo_id)
 if not p: raise HTTPException(404,detail="Photo not found.")
 if p.owner_id!=user.id: raise HTTPException(403,detail="Only the uploader can delete this photo.")
 try: drive_service(user).files().delete(fileId=p.drive_file_id).execute()
 except HttpError as exc:
  if getattr(exc,"status_code",None)!=404: raise HTTPException(502,detail="Drive delete failed.") from exc
 db.delete(p); db.commit(); return {"ok":True}

@app.post("/api/rooms/{museum_id}/presence")
def update_presence(museum_id:str,body:dict,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request); m=museum_access(db,museum_id,user)
 def bounded(key,lo,hi,default):
  try: v=float(body.get(key,default))
  except (ValueError,TypeError): raise HTTPException(400,detail=f"Invalid {key}.")
  if not lo<=v<=hi: raise HTTPException(400,detail=f"{key} out of range.")
  return v
 p=db.get(Presence,(museum_id,user.id))
 if not p:
  p=Presence(museum_id=museum_id,user_id=user.id,display_name=user.name or user.email)
  db.add(p)
 p.x=bounded("x",-5.5,5.5,0); p.y=bounded("y",1.0,2.2,1.7); p.z=bounded("z",-5.5,5.5,0)
 p.updated_at=datetime.now(timezone.utc); db.commit()
 cutoff=datetime.now(timezone.utc)-timedelta(seconds=45)
 rows=db.scalars(select(Presence).where(Presence.museum_id==museum_id,Presence.updated_at>=cutoff)).all()
 return {"visitors":[{"user_id":x.user_id,"name":x.display_name,"x":x.x,"y":x.y,"z":x.z} for x in rows]}

@app.post("/api/rooms/{museum_id}/voice-token")
def voice_token(museum_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
 origin_check(request); museum_access(db,museum_id,user)
 need("LIVEKIT_URL","LIVEKIT_API_KEY","LIVEKIT_API_SECRET")
 room=f"memora-{museum_id}"
 token=livekit_api.AccessToken(ENV["LIVEKIT_API_KEY"],ENV["LIVEKIT_API_SECRET"])
 token.with_identity(user.id).with_name(user.name or user.email).with_grants(
  livekit_api.VideoGrants(room_join=True,room=room,can_publish=True,can_subscribe=True)
 )
 return {"server_url":ENV["LIVEKIT_URL"],"token":token.to_jwt(),"room":room}
