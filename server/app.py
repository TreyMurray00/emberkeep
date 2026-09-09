import hashlib
import json
import logging
import os
import secrets
import time
import uuid
import copy
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import psycopg
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain import ATTRS, CHAPTER_COUNT, DEFAULT_SCENARIO, SKILLS, act, apply_scenario, finalize, log, new_world, side_quest_action, use_consumable, validate_build

ROOT=Path(__file__).resolve().parents[1]
logger=logging.getLogger(__name__)
if (ROOT/'.env').exists():
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k,v=line.split('=',1)
            v=v.strip()
            if len(v)>=2 and v[0]==v[-1] and v[0] in ('"',"'"): v=v[1:-1]
            os.environ.setdefault(k,v)

def db():
    return psycopg.connect(
        os.environ['DATABASE_URL'],
        row_factory=dict_row,
        connect_timeout=int(os.environ.get('DB_CONNECT_TIMEOUT','10')),
        application_name='emberkeep',
    )
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def cipher(): return Fernet(os.environ['SECRET_KEY'].encode())
def secure_cookies():
    configured=os.environ.get('COOKIE_SECURE')
    return configured.lower() in ('1','true','yes') if configured is not None else os.environ.get('APP_ORIGIN','').startswith('https://')

class ExportedSiteFiles(StaticFiles):
    """Serve exported routes such as /admin from their admin.html file."""
    async def get_response(self,path,scope):
        response=await super().get_response(path,scope)
        if response.status_code==404 and path and not Path(path.rstrip('/')).suffix:
            return await super().get_response(path.rstrip('/')+'.html',scope)
        return response

@asynccontextmanager
async def lifespan(app):
    missing=[name for name in ('DATABASE_URL','ADMIN_PASSWORD','SECRET_KEY') if not os.environ.get(name)]
    if missing: raise RuntimeError('Missing required environment variables: '+', '.join(missing))
    cipher()  # Fail startup immediately if SECRET_KEY is not a valid Fernet key.
    with db() as c:
        # Multiple replicas may start together. Serialize idempotent schema setup
        # through Postgres so deployment does not race on a fresh Neon database.
        c.execute("SELECT pg_advisory_xact_lock(hashtext('emberkeep-schema'))")
        c.execute((ROOT/'server/schema.sql').read_text())
        if not c.execute('SELECT version FROM ai_configs LIMIT 1').fetchone():
            c.execute('INSERT INTO ai_configs(config) VALUES (%s)',(Jsonb(dict(mode='template',model='',temperature=0.7,max_tokens=300,voice='af_heart')),))
    yield

