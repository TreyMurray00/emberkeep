import concurrent.futures
import random
import uuid
import pytest
from fastapi.testclient import TestClient
from server.app import app,db
from server.domain import DEFAULT_SCENARIO,cast_spell,encounter_health,ensure_spellbooks,equipment_damage_bonus,new_world,finalize,inventory_item,use_consumable,validate_build,act

def generated_fixture(seed='fixed'):
    return {
        'title':f'The Glass Orchard {seed}','prior_consequence':None,'objective':'Break the winter curse consuming a crystal orchard.',
        'start_location':'Briarwatch','first_location':'The Mirrored Grove','guide_name':'Mara Venn',
        'opening':'Frost spreads through a crystal orchard while its terrified keepers beg you to recover the stolen summer seed.',
        'first_discovery':'Mara Venn finds star-shaped tracks beneath a shattered tree and identifies the first sign left by the winter thieves.',
        'search_discoveries':['A warm shard beneath the roots reveals the thieves entered through a buried aqueduct.','Fresh sap marks reveal the ancient phrase that can peacefully wake the captive summer seed.'],
        'dungeon_name':'The Root Vault',
        'trap':{'name':'Glassvine Snare','location':'The Prismatic Gallery','intro':'Nearly invisible glassvines cross the gallery and tighten whenever warm creatures draw near.','success':'You redirect sunlight through a crystal leaf, making every glassvine visible before cutting a safe path.','failure':'The hidden glassvines snap tight around the adventurer who advances and alert everything deeper within the vault.','damage':3},
        'enemy':{'name':'Rime Jackal','location':'The Frozen Aqueduct','intro':'A pack-leading rime jackal prowls from the frozen channel and bars the route forward.','victory':'The rime jackal dissolves into harmless snow, exposing the passage into the root chamber.','reward':{'name':'Thawing tonic','kind':'potion','restores':'hp','restore_amount':8}},
        'boss':{'name':'The Winter Grafter','location':'The Heartroot Chamber','intro':'The Winter Grafter rises above the stolen summer seed, armored in grafted crystal bark.','combat_ending':'The Grafter falls and warmth rushes from the freed seed, restoring the orchard before dawn.','reward':{'name':'Summer seed splinter','kind':'quest','restores':None,'restore_amount':None}},
        'side_quests':[{'title':'The Keeper’s Missing Tools','giver':'Mara Venn','hook':'Recover the crystal pruning tools abandoned when the frozen creatures arrived.','objective':'Defeat the Iceburrow Scavenger and discover at least two clues within the orchard.','requires_clues':2,'encounter':{'name':'Iceburrow Scavenger','location':'The Buried Tool Shed','intro':'An iceburrow scavenger rises over the missing tools and attacks anyone who comes near.','victory':'The scavenger breaks apart, leaving the missing pruning tools exposed.'},'completion':'Mara recovers the tools and promises to cultivate a healing cutting for your journey.','reward':{'name':'Sunfruit cordial','kind':'potion','restores':'mana','restore_amount':8}}],
        'peaceful_ending':'You speak the Heartroot phrase and the Grafter releases the seed willingly, ending the unnatural winter without bloodshed.',
        'failure_ending':'The winter roots reach Briarwatch and seal the orchard beneath permanent ice.',
    }

@pytest.fixture
def ai_generation():
    from psycopg.types.json import Jsonb
    with db() as c:
        version=c.execute('INSERT INTO ai_configs(config) VALUES (%s) RETURNING version',
            (Jsonb(dict(mode='local',model='test',temperature=.7,max_tokens=300)),)).fetchone()['version']
    yield
    with db() as c:c.execute('DELETE FROM ai_configs WHERE version=%s',(version,))

@pytest.fixture
def players(monkeypatch):
    monkeypatch.setattr('server.app.generate_scenario',lambda cfg,key,seed,party_size,avoid_titles=():generated_fixture(seed))
    clients=[TestClient(app) for _ in range(5)]
    for c in clients:c.__enter__()
    ids=[]
    yield clients,ids
    for sid in ids:
        with db() as c:
            for table in ['relationships','entities','events','identities','sessions']:
                c.execute(f'DELETE FROM {table} WHERE '+('id' if table=='sessions' else 'session_id')+'=%s',(sid,))
    with db() as c:c.execute("DELETE FROM generated_scenarios WHERE title LIKE 'Test Adventure %' OR title LIKE 'The Glass Orchard %'")
    for c in clients:c.__exit__(None,None,None)

