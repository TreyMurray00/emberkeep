"""Versioned, deliberately small homebrew rules for the first playable slice."""
import random
import uuid

ATTRS = ['Might', 'Agility', 'Intellect', 'Resolve']
SKILLS = ['Athletics', 'Stealth', 'Arcana', 'Persuasion']
CHAPTER_COUNT = 5
ARCHETYPES = [
    ('warden', ['Ironbound Warden', 'Ashen Sentinel', 'Oathkeeper'], 'Defender', 'shield', 'Hold the line with steel and stubborn courage.', 'Might', 28, 8, 18),
    ('mage', ['Ember Scholar', 'Veil Arcanist', 'Rune Weaver'], 'Spellcaster', 'sparkles', 'Shape the old magic sleeping beneath the ruins.', 'Intellect', 18, 24, 10),
    ('ranger', ['Thorn Ranger', 'Gloam Stalker', 'Wildstrider'], 'Scout', 'bow', 'Read forgotten trails and strike from the shadows.', 'Agility', 22, 12, 20),
    ('bard', ['Dawn Cantor', 'Echo Bard', 'Silver Envoy'], 'Support', 'music', 'Turn a word, a melody, or a promise into power.', 'Resolve', 22, 18, 14),
]
GEAR = {
    'warden': [('sword', 'Iron longsword'), ('axe', 'Woodland axe')],
    'mage': [('staff', 'Runewood staff'), ('wand', 'Ember wand')],
    'ranger': [('bow', 'Yew shortbow'), ('daggers', 'Twin daggers')],
    'bard': [('lute', 'Travel lute'), ('rapier', 'Silver rapier')],
}

DEFAULT_SCENARIO = {
    'title': 'The Ashen Bell',
    'prior_consequence': None,
    'objective': 'Silence the bell beneath the ruined monastery.',
    'start_location': 'The Cinder Gate',
    'first_location': 'The Whispering Cloister',
    'guide_name': 'Sister Elowen',
    'opening': 'The Cinder Gate stands open. Beyond it, the abandoned monastery watches over Emberkeep. A bell tolls beneath the earth. Before its eighth toll, you must silence it. What will you do?',
    'first_discovery': 'Sister Elowen waits beneath a broken arch. “The bell feeds on fear,” she whispers. “Find its silver tongue, and you can still it.” You discover the first clue.',
    'search_discoveries': [
        'You find a silver inscription: the bell can be unbound with three fragments of its true name. A new clue joins your journal.',
        'Behind a weathered icon, you uncover the final fragment of the bell’s true name. The peaceful rite is now within reach.',
    ],
    'dungeon_name': 'The Ruined Monastery',
    'trap': {'name':'The Tolling Seal','location':'The Sunken Vestry','intro':'Silver wires cross the flooded vestry, each tied to a rusted chime. A careful search may disarm the trap before the party advances.','success':'You trace the wires to their counterweight and silence the trap. A hidden inscription reveals another clue.','failure':'The seal snaps shut on the adventurer who steps through, and its warning chime sounds.','damage':3},
    'enemy': {'name':'Oathbound Husk','location':'The Reliquary Walk','intro':'An oathbound husk blocks the passage into the depths. It raises a corroded spear and attacks.','victory':'The husk collapses, leaving the way to the inner chamber open.','reward':{'name':'Vestry tonic','kind':'potion','restores':'stamina','restore_amount':8}},
    'boss': {'name':'Hollow Guardian','location':'The Bell Chamber','intro':'A hollow guardian rises beside the tolling bell. Its rusted blade scrapes the flagstones. The final encounter begins.','combat_ending':'The guardian falls. You remove the silver tongue; the bell is silent. Dawn returns to Emberkeep.','reward':{'name':'Silver tongue relic','kind':'quest'}},
    'side_quests': [{'title':'Elowen’s Lost Reliquary','giver':'Sister Elowen','hook':'Recover the reliquary stolen by the oathbound dead.','objective':'Defeat the Reliquary Wraith and discover at least two clues in the monastery.','requires_clues':2,'encounter':{'name':'Reliquary Wraith','location':'The Pilgrim Crypt','intro':'A wraith coils around the stolen reliquary and lunges when you enter the crypt.','victory':'The Reliquary Wraith unravels, leaving the stolen reliquary within reach.'},'completion':'You return the reliquary to Sister Elowen and earn her blessing.','reward':{'name':'Elowen’s blessing','kind':'supply'}}],
    'peaceful_ending': 'You speak the bell’s true name. The guardian kneels, its oath fulfilled. The curse dissolves without another blow.',
    'failure_ending': 'The eighth toll echoes across the valley. The ritual is complete; the village must be abandoned.',
}