app=FastAPI(title='Emberkeep',lifespan=lifespan)
allowed_origins=[origin.strip() for origin in os.environ.get('APP_ORIGIN','http://127.0.0.1:5173').split(',') if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.middleware('http')
async def security(request,call_next):
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

def identity(request,c):
    row=c.execute('SELECT * FROM identities WHERE token_hash=%s',(digest(request.cookies.get('player','')),)).fetchone()
    if not row: raise HTTPException(401,'Join a session first.')
    return row

def admin(request,c):
    row=c.execute('SELECT * FROM admin_tokens WHERE token_hash=%s AND expires_at>now()', (digest(request.cookies.get('admin','')),)).fetchone()
    if not row: raise HTTPException(401,'Administrator sign-in required.')

def view(state,pid,sid):
    own=state['members'][pid]
    result={**{k:v for k,v in state.items() if k not in ['members','commands','seed','scenario','side_quests','chapter_history']},'id':sid,'me':own,
        'members':[{k:v for k,v in m.items() if k not in ['draft','character']} | {'hp':m.get('character',{}).get('hp'), 'max_hp':m.get('character',{}).get('max_hp')} for m in state['members'].values()]}
    result['chapter']=state.get('chapter',1)
    result['chapter_count']=state.get('chapter_count',CHAPTER_COUNT)
    result['chapter_title']=state.get('chapter_title',state.get('title','Adventure'))
    result['side_quests']=[{
        k:({ek:ev for ek,ev in v.items() if ek!='victory'} if k=='encounter' and v else v)
        for k,v in q.items() if k!='completion'
    } for q in state.get('side_quests',[])] if state.get('stage',0)>=1 else []
    scenario=state.get('scenario',{})
    if state.get('enemy_kind')=='side_quest':
        quest=next((q for q in state.get('side_quests',[]) if q['id']==state.get('side_quest_encounter_id')),{})
        encounter=quest.get('encounter',{})
    else: encounter=scenario.get(state.get('enemy_kind') or '',{})
    result['enemy_name']=encounter.get('name','Guardian') if state.get('enemy_hp') else None
    return result

def persist(c,sid,w,command,payload):
    w['version']+=1
    c.execute('UPDATE sessions SET state=%s WHERE id=%s',(Jsonb(w),sid))
    c.execute('INSERT INTO events(session_id,command_id,payload) VALUES (%s,%s,%s)',(sid,command,Jsonb(dict(version=w['version'],state=w,**payload))))
    # Rebuild the small materialized graph exactly so completed chapters cannot leave stale facts behind.
    party_id='system:party'; objective_id='system:objective'; location_id='location:'+w['location']; guide_id='npc:guide'
    nodes=[(party_id,'Party',{}),(objective_id,'Objective',dict(status=w['status'],clues=w['clues'])),(location_id,'Location',dict(name=w['location']))]
    scenario=w.get('scenario',{})
    if w['stage']>=1:nodes.append((guide_id,'NPC',dict(name=scenario.get('guide_name','Sister Elowen'),known_fact=scenario.get('first_discovery',''))))
    if w['stage']>=1:
        for quest in w.get('side_quests',[]): nodes.append(('quest:'+quest['id'],'SideQuest',dict(title=quest['title'],status=quest['status'],objective=quest['objective'],reward=quest['reward'])))
    for m in w['members'].values():
        nodes.append(('character:'+m['id'],'Character',dict(name=m['name'],class_id=m.get('class_id'))))
        for item in m.get('character',{}).get('inventory',[]):nodes.append(('item:'+item['id'],'Item',item))
    c.execute('DELETE FROM relationships WHERE session_id=%s',(sid,))
    c.execute('DELETE FROM entities WHERE session_id=%s',(sid,))
    for id,kind,props in nodes:
        c.execute('INSERT INTO entities VALUES (%s,%s,%s,%s)',(sid,id,kind,Jsonb(props)))
    for m in w['members'].values():
        character_id='character:'+m['id']
        for target,kind in [(party_id,'MEMBER_OF'),(location_id,'LOCATED_IN')]:
            c.execute('INSERT INTO relationships VALUES (%s,%s,%s,%s)',(sid,character_id,target,kind))
        for item in m.get('character',{}).get('inventory',[]):
            c.execute('INSERT INTO relationships VALUES (%s,%s,%s,%s)',(sid,character_id,'item:'+item['id'],'OWNS'))
    if w['stage']>=1:
        c.execute('INSERT INTO relationships VALUES (%s,%s,%s,%s)',(sid,guide_id,objective_id,'KNOWS_ABOUT'))
        for quest in w.get('side_quests',[]): c.execute('INSERT INTO relationships VALUES (%s,%s,%s,%s)',(sid,guide_id,'quest:'+quest['id'],'OFFERS'))

class Join(BaseModel):
    name:str=Field(min_length=1,max_length=32)
    code:str=Field(default='',max_length=12)

join_failures={}

@app.get('/api/health')
def health():
    with db() as c: c.execute('SELECT 1')
    return {'ok':True,'database':'postgresql'}

@app.post('/api/join')
def join(body:Join,request:Request,response:Response):
    name=body.name.strip()
    if not name: raise HTTPException(422,'Enter a character name.')
    token=secrets.token_urlsafe(32); pid=str(uuid.uuid4())
    with db() as c:
        prior=c.execute('SELECT * FROM identities WHERE token_hash=%s',(digest(request.cookies.get('player','')),)).fetchone()
        if prior: raise HTTPException(409,'You already belong to a session in this browser. Sign out first.')
        sid=body.code.strip().upper()
        if sid:
            host=request.client.host if request.client else 'unknown'
            now=time.monotonic()
            recent=[attempt for attempt in join_failures.get(host,[]) if now-attempt<60]
            join_failures[host]=recent
            if len(recent)>=8: raise HTTPException(429,'Too many invalid invitation codes. Wait one minute.')
            row=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(sid,)).fetchone()
            if not row:
                join_failures[host]=recent+[now]
                raise HTTPException(404,'Session code not found.')
            w=row['state']
            if w['status']!='lobby': raise HTTPException(409,'This session is unavailable.')
        else:
            for _ in range(5):
                sid=secrets.token_hex(5).upper(); w=new_world(secrets.randbits(32))
                created=c.execute('INSERT INTO sessions(id,state) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id',(sid,Jsonb(w))).fetchone()
                if created: break
            else: raise HTTPException(503,'Could not allocate a session code. Try again.')
        if len(w['members'])>=4: raise HTTPException(409,'All four seats are occupied.')
        w['members'][pid]=dict(id=pid,name=name,host=not w['members'],ready=False,class_id=None,
            draft=dict(class_id=None,gear='',attributes=dict.fromkeys(ATTRS,8),skills=dict.fromkeys(SKILLS,0)))
        c.execute('INSERT INTO identities VALUES (%s,%s,%s)',(digest(token),pid,sid))
        persist(c,sid,w,str(uuid.uuid4()),dict(type='joined',player=pid))
    response.set_cookie('player',token,httponly=True,secure=secure_cookies(),samesite='strict',max_age=60*60*24*30)
    return view(w,pid,sid)

@app.get('/api/session')
def session(request:Request):
    with db() as c:
        who=identity(request,c); w=c.execute('SELECT state FROM sessions WHERE id=%s',(who['session_id'],)).fetchone()['state']
        result=view(w,who['player_id'],who['session_id'])
        row=c.execute('SELECT config FROM ai_configs WHERE version=%s',(w.get('config_version'),)).fetchone() if w.get('config_version') else None
        cfg=(row or c.execute('SELECT config FROM ai_configs ORDER BY version DESC LIMIT 1').fetchone())['config']
        result['ai_enabled']=cfg.get('mode')!='template'
        result['speech']={'voice':cfg.get('voice','af_heart')}
        return result

@app.post('/api/leave')
def leave(request:Request,response:Response):
    with db() as c:
        who=identity(request,c);sid=who['session_id'];pid=who['player_id']
        w=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(sid,)).fetchone()['state']
        if w['status'] in ('active','generating'): raise HTTPException(409,'Finish this adventure before leaving. Closing the browser preserves your place.')
        if w['status']=='lobby':
            was_host=w['members'][pid]['host'];del w['members'][pid]
            if was_host and w['members']:next(iter(w['members'].values()))['host']=True
            c.execute('DELETE FROM relationships WHERE session_id=%s AND (source=%s OR target=%s)',(sid,pid,pid))
            c.execute('DELETE FROM entities WHERE session_id=%s AND id=%s',(sid,pid))
            persist(c,sid,w,str(uuid.uuid4()),dict(type='left',player=pid))
        c.execute('DELETE FROM identities WHERE token_hash=%s',(who['token_hash'],))
    response.delete_cookie('player',secure=secure_cookies(),samesite='strict');return {'ok':True}

