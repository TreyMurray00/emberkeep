"""Versioned, deliberately small homebrew rules for the first playable slice."""
import copy
import random
import uuid

ATTRS = ['Might', 'Agility', 'Intellect', 'Resolve']
SKILLS = ['Athletics', 'Stealth', 'Arcana', 'Persuasion']
CHAPTER_COUNT = 5
ENCOUNTER_HEALTH = {
    'side_quest': (6, 3),
    'enemy': (8, 4),
    'legacy': (12, 6),
    'boss': (16, 7),
}
ARCHETYPES = [
    ('warden', ['Ironbound Warden', 'Ashen Sentinel', 'Oathkeeper', 'Stone Vanguard'], 'Defender', 'shield', ['Hold the line with an oath-forged defense.', 'Turn endurance and discipline into a living bulwark.', 'Guard the company with steel and stubborn courage.'], 'Might', 28, 8, 18),
    ('mage', ['Ember Scholar', 'Veil Arcanist', 'Rune Weaver', 'Star Scribe'], 'Spellcaster', 'sparkles', ['Shape unstable runes into decisive magic.', 'Read the hidden laws of the world and rewrite them in flame.', 'Trade endurance for a deep well of arcane power.'], 'Intellect', 18, 24, 10),
    ('ranger', ['Thorn Ranger', 'Gloam Stalker', 'Wildstrider', 'Mist Hunter'], 'Scout', 'bow', ['Read forgotten trails and strike from the shadows.', 'Outlast the wilds and loose a weapon before danger closes.', 'Turn speed, distance, and sharp senses into an advantage.'], 'Agility', 22, 12, 20),
    ('bard', ['Dawn Cantor', 'Echo Bard', 'Silver Envoy', 'Oath Singer'], 'Support', 'music', ['Turn a word, melody, or promise into power.', 'Steady companions and unmake enemies with resonant magic.', 'Carry old stories whose verses alter the present.'], 'Resolve', 22, 18, 14),
]
GEAR = {
    'warden': [
        ('sword', ['Iron longsword', 'Oathsteel blade', 'Sunken keep sword'], 2, 'hp', 3),
        ('axe', ['Woodland axe', 'Gatebreaker axe', 'Ashwood cleaver'], 3, 'stamina', 2),
    ],
    'mage': [
        ('staff', ['Runewood staff', 'Star-map staff', 'Glassroot staff'], 2, 'mana', 4),
        ('wand', ['Ember wand', 'Stormglass wand', 'Veil-carved wand'], 3, 'mana', 2),
    ],
    'ranger': [
        ('bow', ['Yew shortbow', 'Mistwood bow', 'Thornstring bow'], 3, 'stamina', 3),
        ('daggers', ['Twin daggers', 'Moonlit knives', 'Wayfinder blades'], 2, 'hp', 2),
    ],
    'bard': [
        ('lute', ['Travel lute', 'Echoing cittern', 'Dawnwood lute'], 2, 'mana', 3),
        ('rapier', ['Silver rapier', 'Courtly thorn', 'Whispersteel rapier'], 3, 'stamina', 2),
    ],
}
SPELLS = {
    'warden': [
        dict(id='oath_smite',name='Oath Smite',kind='damage',target='enemy',cost=3,power=4,description='Strike the active enemy with radiant force.'),
        dict(id='guardian_word',name='Guardian Word',kind='ward',target='self_or_ally',cost=2,power=3,description='Reduce the target’s next incoming hit.'),
        dict(id='rallying_light',name='Rallying Light',kind='heal',target='self_or_ally',cost=3,power=7,description='Restore health to yourself or an ally.'),
        dict(id='iron_vow',name='Iron Vow',kind='buff',target='self_or_ally',cost=2,power=3,description='Add damage to the target’s next attack or damaging spell.'),
    ],
    'mage': [
        dict(id='ember_bolt',name='Ember Bolt',kind='damage',target='enemy',cost=3,power=6,description='Hurl concentrated fire at the active enemy.'),
        dict(id='gravity_bind',name='Gravity Bind',kind='debuff',target='enemy',cost=3,power=3,description='Reduce the enemy’s next retaliation.'),
        dict(id='arcane_mending',name='Arcane Mending',kind='heal',target='self_or_ally',cost=3,power=6,description='Knit wounds with controlled arcane energy.'),
        dict(id='starward',name='Starward',kind='ward',target='self_or_ally',cost=2,power=4,description='Shield a party member from the next hit.'),
    ],
    'ranger': [
        dict(id='thorn_volley',name='Thorn Volley',kind='damage',target='enemy',cost=3,power=5,description='Drive spectral thorns into the active enemy.'),
        dict(id='binding_roots',name='Binding Roots',kind='debuff',target='enemy',cost=2,power=2,description='Entangle the enemy and weaken its next retaliation.'),
        dict(id='trail_medicine',name='Trail Medicine',kind='heal',target='self_or_ally',cost=2,power=5,description='Restore health with swift wilderness magic.'),
        dict(id='hunter_mark',name='Hunter’s Mark',kind='buff',target='self_or_ally',cost=2,power=4,description='Empower the target’s next damaging action.'),
    ],
    'bard': [
        dict(id='shattering_note',name='Shattering Note',kind='damage',target='enemy',cost=3,power=5,description='Rend the active enemy with a piercing chord.'),
        dict(id='discordant_refrain',name='Discordant Refrain',kind='debuff',target='enemy',cost=2,power=3,description='Disrupt the enemy’s next retaliation.'),
        dict(id='song_of_mending',name='Song of Mending',kind='heal',target='self_or_ally',cost=3,power=7,description='Restore health with a steadying verse.'),
        dict(id='marching_chorus',name='Marching Chorus',kind='buff',target='self_or_ally',cost=2,power=3,description='Add damage to the target’s next damaging action.'),
    ],
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
    for id, names, role, icon, descriptions, primary, hp, mana, stamina in ARCHETYPES:
        # Each table receives a stable random draw: refreshing preserves the
        # choices, while a new session seed produces a different class pool.
        spread=[rng.randint(-2,2) for _ in range(3)]
        gear=[]
        for gear_id,gear_names,damage_bonus,resource,resource_bonus in GEAR[id]:
            gear.append(dict(id=gear_id,name=rng.choice(gear_names),damage_bonus=damage_bonus,
                resource_bonus=resource_bonus,resource=resource,
                effect=f'+{damage_bonus} damage · +{resource_bonus} max {resource}'))
        result.append(dict(id=id, name=rng.choice(names), role=role, icon=icon, description=rng.choice(descriptions),
                           primary=primary, hp=max(16,hp+spread[0]), mana=max(6,mana+spread[1]), stamina=max(8,stamina+spread[2]),
                           gear=gear,spells=copy.deepcopy(SPELLS[id])))
    rng.shuffle(result)
    return result

def ensure_class_loadouts(world):
    """Backfill spellbooks and starter gear in worlds saved by older builds."""
    changed=False
    for cls in world.get('classes',[]):
        class_id=cls.get('id')
        spells=SPELLS.get(class_id)
        if spells and not cls.get('spells'):
            cls['spells']=copy.deepcopy(spells)
            changed=True
        definitions={gear[0]: gear for gear in GEAR.get(class_id, [])}
        for item in cls.get('gear',[]):
            definition=definitions.get(item.get('id'))
            if not definition: continue
            if not isinstance(item.get('name'), str) or not item['name'].strip():
                item['name']=definition[1][0]
                changed=True
            for key,value in [('damage_bonus',definition[2]),('resource',definition[3]),('resource_bonus',definition[4])]:
                if item.get(key) is None:
                    item[key]=value
                    changed=True
            effect=f'+{item["damage_bonus"]} damage · +{item["resource_bonus"]} max {item["resource"]}'
            if item.get('effect') != effect:
                item['effect']=effect
                changed=True
    return changed

def ensure_spellbooks(world):
    """Compatibility wrapper for callers that only need the old migration."""
    return ensure_class_loadouts(world)

def validate_build(draft, final=False):
    for key, fields, budget, minimum, maximum in [('attributes', ATTRS, 8, 8, 14), ('skills', SKILLS, 4, 0, 3)]:
        values = draft.get(key, {})
        if set(values) != set(fields) or any(type(v) is not int or not minimum <= v <= maximum for v in values.values()):
            raise ValueError(f'Invalid {key}.')
        spent = sum(v - minimum for v in values.values())
        if spent > budget or (final and spent != budget):
            raise ValueError(f'Allocate exactly {budget} {key} points.' if final else f'Too many {key} points.')
    valid_gear={gear[0] for gear in GEAR.get(draft.get('class_id'),[])}
    if final and (not draft.get('class_id') or draft.get('gear') not in valid_gear):
        raise ValueError('Select a class and starter weapon.')
    selected_spells=draft.get('spells',[])
    valid_spells={spell['id'] for spell in SPELLS.get(draft.get('class_id'),[])}
    if not isinstance(selected_spells,list) or any(not isinstance(spell,str) for spell in selected_spells) or len(selected_spells)!=len(set(selected_spells)) or any(spell not in valid_spells for spell in selected_spells):
        raise ValueError('Select valid class spells.')
    if final and len(selected_spells)!=2: raise ValueError('Prepare exactly two spells.')
    if not final and len(selected_spells)>2: raise ValueError('You have only two spell slots.')

def inventory_item(id, name, kind, quantity=1, equipped=False, restores=None, restore_amount=None,
                   damage_bonus=0,resource=None,resource_bonus=0):
    item=dict(id=id, name=name, kind=kind, quantity=quantity, equipped=equipped)
    if damage_bonus: item['damage_bonus']=damage_bonus
    if resource in ('hp','mana','stamina') and resource_bonus:
        item['resource']=resource; item['resource_bonus']=resource_bonus
    if restores in ('hp','mana','stamina'):
        item['restores']=restores; item['restore_amount']=restore_amount or 8
    return item

def sync_equipment_stats(character):
    """Apply equipped resource bonuses while preserving current damage/spend."""
    for item in character.get('inventory',[]):
        if item.get('kind')=='weapon':
            # Upgrade weapons from sessions created before equipment bonuses
            # were introduced when they are next equipped or unequipped.
            item.setdefault('damage_bonus',2)
            item.setdefault('resource','stamina')
            item.setdefault('resource_bonus',1)
    for resource in ('hp','mana','stamina'):
        base_key='base_max_'+resource
        if base_key not in character: character[base_key]=character['max_'+resource]
        old_max=character['max_'+resource]
        bonus=sum(item.get('resource_bonus',0) for item in character.get('inventory',[])
            if item.get('equipped') and item.get('resource')==resource)
        new_max=character[base_key]+bonus
        character[resource]=max(0,min(new_max,character[resource]+new_max-old_max))
        character['max_'+resource]=new_max

def equipment_damage_bonus(character):
    return sum(item.get('damage_bonus',2 if item.get('kind')=='weapon' else 0)
        for item in character.get('inventory',[]) if item.get('equipped'))

def finalize(draft, classes):
    validate_build(draft, True)
    cls = next(c for c in classes if c['id'] == draft['class_id'])
    attrs = draft['attributes']
    selected=next(g for g in cls['gear'] if g['id']==draft['gear'])
    definition=next(g for g in GEAR[draft['class_id']] if g[0]==draft['gear'])
    damage_bonus=selected.get('damage_bonus',definition[2])
    resource=selected.get('resource',definition[3])
    resource_bonus=selected.get('resource_bonus',definition[4])
    character=dict(**draft, hp=cls['hp']+attrs['Might']-8, max_hp=cls['hp']+attrs['Might']-8,
        mana=cls['mana']+attrs['Intellect']-8, max_mana=cls['mana']+attrs['Intellect']-8,
        stamina=cls['stamina']+attrs['Agility']-8, max_stamina=cls['stamina']+attrs['Agility']-8,
        inventory=[inventory_item(str(uuid.uuid4()), selected['name'], 'weapon', equipped=True,
                    damage_bonus=damage_bonus,resource=resource,resource_bonus=resource_bonus),
                   inventory_item(str(uuid.uuid4()), 'Healing draught', 'potion', 2, restores='hp', restore_amount=8),
                   inventory_item(str(uuid.uuid4()), 'Adventurer’s pack', 'supply')])
    for resource in ('hp','mana','stamina'): character['base_max_'+resource]=character['max_'+resource]
    sync_equipment_stats(character)
    return character

def new_world(seed):
    scenario=copy.deepcopy(DEFAULT_SCENARIO)
    return dict(version=0, seed=seed, status='lobby', classes=class_pool(seed), members={},
        title=scenario['title'], campaign_title=scenario['title'], chapter_title=scenario['title'],
        chapter=1, chapter_count=CHAPTER_COUNT, chapter_history=[],
        location=scenario['start_location'], stage=0, clues=0, threat=0, enemy_hp=0, enemy_max_hp=0,
        enemy_kind=None, enemy_effects={}, encounter_party_size=0, side_quest_encounter_id=None, trap_resolved=False, turn=0, ai_enabled=False, side_quests=[],
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
    world['enemy_max_hp']=0
    world['encounter_party_size']=0
    world['turn']=0
    world['trap_resolved']=False
    world['enemy_kind']=None
    world['enemy_effects']={}
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
    item=inventory_item(str(uuid.uuid4()),reward['name'],reward['kind'],restores=restores,restore_amount=reward.get('restore_amount'),
        damage_bonus=2 if reward['kind']=='weapon' else 0,resource='stamina' if reward['kind']=='weapon' else None,
        resource_bonus=1 if reward['kind']=='weapon' else 0)
    character['inventory'].append(item)
    return item

def _first_conscious_turn(world,members):
    world['enemy_effects']={}
    world['turn']=next((index for index,member in enumerate(members) if member['character']['hp']>0),0)

def encounter_health(kind, party_size):
    """Return encounter health scaled to the full party present when combat starts."""
    if kind not in ENCOUNTER_HEALTH: raise ValueError('Unknown encounter type.')
    base, per_member=ENCOUNTER_HEALTH[kind]
    return base + per_member * max(1, int(party_size))

def _start_encounter(world,members,kind):
    party_size=len(members)
    hp=encounter_health(kind,party_size)
    world['enemy_hp']=hp
    world['enemy_max_hp']=hp
    world['encounter_party_size']=party_size
    world['enemy_kind']=kind
    _first_conscious_turn(world,members)

def _finish_encounter(world):
    world['enemy_hp']=0
    world['enemy_max_hp']=0
    world['encounter_party_size']=0
    world['enemy_kind']=None
    world['enemy_effects']={}

def _enemy_retaliation(world,members,char,scenario,rng):
    raw_hit=rng.randint(1,4)
    effects=char.setdefault('effects',{})
    weakened=world.setdefault('enemy_effects',{}).pop('weaken',0)
    ward=effects.pop('ward',0)
    hit=max(0,raw_hit-weakened-ward); char['hp']=max(0,char['hp']-hit)
    if world.get('enemy_kind')=='legacy': foe=scenario.get('guardian_name','Guardian')
    elif world.get('enemy_kind')=='side_quest':
        quest=next((q for q in world.get('side_quests',[]) if q['id']==world.get('side_quest_encounter_id')),{})
        foe=quest.get('encounter',{}).get('name','Enemy')
    else: foe=(scenario['enemy'] if world.get('enemy_kind')=='enemy' else scenario['boss'])['name']
    prevented=raw_hit-hit
    text=f'{foe} retaliates for {hit} damage.'
    if prevented: text+=f' Magic prevents {prevented} damage.'
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

def cast_spell(world,pid,spell_id,target_id=None,rng=None):
    rng=rng or random.SystemRandom()
    if world['status']!='active': raise ValueError('The session is not active.')
    members=[m for m in world['members'].values() if m['ready']]
    caster=world['members'][pid]; char=caster['character']
    if world['enemy_hp'] and members[world['turn'] % len(members)]['id']!=pid:
        raise ValueError('Wait for your initiative turn.')
    if char['hp']<=0: raise ValueError('You are unconscious and cannot cast a spell.')
    prepared=char.get('spells',[])
    available=SPELLS.get(char['class_id'],[])
    spell=next((entry for entry in available if entry['id']==spell_id and entry['id'] in prepared),None)
    if not spell: raise ValueError('Choose one of your prepared spells.')
    if char['mana']<spell['cost']: raise ValueError('Not enough mana.')
    if spell['target']=='enemy':
        if not world['enemy_hp']: raise ValueError('There is no enemy to target.')
        target=None
    else:
        target=next((member for member in members if member['id']==(target_id or pid)),None)
        if not target: raise ValueError('Choose yourself or a party member as the target.')
        if target['character']['hp']<=0 and spell['kind']!='heal': raise ValueError('Only healing can target an unconscious ally.')
        if spell['kind']=='heal' and target['character']['hp']>=target['character']['max_hp']:
            raise ValueError('That target is already at full health.')
    char['mana']-=spell['cost']
    roll=None
    if spell['kind']=='damage':
        roll=rng.randint(1,20)
        buff=char.setdefault('effects',{}).pop('damage',0)
        gear_bonus=equipment_damage_bonus(char)
        damage=spell['power']+char['skills']['Arcana']+gear_bonus+buff if roll>=6 else 0
        world['enemy_hp']=max(0,world['enemy_hp']-damage)
        text=f'{caster["name"]} casts {spell["name"]}, rolls {roll}, and deals {damage} damage.'
    elif spell['kind']=='heal':
        target_char=target['character']; before=target_char['hp']
        target_char['hp']=min(target_char['max_hp'],before+spell['power']+char['skills']['Arcana'])
        restored=target_char['hp']-before
        text=f'{caster["name"]} casts {spell["name"]} on {target["name"]}, restoring {restored} HP.'
    elif spell['kind']=='buff':
        effects=target['character'].setdefault('effects',{})
        effects['damage']=max(effects.get('damage',0),spell['power'])
        text=f'{caster["name"]} casts {spell["name"]} on {target["name"]}. Their next damaging action gains +{spell["power"]} damage.'
    elif spell['kind']=='ward':
        effects=target['character'].setdefault('effects',{})
        effects['ward']=max(effects.get('ward',0),spell['power'])
        text=f'{caster["name"]} casts {spell["name"]} on {target["name"]}. Their next incoming hit is reduced by {spell["power"]}.'
    else:
        effects=world.setdefault('enemy_effects',{})
        effects['weaken']=max(effects.get('weaken',0),spell['power'])
        text=f'{caster["name"]} casts {spell["name"]}. The enemy’s next retaliation is reduced by {spell["power"]}.'
    if spell['kind']=='damage' and world['enemy_hp']==0:
        kind=world.get('enemy_kind','boss')
        if kind=='side_quest':
            quest=next((q for q in world.get('side_quests',[]) if q['id']==world.get('side_quest_encounter_id')),None)
            if not quest or not quest.get('encounter'): raise ValueError('The side quest encounter is no longer available.')
            quest['encounter_status']='defeated';_finish_encounter(world);world['side_quest_encounter_id']=None
            text+=' '+quest['encounter']['victory']+' The side quest encounter is complete.'
        elif kind=='legacy':
            world['status']='complete';_finish_encounter(world);text+=' '+world['scenario']['combat_ending']
        else:
            encounter=world['scenario']['enemy'] if kind=='enemy' else world['scenario']['boss']
            item=grant_reward(char,encounter['reward']);_finish_encounter(world)
            if kind=='enemy': text+=' '+encounter['victory']+f' {caster["name"]} receives {item["name"]}.'
            else: world['status']='complete';text+=' '+encounter['combat_ending']+f' {caster["name"]} claims {item["name"]}.'
    elif world['enemy_hp']:
        text+=' Casting takes the turn. '+_enemy_retaliation(world,members,char,world.get('scenario',DEFAULT_SCENARIO),rng)
    return text,roll

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
        world['location']=encounter['location']; world['side_quest_encounter_id']=quest['id']
        _start_encounter(world,members,'side_quest')
        return accepted+' '+encounter['intro']
    if quest['status']=='active':
        if world['enemy_hp']: raise ValueError('Resolve the encounter before claiming a quest reward.')
        if quest.get('encounter') and quest.get('encounter_status')!='defeated':
            encounter=quest['encounter']; members=[m for m in world['members'].values() if m['ready']]
            quest['encounter_status']='active'
            world['location']=encounter['location']; world['side_quest_encounter_id']=quest['id']
            _start_encounter(world,members,'side_quest')
            return encounter['intro']
        if world['clues']<quest['requires_clues']: raise ValueError(f'Complete the objective first: {quest["objective"]}')
        quest['status']='completed'; item=grant_reward(world['members'][pid]['character'],quest['reward'])
        return f'{quest["completion"]} {world["members"][pid]["name"]} receives {item["name"]}.'
    raise ValueError('This side quest is already complete.')

def log(world, speaker, text, **extra):
    entry=dict(id=str(uuid.uuid4()), speaker=speaker, text=text, **extra)
    world['journal'].append(entry)
    return entry

def act(world, pid, action, rng=None, spell_id=None, target_id=None):
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
            world['location']=scenario['encounter_location']; _start_encounter(world,members,'legacy'); text=scenario['guardian_intro']
        elif world['stage']==2:
            trap=scenario['trap']; world['location']=trap['location']; text=trap['intro']
        elif world['stage']==3:
            trap=scenario['trap']; prefix=''
            if not world.get('trap_resolved'):
                char['hp']=max(0,char['hp']-trap['damage'])
                world['threat']+=1; prefix=f'{trap["failure"]} {player["name"]} takes {trap["damage"]} damage. '
                if all(member['character']['hp']==0 for member in members):
                    world['status']='failed'; return prefix+scenario['failure_ending'],roll
            enemy=scenario['enemy']; world['location']=enemy['location']; _start_encounter(world,members,'enemy'); text=prefix+enemy['intro']
        else:
            boss=scenario['boss']; world['location']=boss['location']; _start_encounter(world,members,'boss'); text=boss['intro']
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
    elif action=='spell':
        return cast_spell(world,pid,spell_id,target_id,rng)
    elif action=='attack':
        if not world['enemy_hp']: raise ValueError('There is no enemy here.')
        if not any(i['kind']=='weapon' and i['equipped'] for i in char['inventory']):
            raise ValueError('Equip a weapon before attacking.')
        resource='stamina'; cost=2
        if char[resource]<cost: raise ValueError(f'Not enough {resource}.')
        char[resource]-=cost
        roll=rng.randint(1,20)
        bonus=char['skills']['Athletics']
        effect_bonus=char.setdefault('effects',{}).pop('damage',0)
        gear_bonus=equipment_damage_bonus(char)
        damage=rng.randint(2,6) + bonus + gear_bonus + effect_bonus if roll>=6 else 0
        world['enemy_hp']=max(0,world['enemy_hp']-damage)
        bonuses=[]
        if gear_bonus: bonuses.append(f'+{gear_bonus} gear')
        if effect_bonus: bonuses.append(f'+{effect_bonus} spell buff')
        bonus_text=f' ({", ".join(bonuses)})' if bonuses else ''
        text=f'{player["name"]} rolls {roll} and deals {damage} damage{bonus_text}. '
        if world['enemy_hp']==0:
            kind=world.get('enemy_kind','boss')
            if kind=='legacy':
                world['status']='complete'; _finish_encounter(world); text+=scenario['combat_ending']
            elif kind=='side_quest':
                quest=next((q for q in world.get('side_quests',[]) if q['id']==world.get('side_quest_encounter_id')),None)
                if not quest or not quest.get('encounter'): raise ValueError('The side quest encounter is no longer available.')
                quest['encounter_status']='defeated'; _finish_encounter(world); world['side_quest_encounter_id']=None
                text+=quest['encounter']['victory']+' The side quest encounter is complete.'
            else:
                encounter=scenario['enemy'] if kind=='enemy' else scenario['boss']
                item=grant_reward(char,encounter['reward']); _finish_encounter(world)
                if kind=='enemy': text+=encounter['victory']+f' {player["name"]} receives {item["name"]}.'
                else: world['status']='complete'; text+=encounter['combat_ending']+f' {player["name"]} claims {item["name"]}.'
        else:
            text+=_enemy_retaliation(world,members,char,scenario,rng)
    elif action == 'negotiate':
        if world['clues']<3: raise ValueError('Discover three clues before attempting a peaceful resolution.')
        if 'trap' in scenario and world['stage']<4: raise ValueError('Reach the final encounter before attempting a peaceful resolution.')
        world['status']='complete'; _finish_encounter(world)
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