def class_pool(seed):
    rng = random.Random(seed)
    result = []
    for id, names, role, icon, description, primary, hp, mana, stamina in ARCHETYPES:
        result.append(dict(id=id, name=rng.choice(names), role=role, icon=icon, description=description,
                           primary=primary, hp=hp, mana=mana, stamina=stamina,
                           gear=[dict(id=i, name=n) for i,n in GEAR[id]]))
    rng.shuffle(result)
    return result

def validate_build(draft, final=False):
    for key, fields, budget, minimum, maximum in [('attributes', ATTRS, 8, 8, 14), ('skills', SKILLS, 4, 0, 3)]:
        values = draft.get(key, {})
        if set(values) != set(fields) or any(type(v) is not int or not minimum <= v <= maximum for v in values.values()):
            raise ValueError(f'Invalid {key}.')
        spent = sum(v - minimum for v in values.values())
        if spent > budget or (final and spent != budget):
            raise ValueError(f'Allocate exactly {budget} {key} points.' if final else f'Too many {key} points.')
    if final and (not draft.get('class_id') or draft.get('gear') not in dict(GEAR[draft['class_id']])):
        raise ValueError('Select a class and starter weapon.')

def inventory_item(id, name, kind, quantity=1, equipped=False, restores=None, restore_amount=None):
    item=dict(id=id, name=name, kind=kind, quantity=quantity, equipped=equipped)
    if restores in ('hp','mana','stamina'):
        item['restores']=restores; item['restore_amount']=restore_amount or 8
    return item

def finalize(draft, classes):
    validate_build(draft, True)
    cls = next(c for c in classes if c['id'] == draft['class_id'])
    attrs = draft['attributes']
    return dict(**draft, hp=cls['hp']+attrs['Might']-8, max_hp=cls['hp']+attrs['Might']-8,
        mana=cls['mana']+attrs['Intellect']-8, max_mana=cls['mana']+attrs['Intellect']-8,
        stamina=cls['stamina']+attrs['Agility']-8, max_stamina=cls['stamina']+attrs['Agility']-8,
        inventory=[inventory_item(str(uuid.uuid4()), dict(GEAR[draft['class_id']])[draft['gear']], 'weapon', equipped=True),
                   inventory_item(str(uuid.uuid4()), 'Healing draught', 'potion', 2, restores='hp', restore_amount=8),
                   inventory_item(str(uuid.uuid4()), 'Adventurer’s pack', 'supply')])

def new_world(seed):
    import copy
    scenario=copy.deepcopy(DEFAULT_SCENARIO)
    return dict(version=0, seed=seed, status='lobby', classes=class_pool(seed), members={},
        title=scenario['title'], campaign_title=scenario['title'], chapter_title=scenario['title'],
        chapter=1, chapter_count=CHAPTER_COUNT, chapter_history=[],
        location=scenario['start_location'], stage=0, clues=0, threat=0, enemy_hp=0,
        enemy_kind=None, side_quest_encounter_id=None, trap_resolved=False, turn=0, ai_enabled=False, side_quests=[],
        objective=scenario['objective'], scenario=scenario, journal=[], commands=[],
        loot=[])