class Command(BaseModel):
    id:str=Field(min_length=8,max_length=80)
    version:int
    type:str
    data:dict=Field(default_factory=dict)

class GeneratedReward(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=80)
    kind:Literal['potion','weapon','supply','quest']
    restores:Literal['hp','mana','stamina'] | None
    restore_amount:int | None=Field(ge=1,le=12)

class GeneratedTrap(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=80)
    location:str=Field(min_length=3,max_length=80)
    intro:str=Field(min_length=20,max_length=500)
    success:str=Field(min_length=20,max_length=500)
    failure:str=Field(min_length=20,max_length=500)
    damage:int=Field(ge=1,le=6)

class GeneratedEnemy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=80)
    location:str=Field(min_length=3,max_length=80)
    intro:str=Field(min_length=20,max_length=500)
    victory:str=Field(min_length=20,max_length=500)
    reward:GeneratedReward

class GeneratedSideQuestEncounter(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=80)
    location:str=Field(min_length=3,max_length=80)
    intro:str=Field(min_length=20,max_length=500)
    victory:str=Field(min_length=20,max_length=500)

class GeneratedBoss(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=80)
    location:str=Field(min_length=3,max_length=80)
    intro:str=Field(min_length=20,max_length=500)
    combat_ending:str=Field(min_length=20,max_length=500)
    reward:GeneratedReward

class GeneratedSideQuest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=3,max_length=80)
    giver:str=Field(min_length=2,max_length=60)
    hook:str=Field(min_length=20,max_length=300)
    objective:str=Field(min_length=12,max_length=180)
    requires_clues:int=Field(ge=1,le=3)
    encounter:GeneratedSideQuestEncounter | None
    completion:str=Field(min_length=20,max_length=500)
    reward:GeneratedReward

class GeneratedScenario(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=3,max_length=80)
    prior_consequence:str | None=Field(min_length=20,max_length=500)
    objective:str=Field(min_length=12,max_length=180)
    start_location:str=Field(min_length=3,max_length=80)
    first_location:str=Field(min_length=3,max_length=80)
    guide_name:str=Field(min_length=2,max_length=60)
    opening:str=Field(min_length=30,max_length=700)
    first_discovery:str=Field(min_length=20,max_length=500)
    search_discoveries:list[str]=Field(min_length=2,max_length=2)
    dungeon_name:str=Field(min_length=3,max_length=80)
    trap:GeneratedTrap
    enemy:GeneratedEnemy
    boss:GeneratedBoss
    side_quests:list[GeneratedSideQuest]=Field(min_length=1,max_length=2)
    peaceful_ending:str=Field(min_length=20,max_length=500)
    failure_ending:str=Field(min_length=20,max_length=500)

    @field_validator('search_discoveries')
    @classmethod
    def valid_search_discoveries(cls,values):
        if any(not 20<=len(value.strip())<=500 for value in values):
            raise ValueError('Each search discovery must contain 20 to 500 characters.')
        return values

    @field_validator('side_quests')
    @classmethod
    def side_quest_encounter_required(cls,values):
        if not any(quest.encounter for quest in values):
            raise ValueError('At least one side quest must include a combat encounter.')
        return values

def _generate_structured_scenario(cfg,key,prompt,avoid_titles=(),consequence_anchors=None):
    schema_object=GeneratedScenario.model_json_schema()
    schema=json.dumps(schema_object,separators=(',',':'))
    if cfg.get('mode')=='local': prompt+=f' Schema: {schema}'
    for attempt in range(2):
        instruction='You are a world generator. Follow the supplied JSON schema exactly. Return one complete, compact JSON object only, with no Markdown or commentary.'
        if attempt: instruction+=' Your previous response was incomplete or invalid; prioritize complete valid JSON over detail.'
        try:
            raw=model_call(cfg,key,prompt,instruction,max_tokens=max(6000,cfg.get('max_tokens',300)),result_limit=12000,json_mode=True,json_schema=schema_object,timeout=90)
            cleaned=raw.strip()
            if cleaned.startswith('```'):
                cleaned=cleaned.split('\n',1)[1] if '\n' in cleaned else cleaned[3:]
                cleaned=cleaned.rsplit('```',1)[0].strip()
            start,end=cleaned.find('{'),cleaned.rfind('}')
            if start>=0 and end>start: cleaned=cleaned[start:end+1]
            result=GeneratedScenario.model_validate(json.loads(cleaned)).model_dump()
            content=json.dumps(result,ensure_ascii=False).casefold()
            forbidden=['ashen bell','emberkeep','sister elowen','cinder gate','whispering cloister','bell chamber','ruined monastery','silver tongue','hollow guardian','bell']
            if any(term in content for term in forbidden): raise ValueError('Generated scenario reused playtest content.')
            if result['title'].casefold().strip() in {title.casefold().strip() for title in avoid_titles}: raise ValueError('Generated title was already used.')
            consequence=result['prior_consequence']
            if consequence_anchors is None:
                if consequence is not None: raise ValueError('Chapter 1 cannot depend on an unplayed chapter.')
            else:
                anchors=[str(anchor).casefold().strip() for anchor in consequence_anchors if str(anchor).strip()]
                if not consequence or not any(anchor in consequence.casefold() for anchor in anchors):
                    raise ValueError('The chapter did not carry forward a recorded consequence.')
                if consequence.casefold() not in result['opening'].casefold():
                    result['opening']=(consequence.strip()+' '+result['opening'].strip())[:700]
            return result
        except (ValueError,httpx.TimeoutException,httpx.NetworkError):
            if attempt: raise