def join(c,name='Tester',code=''):
    r=c.post('/api/join',json=dict(name=name,code=code));assert r.status_code==200,r.text;return r.json()

def send(c,type,data=None,id=None,version=None):
    if version is None:version=c.get('/api/session').json()['version']
    return c.post('/api/command',json=dict(id=id or str(uuid.uuid4()),version=version,type=type,data=data or {}))

def build(c,cls,command_id=None):
    assert send(c,'reserve',{'class_id':cls}).status_code==200
    w=c.get('/api/session').json();chosen=next(x for x in w['classes'] if x['id']==cls);gear=chosen['gear'][0]['id']
    draft=dict(gear=gear,spells=[spell['id'] for spell in chosen['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
    assert send(c,'draft',draft).status_code==200
    return send(c,'finalize',id=command_id)

def test_four_seats_and_private_drafts(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id'])
    for i in range(1,4):join(cs[i],f'Player{i}',w['id'])
    assert cs[4].post('/api/join',json=dict(name='Fifth',code=w['id'])).status_code==409
    view=cs[0].get('/api/session').json()
    assert len(view['members'])==4
    assert 'scenario' not in view
    assert all('draft' not in m and 'character' not in m for m in view['members'])
    assert cs[0].get('/api/admin/ai').status_code==401

def test_simultaneous_class_claim(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);join(cs[1],code=w['id'])
    v=cs[0].get('/api/session').json()['version']
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda c:send(c,'reserve',{'class_id':'warden'},version=v),cs[:2]))
    assert sorted(r.status_code for r in results)==[200,409]
    owner=next(c for c,r in zip(cs,results) if r.status_code==200)
    other=cs[1] if owner is cs[0] else cs[0]
    assert send(other,'reserve',{'class_id':'warden'}).status_code==422

def test_finalize_retry_and_unique_loot(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);join(cs[1],code=w['id'])
    finalize_id=str(uuid.uuid4())
    first=build(cs[0],'warden',finalize_id)
    assert first.status_code==200
    retry=send(cs[0],'finalize',id=finalize_id,version=0)
    assert retry.status_code==200
    assert retry.json()['me']['character']['inventory']==first.json()['me']['character']['inventory']
    assert build(cs[1],'mage').status_code==200
    assert send(cs[0],'finalize').status_code==422
    assert send(cs[0],'start').status_code==200
    with db() as c:
        state=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(w['id'],)).fetchone()['state']
        state['loot'].append(dict(id='test-relic',name='Test relic',kind='quest',quantity=1,equipped=False))
        from psycopg.types.json import Jsonb
        c.execute('UPDATE sessions SET state=%s WHERE id=%s',(Jsonb(state),w['id']))
    cmd=str(uuid.uuid4());r=send(cs[0],'collect',{'item_id':'test-relic'},id=cmd)
    assert r.status_code==200
    assert send(cs[0],'collect',{'item_id':'test-relic'},id=cmd,version=0).status_code==200
    assert send(cs[1],'collect',{'item_id':'test-relic'}).status_code==422
    inv=cs[0].get('/api/session').json()['me']['character']['inventory']
    assert len([x for x in inv if x['id']=='test-relic'])==1
    with db() as c:
        assert c.execute("SELECT count(*) AS n FROM relationships WHERE session_id=%s AND kind IN ('LOCATED_IN','MEMBER_OF')",(w['id'],)).fetchone()['n']==4
        saved=c.execute('SELECT payload FROM events WHERE session_id=%s ORDER BY id DESC LIMIT 1',(w['id'],)).fetchone()['payload']['state']
        assert saved['members'][w['me']['id']]['character']['inventory']==inv

def test_invalid_build_and_premature_start(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id'])
    assert send(cs[0],'start').status_code==422
    assert send(cs[0],'action',{'action':'explore'}).status_code==422
    assert send(cs[0],'draft',{'attributes':dict(Might=99,Agility=8,Intellect=8,Resolve=8)}).status_code==422
    assert cs[0].post('/api/join',json=dict(name='Again')).status_code==409
    cross_origin=cs[0].post('/api/admin/login',json=dict(password='wrong'),headers={'origin':'https://test-client.example'})
    assert cross_origin.status_code==401
    assert 'access-control-allow-origin' not in cross_origin.headers
    preflight=cs[0].options('/api/admin/login',headers={
        'origin':'https://another-test-client.example',
        'access-control-request-method':'POST',
    })
    assert preflight.status_code==400
    assert 'access-control-allow-origin' not in preflight.headers

def test_inventory_consumption_atomic_retry(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);build(cs[0],'warden');send(cs[0],'start')
    with db() as c:
        c.execute("UPDATE sessions SET state=jsonb_set(state,ARRAY['members',%s,'character','hp'],'1'::jsonb) WHERE id=%s",(w['me']['id'],w['id']))
    item=cs[0].get('/api/session').json()['me']['character']['inventory'][1]
    cmd=str(uuid.uuid4());assert send(cs[0],'use',{'item_id':item['id']},id=cmd).status_code==200
    assert send(cs[0],'use',{'item_id':item['id']},id=cmd,version=0).status_code==200
    char=cs[0].get('/api/session').json()['me']['character']
    assert char['hp']==9 and char['inventory'][1]['quantity']==1

@pytest.mark.parametrize(('resource','starting'),[('hp',1),('mana',0),('stamina',0)])
def test_consumables_restore_each_character_resource(resource,starting):
    class FixedDice:
        def randint(self,a,b):return 1
    w=new_world(7);draft=dict(class_id='warden',gear='sword',spells=[spell['id'] for spell in next(c for c in w['classes'] if c['id']=='warden')['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
    char=finalize(draft,w['classes']);char[resource]=starting
    potion=inventory_item('resource-tonic','Resource tonic','potion',restores=resource,restore_amount=6)
    char['inventory'].append(potion);w['members']['a']=dict(id='a',name='A',ready=True,character=char)
    w['status']='active';w['enemy_hp']=10;w['enemy_kind']='enemy'
    text=use_consumable(w,'a',potion['id'],FixedDice())
    expected=min(char['max_'+resource],starting+6)-(1 if resource=='hp' else 0)
    assert char[resource]==expected
    assert potion['quantity']==0
    assert 'takes the turn' in text and 'retaliates for 1 damage' in text

def test_combat_consumable_advances_to_next_player():
    class FixedDice:
        def randint(self,a,b):return 1
    w=new_world(8)
    for pid,cls in [('a','warden'),('b','mage')]:
        draft=dict(class_id=cls,gear=dict(warden='sword',mage='staff')[cls],spells=[spell['id'] for spell in next(c for c in w['classes'] if c['id']==cls)['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
        w['members'][pid]=dict(id=pid,name=pid.upper(),ready=True,character=finalize(draft,w['classes']))
    char=w['members']['a']['character'];char['mana']=0
    potion=inventory_item('mana-tonic','Mana tonic','potion',restores='mana',restore_amount=5);char['inventory'].append(potion)
    w['status']='active';w['enemy_hp']=10;w['enemy_kind']='enemy';w['turn']=0
    use_consumable(w,'a',potion['id'],FixedDice())
    assert w['turn']==1
    with pytest.raises(ValueError,match='initiative turn'):use_consumable(w,'a',char['inventory'][1]['id'],FixedDice())

def test_new_encounters_skip_unconscious_players():
    from server.domain import side_quest_action
    w=new_world(9)
    for pid,cls,gear in [('a','warden','sword'),('b','mage','staff')]:
        draft=dict(class_id=cls,gear=gear,spells=[spell['id'] for spell in next(c for c in w['classes'] if c['id']==cls)['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
        w['members'][pid]=dict(id=pid,name=pid.upper(),ready=True,character=finalize(draft,w['classes']))
    w['members']['a']['character']['hp']=0;w['status']='active';w['stage']=3
    act(w,'b','explore')
    assert w['enemy_kind']=='boss' and w['turn']==1
    w['enemy_hp']=0;w['enemy_kind']=None;w['stage']=1;w['side_quests']=[{
        **DEFAULT_SCENARIO['side_quests'][0],'id':'quest','status':'available','encounter_status':'pending'}]
    side_quest_action(w,'b','quest')
    assert w['enemy_kind']=='side_quest' and w['turn']==1

def test_encounters_scale_with_total_party_members():
    expected={'side_quest':(9,18),'enemy':(12,24),'legacy':(18,36),'boss':(23,44)}
    for kind,(solo_hp,four_player_hp) in expected.items():
        assert encounter_health(kind,1)==solo_hp
        assert encounter_health(kind,4)==four_player_hp
        assert four_player_hp>solo_hp

def test_world_generation_and_endings():
    signatures=[]
    for seed in range(20):
        w=new_world(seed);assert len({c['id'] for c in w['classes']})==4
        assert w['classes']==new_world(seed)['classes']
        signatures.append(tuple((c['name'],c['hp'],c['mana'],c['stamina'],tuple(g['name'] for g in c['gear'])) for c in w['classes']))
    assert len(set(signatures))>10
    w=new_world(1);draft=dict(class_id='warden',gear='sword',spells=[spell['id'] for spell in next(c for c in w['classes'] if c['id']=='warden')['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
    w['members']['a']=dict(id='a',name='A',ready=True,character=finalize(draft,w['classes']))
    w['status']='active';w['clues']=3;w['stage']=4
    act(w,'a','negotiate');assert w['status']=='complete'
    w['status']='active';w['threat']=6
    act(w,'a','rest');assert w['status']=='failed'

def test_spellbooks_exist_before_character_selection_and_backfill_old_worlds():
    first=new_world(101);second=new_world(101)
    assert all(len(cls['spells'])==4 for cls in first['classes'])
    first['classes'][0]['spells'][0]['name']='Changed locally'
    assert second['classes'][0]['spells'][0]['name']!='Changed locally'

    legacy=new_world(102)
    legacy['classes'][0].pop('spells')
    legacy['classes'][1]['spells']=[]
    assert ensure_spellbooks(legacy)
    assert len(legacy['classes'][0]['spells'])==4
    assert len(legacy['classes'][1]['spells'])==4
    assert not ensure_spellbooks(legacy)

def test_resumed_lobby_backfills_spellbooks_before_selection(players):
    cs,ids=players;joined=join(cs[0]);ids.append(joined['id'])
    with db() as c:
        state=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(joined['id'],)).fetchone()['state']
        for cls in state['classes']: cls.pop('spells',None)
        from psycopg.types.json import Jsonb
        c.execute('UPDATE sessions SET state=%s WHERE id=%s',(Jsonb(state),joined['id']))

    resumed=cs[0].get('/api/session').json()
    assert all(len(cls['spells'])==4 for cls in resumed['classes'])
    with db() as c:
        saved=c.execute('SELECT state FROM sessions WHERE id=%s',(joined['id'],)).fetchone()['state']
    assert all(len(cls['spells'])==4 for cls in saved['classes'])

def test_equipped_gear_contributes_resources_and_damage():
    class HighDice:
        def randint(self,a,b): return b
    w=new_world(31);cls=w['classes'][0];gear=cls['gear'][0]
    draft=dict(class_id=cls['id'],gear=gear['id'],spells=[spell['id'] for spell in cls['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
    char=finalize(draft,w['classes'])
    assert equipment_damage_bonus(char)==gear['damage_bonus']
    assert char['max_'+gear['resource']]==char['base_max_'+gear['resource']]+gear['resource_bonus']
    w['members']['a']=dict(id='a',name='A',ready=True,character=char)
    w['status']='active';w['enemy_hp']=100;w['enemy_kind']='enemy'
    act(w,'a','attack',HighDice())
    assert w['enemy_hp']==100-(6+char['skills']['Athletics']+gear['damage_bonus'])

def test_equipping_recalculates_resource_bonus(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);build(cs[0],'warden');send(cs[0],'start')
    before=cs[0].get('/api/session').json()['me']['character'];weapon=next(item for item in before['inventory'] if item['kind']=='weapon')
    resource=weapon['resource'];bonus=weapon['resource_bonus']
    assert send(cs[0],'equip',{'item_id':weapon['id']}).status_code==200
    unequipped=cs[0].get('/api/session').json()['me']['character']
    assert unequipped['max_'+resource]==before['max_'+resource]-bonus
    assert send(cs[0],'equip',{'item_id':weapon['id']}).status_code==200
    equipped=cs[0].get('/api/session').json()['me']['character']
    assert equipped['max_'+resource]==before['max_'+resource]

def test_class_spells_require_slots_and_apply_targets():
    class HighDice:
        def randint(self,a,b): return b
    w=new_world(41)
    mage=next(cls for cls in w['classes'] if cls['id']=='mage')
    warden=next(cls for cls in w['classes'] if cls['id']=='warden')
    mage_spells=['ember_bolt','arcane_mending']
    mage_draft=dict(class_id='mage',gear='staff',spells=mage_spells,attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=2,Persuasion=0))
    warden_draft=dict(class_id='warden',gear='sword',spells=['guardian_word','rallying_light'],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
    mage_char=finalize(mage_draft,w['classes']);warden_char=finalize(warden_draft,w['classes'])
    warden_char['hp']=1
    w['members']={'mage':dict(id='mage',name='Mage',ready=True,character=mage_char),'warden':dict(id='warden',name='Warden',ready=True,character=warden_char)}
    w['status']='active'
    text,_=cast_spell(w,'mage','arcane_mending','warden',HighDice())
    assert warden_char['hp']==min(warden_char['max_hp'],1+6+mage_char['skills']['Arcana'])
    assert 'Warden' in text
    with pytest.raises(ValueError,match='no enemy'):cast_spell(w,'mage','ember_bolt','enemy',HighDice())
    invalid={**mage_draft,'spells':['ember_bolt']}
    with pytest.raises(ValueError,match='exactly two'):validate_build(invalid,True)

def test_invalid_bool_points():
    with pytest.raises(ValueError):validate_build(dict(attributes=dict(Might=True,Agility=8,Intellect=8,Resolve=8),skills={}))

def test_generated_scenario_is_validated(monkeypatch):
    import json
    from server.app import generate_scenario
    candidate=generated_fixture()
    monkeypatch.setattr('server.app.model_call',lambda *args,**kwargs:'```json\n'+json.dumps(candidate)+'\n```')
    result=generate_scenario({'max_tokens':300},'secret',42,2)
    assert result['title']=='The Glass Orchard fixed'
    assert result['search_discoveries']==candidate['search_discoveries']

def test_later_chapter_generation_receives_completed_outcomes(monkeypatch):
    import json
    from server.app import generate_chapter
    candidate=generated_fixture('chapter-two');candidate['prior_consequence']='The First Trial ended peacefully, opening a safer road north.';captured={}
    def respond(cfg,key,prompt,*args,**kwargs):
        captured['prompt']=prompt
        return json.dumps(candidate)
    monkeypatch.setattr('server.app.model_call',respond)
    history=[dict(number=1,title='The First Trial',objective='Protect the crossing.',
        resolution='a peaceful resolution',ending='The rival yielded.',clues=3,threat=2,
        completed_side_quests=['A Lost Promise'],party=[dict(name='A',hp=17,rewards=['Moon key'])])]
    result=generate_chapter({'mode':'openrouter','model':'test','max_tokens':300},'secret',42,1,2,history)
    assert result['title']==candidate['title']
    assert 'Create Chapter 2 only' in captured['prompt']
    assert 'The First Trial' in captured['prompt']
    assert 'a peaceful resolution' in captured['prompt']
    assert 'Do not create, outline, or return any later chapter' in captured['prompt']

def test_later_chapter_rejects_an_unanchored_consequence(monkeypatch):
    import json
    from server.app import generate_chapter
    candidate=generated_fixture('unrelated');candidate['prior_consequence']='An unrelated storm creates an entirely separate problem.'
    monkeypatch.setattr('server.app.model_call',lambda *args,**kwargs:json.dumps(candidate))
    history=[dict(number=1,title='The First Trial',objective='Protect the crossing.',resolution='victory in combat',
        ending='The rival fell.',clues=2,threat=1,completed_side_quests=[],party=[])]
    with pytest.raises(ValueError,match='carry forward'):
        generate_chapter({'mode':'openrouter','model':'test','max_tokens':300},'secret',42,1,2,history)

def test_fifth_chapter_completion_is_the_scenario_ending():
    from server.app import prepare_chapter_transition
    w=new_world(42)
    draft=dict(class_id='warden',gear='sword',spells=[spell['id'] for spell in next(c for c in w['classes'] if c['id']=='warden')['spells'][:2]],attributes=dict(Might=10,Agility=10,Intellect=10,Resolve=10),skills=dict(Athletics=1,Stealth=1,Arcana=1,Persuasion=1))
    w['members']['a']=dict(id='a',name='A',ready=True,character=finalize(draft,w['classes']))
    w['chapter']=5;w['chapter_title']='The Final Chapter';w['status']='complete'
    assert prepare_chapter_transition(None,w,'victory in combat','The final enemy falls.') is None
    assert w['status']=='complete' and w['chapter']==5
    assert len(w['chapter_history'])==1 and w['chapter_history'][0]['number']==5

def test_generation_retries_an_empty_model_response(monkeypatch):
    import json
    from server.app import generate_scenario
    candidate=generated_fixture('retry');calls=[]
    def respond(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1: raise ValueError('Empty narration')
        return json.dumps(candidate)
    monkeypatch.setattr('server.app.model_call',respond)
    assert generate_scenario({'mode':'openrouter','model':'openrouter/free','max_tokens':300},'secret',42,1)['title']==candidate['title']
    assert len(calls)==2 and calls[-1]['json_schema']['type']=='object'

def test_initial_generation_does_not_hold_session_lock(players,monkeypatch,ai_generation):
    cs,ids=players; w=join(cs[0]); ids.append(w['id']); build(cs[0],'warden')
    def generate(*args,**kwargs):
        with db() as c:
            pending=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE NOWAIT',(w['id'],)).fetchone()['state']
            assert pending['status']=='generating' and pending['pending_chapter']==1
        return generated_fixture('unlocked')
    monkeypatch.setattr('server.app.generate_scenario',generate)
    result=send(cs[0],'start')
    assert result.status_code==200 and result.json()['generation_source']=='ai'
    assert result.json()['chapter_title']=='The Glass Orchard unlocked'

def test_abandoned_generation_recovers_on_session_read(players):
    import time
    from psycopg.types.json import Jsonb
    cs,ids=players; w=join(cs[0]); ids.append(w['id']); build(cs[0],'warden')
    with db() as c:
        state=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE',(w['id'],)).fetchone()['state']
        state.update(status='generating',pending_chapter=1,generation_started_at=time.time()-500)
        c.execute('UPDATE sessions SET state=%s WHERE id=%s',(Jsonb(state),w['id']))
    recovered=cs[0].get('/api/session').json()
    assert recovered['status']=='active' and recovered['generation_source']=='fallback'
    assert recovered['chapter']==1 and recovered['journal'][-1]['text']==DEFAULT_SCENARIO['opening']
    assert cs[0].get('/api/session').json()['version']==recovered['version']

def test_host_fallback_wins_over_late_provider_result(players,monkeypatch,ai_generation):
    cs,ids=players; w=join(cs[0]); ids.append(w['id']); build(cs[0],'warden')
    def generate(*args,**kwargs):
        fallback=cs[0].post('/api/generation/fallback',json={})
        assert fallback.status_code==200 and fallback.json()['generation_source']=='fallback'
        return generated_fixture('too-late')
    monkeypatch.setattr('server.app.generate_scenario',generate)
    response=send(cs[0],'start')
    assert response.status_code==200 and response.json()['generation_source']=='fallback'
    assert response.json()['chapter_title'].startswith('The Ashen Bell')

def test_generated_scenario_rejects_playtest_content(monkeypatch):
    import json
    from server.app import generate_scenario
    monkeypatch.setattr('server.app.model_call',lambda *args,**kwargs:json.dumps(DEFAULT_SCENARIO))
    with pytest.raises(ValueError):generate_scenario({'max_tokens':300},'secret',42,2)

def test_admin_key_encryption_and_redaction(players):
    import os
    cs,_=players;c=cs[0]
    assert c.post('/api/admin/login',json={'password':os.environ['ADMIN_PASSWORD']}).status_code==200
    baseline=c.get('/api/admin/ai').json()
    r=c.post('/api/admin/ai',json=dict(mode='openrouter',model='test/model',api_key='test-secret-never-return-this'))
    assert r.status_code==200
    version=r.json()['version']
    try:
        result=c.get('/api/admin/ai')
        assert result.json()['has_key'] is True
        assert 'test-secret' not in result.text and 'encrypted_key' not in result.text
        with db() as conn:
            stored=conn.execute('SELECT encrypted_key FROM ai_configs WHERE version=%s',(version,)).fetchone()['encrypted_key']
            assert stored and 'test-secret' not in stored
        assert c.post('/api/admin/ai',json=dict(mode='other',model='x')).status_code==422
        assert c.post('/api/admin/logout',json={}).status_code==200
        assert c.get('/api/admin/ai').status_code==401
    finally:
        with db() as conn:conn.execute('DELETE FROM ai_configs WHERE version=%s',(version,))

def test_leave_releases_class(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);join(cs[1],code=w['id'])
    send(cs[0],'reserve',dict(class_id='warden'))
    assert cs[0].post('/api/leave',json={}).status_code==200
    assert send(cs[1],'reserve',dict(class_id='warden')).status_code==200
    assert cs[1].get('/api/session').json()['me']['host'] is True

def test_provider_failure_preserves_committed_outcome(players,monkeypatch):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);build(cs[0],'warden');send(cs[0],'start')
    entry=cs[0].get('/api/session').json()['journal'][-1]
    before=cs[0].get('/api/session').json()['version']
    def fail(*args,**kwargs):raise RuntimeError('Simulated provider outage')
    monkeypatch.setattr('server.app.model_call',fail)
    with db() as c:
        from psycopg.types.json import Jsonb
        version=c.execute('INSERT INTO ai_configs(config) VALUES (%s) RETURNING version',(Jsonb(dict(mode='local',model='test',temperature=.7,max_tokens=100)),)).fetchone()['version']
        c.execute("UPDATE sessions SET state=jsonb_set(state,'{config_version}',%s::jsonb) WHERE id=%s",(str(version),w['id']))
    try:result=cs[0].post('/api/narrate/'+entry['id'],json={})
    finally:
        with db() as c:c.execute('DELETE FROM ai_configs WHERE version=%s',(version,))
    assert result.status_code==200 and result.json()['text']==entry['text']
    assert cs[0].get('/api/session').json()['version']==before

def test_narration_rejects_reasoning_and_overlong_output():
    from server.app import safe_narration
    fallback='Mira offers the party a quest to recover her heirloom.'
    assert safe_narration("Here's a thinking process: analyze user input.",fallback)==fallback
    assert safe_narration('word '*101,fallback)==fallback
    narration='Mira explains that a rogue spirit stole her heirloom. The party accepts her request to recover it.'
    assert safe_narration(narration,fallback)==narration

def test_openrouter_reasoning_is_excluded(monkeypatch):
    from server.app import model_call
    captured={}
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':'A concise narration.'}}]}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,headers,json):captured.update(json);return Response()
    monkeypatch.setattr('server.app.httpx.Client',Client)
    cfg=dict(mode='openrouter',model='openrouter/free',temperature=.7,max_tokens=300)
    assert model_call(cfg,'secret','prompt')=='A concise narration.'
    assert captured['reasoning']=={'exclude':True,'effort':'low'}

def test_openrouter_generation_uses_strict_schema_with_minimal_reasoning(monkeypatch):
    from server.app import model_call
    captured={}
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':'{}'}}]}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,headers,json):captured.update(json);return Response()
    monkeypatch.setattr('server.app.httpx.Client',Client)
    cfg=dict(mode='openrouter',model='openrouter/free',temperature=.7,max_tokens=300)
    assert model_call(cfg,'secret','prompt',json_mode=True,json_schema={'type':'object'})=='{}'
    assert captured['reasoning']=={'exclude':True,'effort':'minimal'}
    assert captured['response_format']['type']=='json_schema'
    assert captured['response_format']['json_schema']['strict'] is True
    assert captured['plugins']==[{'id':'response-healing'}]

def test_four_player_combat_completion_advances_to_next_chapter(players,monkeypatch):
    class FixedDice:
        def randint(self,a,b):return b
    monkeypatch.setattr('server.domain.random.SystemRandom',FixedDice)
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);observed=[]
    from server.app import create_pending_chapter as real_create_pending_chapter
    def create_without_session_lock(request):
        with db() as c:
            pending=c.execute('SELECT state FROM sessions WHERE id=%s FOR UPDATE NOWAIT',(w['id'],)).fetchone()['state']
            observed.append((pending['status'],pending['pending_chapter']))
        return real_create_pending_chapter(request)
    monkeypatch.setattr('server.app.create_pending_chapter',create_without_session_lock)
    for c in cs[1:4]:join(c,code=w['id'])
    for c,cls in zip(cs,['warden','mage','ranger','bard']):assert build(c,cls).status_code==200
    assert send(cs[0],'start').status_code==200
    assert send(cs[0],'action',dict(action='explore')).status_code==200
    assert send(cs[0],'action',dict(action='explore')).status_code==200
    assert send(cs[0],'action',dict(action='search')).status_code==200
    assert send(cs[0],'action',dict(action='search')).status_code==200
    assert send(cs[0],'action',dict(action='explore')).status_code==200
    clients={c.get('/api/session').json()['me']['id']:c for c in cs[:4]}
    def defeat_current_enemy():
        for _ in range(16):
            state=cs[0].get('/api/session').json()
            if not state['enemy_hp']:return
            actor=state['members'][state['turn']]['id']
            other=next(c for id,c in clients.items() if id!=actor)
            assert send(other,'action',dict(action='attack')).status_code==422
            assert send(clients[actor],'action',dict(action='attack')).status_code==200
        pytest.fail('Encounter did not finish.')
    defeat_current_enemy()
    assert send(cs[0],'action',dict(action='explore')).status_code==200
    defeat_current_enemy()
    state=cs[0].get('/api/session').json()
    assert state['status']=='active'
    assert state['chapter']==2 and state['chapter_count']==5
    assert 'chapter_history' not in state
    assert state['chapter_title']=='Ashes on the Road'
    assert state['stage']==0 and state['clues']==0 and state['threat']==0
    assert observed==[('generating',2)]
    with db() as c:
        saved=c.execute('SELECT state FROM sessions WHERE id=%s',(w['id'],)).fetchone()['state']
        assert c.execute("SELECT count(*) AS n FROM relationships WHERE session_id=%s AND kind='OFFERS'",(w['id'],)).fetchone()['n']==0
        assert c.execute("SELECT count(*) AS n FROM entities WHERE session_id=%s AND kind='SideQuest'",(w['id'],)).fetchone()['n']==0
    assert len(saved['chapter_history'])==1
    assert saved['chapter_history'][0]['resolution']=='victory in combat'

def test_side_quest_awards_generated_reward(players,monkeypatch):
    class FixedDice:
        def randint(self,a,b):return b
    monkeypatch.setattr('server.domain.random.SystemRandom',FixedDice)
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);build(cs[0],'warden');send(cs[0],'start')
    assert cs[0].get('/api/session').json()['side_quests']==[]
    send(cs[0],'action',dict(action='explore'))
    quest=cs[0].get('/api/session').json()['side_quests'][0]
    assert 'completion' not in quest
    reward_name=quest['reward']['name']
    accepted=send(cs[0],'side_quest',{'quest_id':quest['id']})
    assert accepted.status_code==200
    assert accepted.json()['side_quests'][0]['status']=='active',accepted.json()
    assert accepted.json()['enemy_name']==quest['encounter']['name']
    assert 'victory' not in accepted.json()['side_quests'][0]['encounter']
    fought=accepted
    for _ in range(4):
        if not fought.json()['enemy_hp']: break
        fought=send(cs[0],'action',dict(action='attack'))
        assert fought.status_code==200
    assert fought.json()['side_quests'][0]['encounter_status']=='defeated'
    send(cs[0],'action',dict(action='search'))
    result=send(cs[0],'side_quest',{'quest_id':quest['id']})
    assert result.status_code==200
    assert any(i['name']==reward_name for i in result.json()['me']['character']['inventory']),result.json()

def test_undisarmed_trap_damages_only_triggering_adventurer(players):
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);join(cs[1],'Scout',w['id'])
    build(cs[0],'warden');build(cs[1],'ranger');send(cs[0],'start')
    send(cs[0],'action',dict(action='explore'))
    send(cs[0],'action',dict(action='explore'))
    first_before=cs[0].get('/api/session').json()['me']['character']['hp']
    second_before=cs[1].get('/api/session').json()['me']['character']['hp']
    triggered=send(cs[1],'action',dict(action='explore'))
    assert triggered.status_code==200
    assert cs[0].get('/api/session').json()['me']['character']['hp']==first_before
    assert triggered.json()['me']['character']['hp']==second_before-generated_fixture()['trap']['damage']
    assert 'Scout takes 3 damage' in triggered.json()['journal'][-1]['text']

def test_text_intent_and_endpoint_validation(players):
    import os
    cs,ids=players;w=join(cs[0]);ids.append(w['id']);build(cs[0],'warden');send(cs[0],'start')
    assert cs[0].post('/api/interpret',json={'text':'I search the ruins'}).json()['action']=='search'
    assert cs[0].post('/api/interpret',json={'text':'Delete the database'}).status_code==422
    cs[0].post('/api/admin/login',json={'password':os.environ['ADMIN_PASSWORD']})
    assert cs[0].post('/api/admin/ai',json=dict(mode='local',model='x',local_url='http://169.254.169.254:80/v1')).status_code==422

def test_invalid_invitation_codes_are_rate_limited(monkeypatch):
    monkeypatch.setattr('server.app.join_failures',{})
    with TestClient(app) as client:
        for _ in range(8): assert client.post('/api/join',json={'name':'Scout','code':'0000000000'}).status_code==404
        assert client.post('/api/join',json={'name':'Scout','code':'0000000000'}).status_code==429