def apply_scenario(world, scenario, chapter_number=1):
    world['scenario']=scenario
    world['chapter']=chapter_number
    world['chapter_count']=CHAPTER_COUNT
    world['chapter_title']=scenario['title']
    if chapter_number==1:
        world['campaign_title']=scenario['title']
    world['title']=world.get('campaign_title',scenario['title'])
    world['objective']=scenario['objective']
    world['location']=scenario['start_location']
    world['stage']=0
    world['clues']=0
    world['threat']=0
    world['enemy_hp']=0
    world['turn']=0
    world['trap_resolved']=False
    world['enemy_kind']=None
    world['side_quest_encounter_id']=None
    world['loot']=[]
    world['side_quests']=[{
        **quest,
        'id':str(uuid.uuid4()),
        'status':'available',
        'encounter_status':'pending' if quest.get('encounter') else None,
    } for quest in scenario['side_quests']]

def grant_reward(character, reward):
    restores=reward.get('restores') or ('hp' if reward['kind']=='potion' else None)
    item=inventory_item(str(uuid.uuid4()),reward['name'],reward['kind'],restores=restores,restore_amount=reward.get('restore_amount'))
    character['inventory'].append(item)
    return item

def _first_conscious_turn(world,members):
    world['turn']=next((index for index,member in enumerate(members) if member['character']['hp']>0),0)

def _enemy_retaliation(world,members,char,scenario,rng):
    hit=rng.randint(1,4); char['hp']=max(0,char['hp']-hit)
    if world.get('enemy_kind')=='legacy': foe=scenario.get('guardian_name','Guardian')
    elif world.get('enemy_kind')=='side_quest':
        quest=next((q for q in world.get('side_quests',[]) if q['id']==world.get('side_quest_encounter_id')),{})
        foe=quest.get('encounter',{}).get('name','Enemy')
    else: foe=(scenario['enemy'] if world.get('enemy_kind')=='enemy' else scenario['boss'])['name']
    text=f'{foe} retaliates for {hit} damage.'
    world['turn']=(world['turn']+1)%len(members)
    for _ in members:
        if members[world['turn']]['character']['hp']>0: break
        world['turn']=(world['turn']+1)%len(members)
    if all(m['character']['hp']==0 for m in members):
        world['status']='failed'; text+=' The party falls. '+scenario['failure_ending']
    return text

def use_consumable(world,pid,item_id,rng=None):
    rng=rng or random.SystemRandom()
    if world['status']!='active': raise ValueError('Enter an active session first.')
    members=[m for m in world['members'].values() if m['ready']]
    player=world['members'][pid]; char=player['character']
    if world['enemy_hp'] and members[world['turn'] % len(members)]['id']!=pid:
        raise ValueError('Wait for your initiative turn.')
    if char['hp']<=0: raise ValueError('You are unconscious and cannot use an item.')
    item=next((x for x in char['inventory'] if x['id']==item_id),None)
    if not item or item['kind']!='potion' or item['quantity']<1: raise ValueError('This item cannot be consumed.')
    resource=item.get('restores','hp'); amount=item.get('restore_amount',8)
    if resource not in ('hp','mana','stamina') or type(amount) is not int or amount<1:
        raise ValueError('This consumable has an invalid effect.')
    if char[resource]>=char['max_'+resource]: raise ValueError(f'Your {resource} is already full.')
    before=char[resource]; char[resource]=min(char['max_'+resource],before+amount); restored=char[resource]-before
    item['quantity']-=1
    text=f'{player["name"]} uses {item["name"]}, restoring {restored} {resource.upper()}.'
    if world['enemy_hp']:
        text+=' Using the consumable takes the turn. '+_enemy_retaliation(world,members,char,world.get('scenario',DEFAULT_SCENARIO),rng)
    return text