def _chapter_rules():
    return '''Create one named dungeon, one meaningful trap, one enemy encounter, one boss encounter, rewards, and one or two optional NPC side quests. A side quest may include its own combat encounter; at least one side quest must have an encounter, and its objective must mention defeating that enemy. A side-quest reward is granted only when the full quest is turned in. Potion rewards must specify whether they restore hp, mana, or stamina and an amount from 1 to 12; vary the restored resource when it fits the reward. Non-potion rewards must use null for those fields. The fixed rules are: the guide reveals the first clue; two clues can be found by searching; the trap can be disarmed; the enemy and boss can be fought; an undisarmed trap damages only the adventurer who advances into it, so its failure text must describe one adventurer rather than the whole party; three clues unlock a peaceful boss resolution; and eight threat advances cause failure.'''

def generate_scenario(cfg,key,seed,party_size,avoid_titles=()):
    avoided=', '.join(avoid_titles) or 'none'
    prompt=f'''Create Chapter 1 only of an original five-chapter fantasy tabletop scenario for {party_size} adventurer(s).
Use seed {seed} only as creative inspiration. This chapter must establish a main storyline that can continue, but do not create, outline, foreshadow in detail, or return Chapters 2–5. Those chapters will be created only after play completes each preceding chapter.
{_chapter_rules()}
Do not reuse any content, names, locations, objects, creatures, plot devices, or motifs from the built-in playtest. Forbidden terms include: Ashen Bell, Emberkeep, Sister Elowen, Cinder Gate, Whispering Cloister, Bell Chamber, ruined monastery, silver tongue, hollow guardian, and bell. Do not use copyrighted settings or characters.
Previously generated titles that must not be reused: {avoided}.
Set prior_consequence to null. Make the side quests relevant to NPC goals and ensure their rewards fit their objectives. Keep every narrative field compact: one or two sentences and under 80 words. The title is the overall scenario title as well as the Chapter 1 title.
Return only one JSON object matching the supplied schema exactly.'''
    return _generate_structured_scenario(cfg,key,prompt,avoid_titles)

def generate_chapter(cfg,key,seed,party_size,chapter_number,history):
    if not 2<=chapter_number<=CHAPTER_COUNT: raise ValueError('Invalid chapter number.')
    prior=json.dumps(history,ensure_ascii=False,separators=(',',':'))
    prior_titles=[chapter['title'] for chapter in history]
    prompt=f'''Create Chapter {chapter_number} only of a five-chapter fantasy tabletop scenario for {party_size} adventurer(s).
Use seed {seed + chapter_number} only as creative inspiration. This chapter must be a direct continuation of the completed chapters below. Preserve their player choices, victories, peaceful resolutions, completed side quests, earned rewards, injuries, and accumulated pressure. Turn at least one recorded consequence into a location, ally, obstacle, objective, or encounter in this chapter. Do not undo a completed outcome. Do not create, outline, or return any later chapter.
Completed chapter history (authoritative JSON): {prior}
{_chapter_rules()}
Set prior_consequence to one concise cause-and-effect sentence that explicitly names the immediately preceding chapter, its resolution, a completed side quest, an earned reward, or an affected party member from the history. Do not reuse prior chapter titles as this chapter's title: {', '.join(prior_titles)}. Do not reuse content, names, locations, objects, creatures, plot devices, or motifs from the built-in playtest. Forbidden terms include: Ashen Bell, Emberkeep, Sister Elowen, Cinder Gate, Whispering Cloister, Bell Chamber, ruined monastery, silver tongue, hollow guardian, and bell. Do not use copyrighted settings or characters. Keep every narrative field compact: one or two sentences and under 80 words. For Chapter 5, make the boss ending resolve the overall storyline; earlier chapters must end with a consequential development that can drive the next chapter.
Return only one JSON object matching the supplied schema exactly.'''
    latest=history[-1]
    anchors=[latest['title'],latest['resolution'],*latest.get('completed_side_quests',[])]
    for member in latest.get('party',[]): anchors.extend([member.get('name',''),*member.get('rewards',[])])
    return _generate_structured_scenario(cfg,key,prompt,prior_titles,anchors)