def side_quest_action(world,pid,quest_id):
    if world['status']!='active': raise ValueError('The session is not active.')
    if world['stage']<1: raise ValueError('Meet the local inhabitants before seeking side work.')
    quest=next((q for q in world.get('side_quests',[]) if q['id']==quest_id),None)
    if not quest: raise ValueError('Side quest not found.')
    if quest['status']=='available':
        if world['enemy_hp']: raise ValueError('Resolve the current encounter before accepting another quest.')
        quest['status']='active'
        accepted=f'{quest["giver"]} offers “{quest["title"]}”: {quest["hook"]} Quest accepted — {quest["objective"]}'
        if not quest.get('encounter'): return accepted
        encounter=quest['encounter']; members=[m for m in world['members'].values() if m['ready']]
        quest['encounter_status']='active'
        world['location']=encounter['location']; world['enemy_hp']=6+3*len(members)
        world['enemy_kind']='side_quest'; world['side_quest_encounter_id']=quest['id']; _first_conscious_turn(world,members)
        return accepted+' '+encounter['intro']
    if quest['status']=='active':
        if world['enemy_hp']: raise ValueError('Resolve the encounter before claiming a quest reward.')
        if quest.get('encounter') and quest.get('encounter_status')!='defeated':
            encounter=quest['encounter']; members=[m for m in world['members'].values() if m['ready']]
            quest['encounter_status']='active'
            world['location']=encounter['location']; world['enemy_hp']=6+3*len(members)
            world['enemy_kind']='side_quest'; world['side_quest_encounter_id']=quest['id']; _first_conscious_turn(world,members)
            return encounter['intro']
        if world['clues']<quest['requires_clues']: raise ValueError(f'Complete the objective first: {quest["objective"]}')
        quest['status']='completed'; item=grant_reward(world['members'][pid]['character'],quest['reward'])
        return f'{quest["completion"]} {world["members"][pid]["name"]} receives {item["name"]}.'
    raise ValueError('This side quest is already complete.')

def log(world, speaker, text, **extra):
    entry=dict(id=str(uuid.uuid4()), speaker=speaker, text=text, **extra)
    world['journal'].append(entry)
    return entry