def template_chapter(chapter_number,history):
    """Build the deterministic fallback chapter only when play reaches it."""
    themes={
        2:('Ashes on the Road','The Sable Crossing','Captain Ilyra','Ember Warden','Road of Cinders','Find who carried the first chapter’s curse beyond the valley.'),
        3:('The Crown Below','The Drowned Archive','Archivist Pell','Tidebound Judge','Vault of Tides','Recover the history that reveals the enemy behind the spreading curse.'),
        4:('A Kingdom Divided','The Thorn Parliament','Envoy Sera','Briar Regent','Court of Roots','Win an ally and break the power shielding the architect of the curse.'),
        5:('The Last Oath','The Starless Citadel','Keeper Orin','The Oathbreaker','Hall of First Light','End the curse and decide what will replace the power that sustained it.'),
    }
    title,dungeon,guide,boss,location,objective=themes[chapter_number]
    prior=history[-1]
    details=[]
    if prior.get('completed_side_quests'): details.append(f'Their completion of {prior["completed_side_quests"][0]} earned them an ally')
    injured=next((member for member in prior.get('party',[]) if member['hp']<member.get('max_hp',member['hp'])),None)
    if injured: details.append(f'{injured["name"]} still bears injuries from the victory')
    if prior.get('threat'): details.append(f'the threat had advanced {prior["threat"]} times')
    consequence=f'Because the party resolved “{prior["title"]}” by {prior["resolution"]}, its consequences have reached {location}'
    if details: consequence+=', and '+details[0].lower()
    consequence+='.'
    scenario=copy.deepcopy(DEFAULT_SCENARIO)
    scenario.update(title=title,prior_consequence=consequence,objective=objective,start_location=location,first_location=f'{location} Outskirts',
        guide_name=guide,dungeon_name=dungeon,
        opening=f'{consequence} {guide} asks the party to continue the struggle in {dungeon}.',
        first_discovery=f'{guide} studies the evidence carried from the prior chapter and reveals the first clue to the danger within {dungeon}.',
        search_discoveries=[
            f'A hidden record connects the events of {prior["title"]} to the power gathering deeper in {dungeon}.',
            f'A second discovery reveals how the party’s earlier choice can be used against {boss} without repeating the harm it caused.',
        ],
        peaceful_ending=f'The party uses what it learned in earlier chapters to persuade {boss} to yield, changing the course of the wider conflict.',
        failure_ending=f'The danger in {dungeon} overwhelms the party, and the unresolved consequences of earlier chapters spread unchecked.')
    scenario['trap'].update(name=f'{dungeon} Ward',location=f'{dungeon} Threshold',
        intro=f'A reactive ward shaped by the last chapter’s aftermath seals the threshold of {dungeon}. A careful search may disarm it.',
        success='The party reads the pattern left by earlier events, disables the ward, and uncovers another clue.',
        failure='The ward lashes the adventurer who advances through it and alerts the forces ahead.')
    scenario['enemy'].update(name=f'{title} Pursuer',location=f'{dungeon} Approach',
        intro=f'A pursuer empowered by the previous chapter bars the route through {dungeon}.',
        victory='The pursuer falls, and evidence on it shows how the conflict has changed in response to the party.')
    scenario['enemy']['reward']['name']=f'{title} restorative'
    scenario['boss'].update(name=boss,location=f'{dungeon} Heart',
        intro=f'{boss} confronts the party with the accumulated consequences of their journey.',
        combat_ending=(f'{boss} falls, and the five-chapter conflict is finally resolved by the path the party forged.' if chapter_number==CHAPTER_COUNT else f'{boss} falls, but the victory reveals a new consequence that carries the party toward Chapter {chapter_number+1}.'))
    scenario['boss']['reward']['name']=f'{title} relic'
    quest=scenario['side_quests'][0]
    quest.update(title=f'{guide}’s Reckoning',giver=guide,
        hook=f'Help {guide} address a personal cost created by the events of {prior["title"]}.',
        objective=f'Defeat the {title} Echo and discover at least two clues within {dungeon}.',
        completion=f'{guide} accepts how the earlier events changed the world and gives the party aid for the road ahead.')
    quest['encounter'].update(name=f'{title} Echo',location=f'{dungeon} Refuge',
        intro='A hostile echo of the party’s earlier choices guards what the guide needs.',
        victory='The echo disperses, leaving the guide’s objective within reach.')
    quest['reward']['name']=f'{guide}’s aid'
    return scenario

def chapter_outcome(world,resolution,ending):
    return dict(
        number=world.get('chapter',1),title=world.get('chapter_title',world['title']),
        objective=world['objective'],resolution=resolution,ending=ending,
        clues=world['clues'],threat=world['threat'],
        completed_side_quests=[q['title'] for q in world.get('side_quests',[]) if q['status']=='completed'],
        party=[dict(name=m['name'],hp=m['character']['hp'],max_hp=m['character']['max_hp'],rewards=[i['name'] for i in m['character']['inventory'] if i['kind'] in ('quest','potion')]) for m in world['members'].values() if m.get('ready')],
    )

def prepare_chapter_transition(c,world,resolution,ending):
    history=world.setdefault('chapter_history',[])
    history.append(chapter_outcome(world,resolution,ending))
    current=world.get('chapter',1)
    if current>=CHAPTER_COUNT: return None
    next_number=current+1
    row=c.execute('SELECT config,encrypted_key FROM ai_configs WHERE version=%s',(world['config_version'],)).fetchone()
    if not row: raise ValueError('The session AI configuration is no longer available.')
    world['status']='generating'
    world['pending_chapter']=next_number
    return dict(number=next_number,history=copy.deepcopy(history),cfg=row['config'],encrypted_key=row['encrypted_key'],
        seed=world['seed'],party_size=len(world['members']))

def create_pending_chapter(request):
    cfg=request['cfg']
    if cfg.get('mode')=='template': return template_chapter(request['number'],request['history'])
    try:
        key=cipher().decrypt(request['encrypted_key'].encode()).decode() if request['encrypted_key'] else ''
        return generate_chapter(cfg,key,request['seed'],request['party_size'],request['number'],request['history'])
    except Exception:
        logger.exception('Chapter %s generation failed; using deterministic fallback.',request['number'])
        return template_chapter(request['number'],request['history'])

@app.post('/api/command')
def command(body:Command,request:Request):
    generation_request=None
    with db() as c:
        who=identity(request,c); sid=who['session_id']; pid=who['player_id']
        w=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(sid,)).fetchone()['state']
        existing=c.execute('SELECT payload FROM events WHERE session_id=%s AND command_id=%s',(sid,body.id)).fetchone()
        if existing:
            if existing['payload'].get('player')!=pid: raise HTTPException(409,'Command ID already used.')
            return view(w,pid,sid)
        if body.version!=w['version']: raise HTTPException(409,'The party changed. Your view has been refreshed; try again.')
        m=w['members'][pid]; data=body.data; payload=dict(type=body.type,player=pid)
        try:
            if body.type in ['reserve','draft','finalize']:
                if m['ready'] or w['status']!='lobby': raise ValueError('This character is already finalized.')
                if body.type=='reserve':
                    cls=data.get('class_id')
                    if cls not in [cl['id'] for cl in w['classes']]: raise ValueError('Unknown class.')
                    if any(x['class_id']==cls and x['id']!=pid for x in w['members'].values()): raise ValueError('Another player has reserved this class.')
                    m['class_id']=cls; m['draft']['class_id']=cls; m['draft']['gear']=''
                elif body.type=='draft':
                    allowed={'attributes','skills','gear'}
                    draft={**m['draft'],**{k:v for k,v in data.items() if k in allowed}}
                    validate_build(draft); m['draft']=draft
                else:
                    m['character']=finalize(m['draft'],w['classes']); m['ready']=True
            elif body.type=='start':
                if not m['host'] or w['status']!='lobby': raise ValueError('Only the host can start from the lobby.')
                if not all(x['ready'] for x in w['members'].values()): raise ValueError('Every player must finish their character first.')
                cfgrow=c.execute('SELECT * FROM ai_configs ORDER BY version DESC LIMIT 1').fetchone()
                w['config_version']=cfgrow['version']
                w['ai_enabled']=cfgrow['config']['mode']!='template'
                if cfgrow['config']['mode']!='template':
                    key=cipher().decrypt(cfgrow['encrypted_key'].encode()).decode() if cfgrow['encrypted_key'] else ''
                    try:
                        avoid=[row['title'] for row in c.execute('SELECT title FROM generated_scenarios ORDER BY created_at DESC LIMIT 50').fetchall()]
                        for _ in range(2):
                            scenario=generate_scenario(cfgrow['config'],key,w['seed'],len(w['members']),avoid)
                            fingerprint=digest(json.dumps(scenario,sort_keys=True,ensure_ascii=False))
                            title_key=' '.join(scenario['title'].casefold().split())
                            registered=c.execute('INSERT INTO generated_scenarios(fingerprint,title_key,title) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING fingerprint',(fingerprint,title_key,scenario['title'])).fetchone()
                            if registered:
                                apply_scenario(w,scenario,1); break
                            avoid.append(scenario['title'])
                        else: raise ValueError('The provider repeated a prior adventure.')
                    except Exception:
                        logger.exception('Initial adventure generation failed.')
                        raise HTTPException(502,'Adventure generation failed. The model may be busy or may not have returned valid structured data. Your party is still in the lobby; try again.') from None
                else: apply_scenario(w,w['scenario'],1)
                w['status']='active'
                log(w,'Dungeon Master',w['scenario']['opening'])
            elif body.type=='action':
                if not m['ready']: raise ValueError('Finish your character first.')
                text,roll=act(w,pid,data.get('action'))
                entry=log(w,'Dungeon Master',text,roll=roll); payload['entry']=entry
                if w['status']=='complete':
                    resolution='a peaceful resolution' if data.get('action')=='negotiate' else 'victory in combat'
                    generation_request=prepare_chapter_transition(c,w,resolution,text)
            elif body.type=='side_quest':
                if not m['ready']: raise ValueError('Finish your character first.')
                entry=log(w,'Chronicle',side_quest_action(w,pid,data.get('quest_id'))); payload['entry']=entry
            elif body.type in ['use','equip','collect']:
                if not m['ready'] or w['status']!='active': raise ValueError('Enter an active session first.')
                char=m['character']
                if body.type=='collect':
                    item=next((x for x in w['loot'] if x['id']==data.get('item_id')),None)
                    if not item: raise ValueError('That item has already been collected.')
                    char['inventory'].append(item); w['loot'].remove(item)
                    log(w,'Chronicle',f'{m["name"]} collected {item["name"]}.')
                else:
                    item=next((x for x in char['inventory'] if x['id']==data.get('item_id')),None)
                    if not item: raise ValueError('Item not found in your inventory.')
                    if body.type=='use':
                        log(w,'Chronicle',use_consumable(w,pid,item['id']))
                    else:
                        if item['kind']!='weapon': raise ValueError('Only weapons can be equipped in this rules slice.')
                        item['equipped']=not item['equipped']
            else: raise ValueError('Unknown command.')
        except (ValueError,KeyError,TypeError) as e:
            raise HTTPException(422,str(e) if isinstance(e,ValueError) else 'Invalid command data.')
        persist(c,sid,w,body.id,payload)
        result=view(w,pid,sid)
    if not generation_request: return result
    next_chapter=create_pending_chapter(generation_request)
    with db() as c:
        latest=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(sid,)).fetchone()['state']
        if latest.get('status')!='generating' or latest.get('pending_chapter')!=generation_request['number']:
            return view(latest,pid,sid)
        apply_scenario(latest,next_chapter,generation_request['number'])
        latest['status']='active'; latest.pop('pending_chapter',None)
        entry=log(latest,'Dungeon Master',next_chapter['opening'],chapter=latest['chapter'])
        persist(c,sid,latest,'chapter:'+str(uuid.uuid4()),dict(type='chapter_generated',player=pid,entry=entry))
        return view(latest,pid,sid)