def act(world, pid, action, rng=None):
    rng = rng or random.SystemRandom()
    if world['status'] != 'active': raise ValueError('The session is not active.')
    scenario=world.get('scenario',DEFAULT_SCENARIO)
    members = [m for m in world['members'].values() if m['ready']]
    player=world['members'][pid]; char=player['character']
    if world['enemy_hp'] and members[world['turn'] % len(members)]['id'] != pid:
        raise ValueError('Wait for your initiative turn.')
    if char['hp'] <= 0: raise ValueError('You are unconscious. Another player can still finish the objective.')
    roll=None
    if action == 'explore':
        if world['enemy_hp']: raise ValueError('Resolve the encounter before exploring.')
        world['stage']+=1
        if world['stage']==1:
            world['location']=scenario['first_location']; world['clues']+=1
            hooks=' '.join(f'{q["giver"]} also offers a side quest: “{q["title"]}.”' for q in world.get('side_quests',[]))
            text=scenario['first_discovery']+' '+hooks
        elif 'trap' not in scenario:
            world['location']=scenario['encounter_location']; world['enemy_hp']=12+6*len(members)
            world['enemy_kind']='legacy'; world['turn']=0; text=scenario['guardian_intro']
        elif world['stage']==2:
            trap=scenario['trap']; world['location']=trap['location']; text=trap['intro']
        elif world['stage']==3:
            trap=scenario['trap']; prefix=''
            if not world.get('trap_resolved'):
                char['hp']=max(0,char['hp']-trap['damage'])
                world['threat']+=1; prefix=f'{trap["failure"]} {player["name"]} takes {trap["damage"]} damage. '
                if all(member['character']['hp']==0 for member in members):
                    world['status']='failed'; return prefix+scenario['failure_ending'],roll
            enemy=scenario['enemy']; world['location']=enemy['location']; world['enemy_hp']=8+4*len(members)
            world['enemy_kind']='enemy'; _first_conscious_turn(world,members); text=prefix+enemy['intro']
        else:
            boss=scenario['boss']; world['location']=boss['location']; world['enemy_hp']=16+7*len(members)
            world['enemy_kind']='boss'; _first_conscious_turn(world,members); text=boss['intro']
    elif action == 'search':
        if world['enemy_hp']: raise ValueError('Resolve the encounter before searching.')
        roll=rng.randint(1,20)
        if roll + char['skills']['Arcana'] >= 9:
            if 'trap' in scenario and world['stage']==2 and not world.get('trap_resolved'):
                world['trap_resolved']=True; discovery=scenario['trap']['success']
            else: discovery=scenario['search_discoveries'][min(max(world['clues']-1,0),1)]
            world['clues']=min(3,world['clues']+1)
            text=discovery
        else: text='Your search reveals nothing useful, and the danger draws closer.'
        world['threat']+=1
    elif action in ['attack','spell']:
        if not world['enemy_hp']: raise ValueError('There is no enemy here.')
        if action=='attack' and not any(i['kind']=='weapon' and i['equipped'] for i in char['inventory']):
            raise ValueError('Equip a weapon before attacking.')
        resource='mana' if action=='spell' else 'stamina'; cost=3 if action=='spell' else 2
        if char[resource]<cost: raise ValueError(f'Not enough {resource}.')
        char[resource]-=cost
        roll=rng.randint(1,20)
        bonus=char['skills']['Arcana' if action=='spell' else 'Athletics']
        damage=(rng.randint(4,8) if action=='spell' else rng.randint(2,6)) + bonus if roll>=6 else 0
        world['enemy_hp']=max(0,world['enemy_hp']-damage)
        text=f'{player["name"]} rolls {roll} and deals {damage} damage. '
        if world['enemy_hp']==0:
            kind=world.get('enemy_kind','boss')
            if kind=='legacy':
                world['status']='complete'; world['enemy_kind']=None; text+=scenario['combat_ending']
            elif kind=='side_quest':
                quest=next((q for q in world.get('side_quests',[]) if q['id']==world.get('side_quest_encounter_id')),None)
                if not quest or not quest.get('encounter'): raise ValueError('The side quest encounter is no longer available.')
                quest['encounter_status']='defeated'; world['enemy_kind']=None; world['side_quest_encounter_id']=None
                text+=quest['encounter']['victory']+' The side quest encounter is complete.'
            else:
                encounter=scenario['enemy'] if kind=='enemy' else scenario['boss']
                item=grant_reward(char,encounter['reward']); world['enemy_kind']=None
                if kind=='enemy': text+=encounter['victory']+f' {player["name"]} receives {item["name"]}.'
                else: world['status']='complete'; text+=encounter['combat_ending']+f' {player["name"]} claims {item["name"]}.'
        else:
            text+=_enemy_retaliation(world,members,char,scenario,rng)
    elif action == 'negotiate':
        if world['clues']<3: raise ValueError('Discover three clues before attempting a peaceful resolution.')
        if 'trap' in scenario and world['stage']<4: raise ValueError('Reach the final encounter before attempting a peaceful resolution.')
        world['status']='complete'; world['enemy_hp']=0; world['enemy_kind']=None
        if 'boss' in scenario:
            item=grant_reward(char,scenario['boss']['reward']); text=scenario['peaceful_ending']+f' {player["name"]} receives {item["name"]}.'
        else: text=scenario['peaceful_ending']
    elif action == 'rest':
        if world['enemy_hp']: raise ValueError('You cannot rest during combat.')
        for m in members:
            c=m['character']
            for r in ['hp','mana','stamina']: c[r]=c['max_'+r]
        world['threat']+=2; text='The party finds a defensible refuge and recovers, but the threat advances twice.'
    else: raise ValueError('Choose one of the supported actions.')
    if world['threat']>=8 and world['status']=='active':
        world['status']='failed'; text+=' '+scenario['failure_ending']
    return text, roll