class Login(BaseModel): password:str=Field(max_length=256)
attempts={}

@app.post('/api/admin/login')
def login(body:Login,request:Request,response:Response):
    host=request.client.host; now=time.monotonic()
    recent=[t for t in attempts.get(host,[]) if now-t<60]
    if len(recent)>=6: raise HTTPException(429,'Too many attempts. Wait one minute.')
    attempts[host]=recent+[now]
    if not secrets.compare_digest(body.password,os.environ['ADMIN_PASSWORD']): raise HTTPException(401,'Incorrect administrator password.')
    token=secrets.token_urlsafe(32)
    with db() as c: c.execute("INSERT INTO admin_tokens VALUES (%s,now()+interval '8 hours')",(digest(token),))
    response.set_cookie('admin',token,httponly=True,secure=secure_cookies(),samesite='strict',max_age=28800)
    return {'ok':True}

@app.post('/api/admin/logout')
def logout(request:Request,response:Response):
    with db() as c: c.execute('DELETE FROM admin_tokens WHERE token_hash=%s',(digest(request.cookies.get('admin','')),))
    response.delete_cookie('admin',secure=secure_cookies(),samesite='strict'); return {'ok':True}

@app.get('/api/admin/ai')
def config(request:Request):
    with db() as c:
        admin(request,c)
        row=c.execute('SELECT * FROM ai_configs ORDER BY version DESC LIMIT 1').fetchone()
        return {**row['config'],'version':row['version'],'has_key':bool(row['encrypted_key'])}

class Config(BaseModel):
    mode:str='template'
    model:str=Field(default='',max_length=150)
    api_key:str=Field(default='',max_length=512)
    clear_key:bool=False
    temperature:float=Field(default=0.7,ge=0,le=1.5)
    max_tokens:int=Field(default=300,ge=64,le=1000)
    voice:str='af_heart'
    local_url:str='http://127.0.0.1:8080/v1'

def checked(body):
    if body.mode not in ['template','local','openrouter']: raise HTTPException(422,'Unsupported provider.')
    if body.mode!='template' and not body.model.strip(): raise HTTPException(422,'Enter a model identifier.')
    if body.voice not in ['af_heart','am_michael','bf_emma','bm_george']: raise HTTPException(422,'Unsupported voice.')
    try:
        parsed=urlsplit(body.local_url)
        if parsed.scheme!='http' or parsed.hostname not in ['127.0.0.1','localhost'] or not parsed.port or parsed.path.rstrip('/')!='/v1' or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
    except ValueError: raise HTTPException(422,'Local endpoint must be http://127.0.0.1:PORT/v1 or http://localhost:PORT/v1.')
    return body.model_dump(exclude={'api_key','clear_key'})

@app.post('/api/admin/ai')
def save_config(body:Config,request:Request):
    cfg=checked(body)
    with db() as c:
        admin(request,c)
        old=c.execute('SELECT encrypted_key FROM ai_configs ORDER BY version DESC LIMIT 1').fetchone()
        key=cipher().encrypt(body.api_key.encode()).decode() if body.api_key else (None if body.clear_key else old['encrypted_key'])
        if body.mode=='openrouter' and not key: raise HTTPException(422,'Add an API key for OpenRouter.')
        row=c.execute('INSERT INTO ai_configs(config,encrypted_key) VALUES (%s,%s) RETURNING version',(Jsonb(cfg),key)).fetchone()
        return {'ok':True,'version':row['version']}

def model_call(cfg,key,prompt,instruction=None,max_tokens=None,result_limit=4000,json_mode=False,json_schema=None,timeout=60):
    if cfg['mode']=='template': return 'Template DM is ready. No external model is configured.'
    url=cfg.get('local_url','http://127.0.0.1:8080/v1').replace('localhost','127.0.0.1').rstrip('/')+'/chat/completions' if cfg['mode']=='local' else 'https://openrouter.ai/api/v1/chat/completions'
    headers={'Authorization':'Bearer '+key} if key and cfg['mode']=='openrouter' else {}
    output_tokens=max_tokens or cfg['max_tokens']
    if cfg['mode']=='openrouter' and cfg['model']=='openrouter/free': output_tokens=max(800,output_tokens)
    payload=dict(model=cfg['model'],temperature=cfg['temperature'],max_tokens=output_tokens,messages=[
            dict(role='system',content=instruction or 'You narrate a fantasy tabletop game. Describe only the supplied confirmed outcome. Never change numbers, create items, reveal secrets, or add actions. Keep under 100 words.'),
            dict(role='user',content=prompt)])
    if cfg['mode']=='openrouter':
        payload['reasoning']={'exclude':True}
        if cfg['model']=='openrouter/free': payload['reasoning']['effort']='minimal' if json_mode else 'low'
    if json_mode:
        if cfg['mode']=='openrouter' and json_schema:
            payload['response_format']={'type':'json_schema','json_schema':{'name':'adventure','strict':True,'schema':json_schema}}
            payload['plugins']=[{'id':'response-healing'}]
        else: payload['response_format']={'type':'json_object'}
        if cfg['mode']=='openrouter': payload['provider']={'require_parameters':True}
    with httpx.Client(timeout=timeout,follow_redirects=False,trust_env=False) as client:
        r=client.post(url,headers=headers,json=payload)
        r.raise_for_status()
        result=r.json()['choices'][0]['message']['content']
        if not isinstance(result,str) or not result.strip(): raise ValueError('Empty narration')
        return result[:result_limit]

def safe_narration(candidate,fallback):
    if not isinstance(candidate,str): return fallback
    text=candidate.strip()
    markers=(
        "here's a thinking process",'analyze user input','identify constraints',
        'draft - attempt','check constraints','chain of thought','<think>','</think>',
        'analysis:','reasoning:',
    )
    lowered=text.casefold()
    if not text or len(text.split())>100 or any(marker in lowered for marker in markers): return fallback
    return text

class Intent(BaseModel):text:str=Field(min_length=1,max_length=500)

@app.post('/api/interpret')
def interpret(body:Intent,request:Request):
    with db() as c:
        who=identity(request,c)
        w=c.execute('SELECT state FROM sessions WHERE id=%s',(who['session_id'],)).fetchone()['state']
        if w['status']!='active':raise HTTPException(409,'Enter an active session first.')
        cfg=c.execute('SELECT * FROM ai_configs WHERE version=%s',(w['config_version'],)).fetchone()
    actions=['explore','search','attack','spell','negotiate','rest']
    if cfg['config']['mode']!='template':
        try:
            key=cipher().decrypt(cfg['encrypted_key'].encode()).decode() if cfg['encrypted_key'] else ''
            raw=model_call(cfg['config'],key,body.text,'Map the player intent to exactly one supported action: explore, search, attack, spell, negotiate, rest. Return only JSON {"action":"name"}. If ambiguous or unsupported return {"action":"unknown"}. Never execute the action.')
            proposal=json.loads(raw.strip().removeprefix('```json').removesuffix('```').strip())
            if proposal.get('action') in actions:return {'action':proposal['action']}
        except Exception:
            logger.exception('Intent interpretation failed; trying deterministic aliases.')
    text=body.text.lower()
    aliases={'spell':['spell','cast','magic'],'attack':['attack','strike','hit','fight'],'search':['search','inspect','investigate','look'],'explore':['explore','enter','travel','walk','gate','continue'],'negotiate':['negotiate','unbind','true name','persuade'],'rest':['rest','sleep','camp']}
    found=[action for action,words in aliases.items() if any(word in text for word in words)]
    if len(found)==1:return {'action':found[0]}
    raise HTTPException(422,'Try a clear action: explore, search, attack, cast a spell, resolve the threat, or rest.')

@app.post('/api/admin/ai/test')
def test_config(body:Config,request:Request):
    cfg=checked(body)
    with db() as c:
        admin(request,c); old=c.execute('SELECT encrypted_key FROM ai_configs ORDER BY version DESC LIMIT 1').fetchone()
    key=body.api_key or (cipher().decrypt(old['encrypted_key'].encode()).decode() if old['encrypted_key'] and not body.clear_key else '')
    try: model_call(cfg,key,'A traveler arrives at a quiet inn. Greet them in one sentence.')
    except Exception:
        logger.exception('AI connection test failed.')
        raise HTTPException(502,'Connection test failed. Check the model, key, and provider availability.') from None
    return {'ok':True,'message':'Connection succeeded.'}

@app.post('/api/narrate/{entry_id}')
def narrate(entry_id:str,request:Request):
    # Serialize a single narration per session. State resolution remains a separate committed transaction.
    with db() as c:
        who=identity(request,c); sid=who['session_id']
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(sid,))
        w=c.execute('SELECT state FROM sessions WHERE id=%s',(sid,)).fetchone()['state']
        entry=next((x for x in w['journal'] if x['id']==entry_id),None)
        if not entry: raise HTTPException(404,'Narration not found.')
        if 'prose' in entry: return {'text':entry['prose']}
        cfg=c.execute('SELECT * FROM ai_configs WHERE version=%s',(w.get('config_version',1),)).fetchone()
        facts=c.execute("SELECT e.id,e.kind,e.properties FROM relationships r JOIN entities e ON e.session_id=r.session_id AND e.id=r.target WHERE r.session_id=%s AND r.source IN (%s,%s) AND r.kind IN ('LOCATED_IN','MEMBER_OF')",(sid,'character:'+who['player_id'],who['player_id'])).fetchall()
        key=cipher().decrypt(cfg['encrypted_key'].encode()).decode() if cfg['encrypted_key'] else ''
        try:
            candidate=entry['text'] if cfg['config']['mode']=='template' else model_call(cfg['config'],key,json.dumps(dict(confirmed_outcome=entry['text'],visible_context=facts)))
            prose=safe_narration(candidate,entry['text'])
        except Exception:
            logger.exception('Narration generation failed; using confirmed outcome.')
            prose=entry['text']
        # Re-read under the mutation lock so concurrent game commands cannot be overwritten.
        latest=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(sid,)).fetchone()['state']
        for e in latest['journal']:
            if e['id']==entry_id: e['prose']=prose
        c.execute('UPDATE sessions SET state=%s WHERE id=%s',(Jsonb(latest),sid))
        return {'text':prose}

# In a production image the exported Vinext application is copied here. Keeping
# this conditional preserves the existing two-process development workflow.
web_root=ROOT/'web/dist/client'
if web_root.is_dir():
    app.mount('/',ExportedSiteFiles(directory=web_root,html=True),name='web')
