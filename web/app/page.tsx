'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  Shield,
  Sparkles,
  BowArrow,
  Music2,
  Flame,
  BookOpen,
  Backpack,
  Settings,
  ArrowRight,
  Check,
  Plus,
  Minus,
  Users,
  Swords,
  Compass,
  Search,
  Tent,
  Gem,
  Heart,
  Droplets,
  Zap,
  ScrollText,
  ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { Voice } from '@/components/voice';
import { LeaveTable } from '@/components/leave-table';
import { api, isSafetyMessage, type World, type Draft } from '@/lib/game';
const icons: Record<string, typeof Shield> = {
  warden: Shield,
  mage: Sparkles,
  ranger: BowArrow,
  bard: Music2,
};
const steps = ['Calling', 'Equipment', 'Spells', 'Attributes', 'Skills', 'Review'];
export default function Home() {
  const [world, setWorld] = useState<World | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const [name, setName] = useState(''),
    [code, setCode] = useState(''),
    [step, setStep] = useState(0),
    [draft, setDraft] = useState<Draft | null>(null),
    [query, setQuery] = useState('');
  const [intent, setIntent] = useState('');
  const [sideQuestsOpen, setSideQuestsOpen] = useState(true);
  const [spellOpen, setSpellOpen] = useState(false),
    [selectedSpellId, setSelectedSpellId] = useState(''),
    [spellTarget, setSpellTarget] = useState('');
  const narrated = useRef(new Set<string>());
  async function refresh() {
    try {
      const w = await api('/session');
      setWorld(w);
      setDraft((current) => current ?? w.me.draft);
      return w;
    } catch (e) {
      if ((e as Error).message !== 'Join a session first.')
        setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const timer = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(timer);
  }, []);
  const worldId = world?.id;
  useEffect(() => {
    if (!worldId) return;
    const timer = setInterval(refresh, 2500);
    return () => clearInterval(timer);
  }, [worldId]);
  const latestJournalEntry = world?.journal.at(-1);
  useEffect(() => {
    const e = latestJournalEntry;
    if (e && !e.prose && !narrated.current.has(e.id)) {
      narrated.current.add(e.id);
      void api('/narrate/' + e.id, {})
        .then(() => refresh())
        .catch(() => {});
    }
  }, [latestJournalEntry]);
  useEffect(() => {
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (tool: object, options: object) => void;
        };
      }
    ).modelContext;
    if (!context) return;
    const life = new AbortController();
    try {
      context.registerTool(
        {
          name: 'read_party_state',
          description:
            'Read the current player-visible session, inventory, and character-building state.',
          inputSchema: {
            type: 'object',
            properties: {},
            additionalProperties: false,
          },
          annotations: { readOnlyHint: true },
          execute: () => api('/session'),
        },
        { signal: life.signal },
      );
    } catch {
      /* Browser support is optional. */
    }
    return () => life.abort();
  }, []);
  async function describe() {
    setBusy(true);
    setError('');
    try {
      const proposal = await api<{ action: string }>('/interpret', {
        text: intent,
      });
      if (proposal.action === 'spell') {
        openSpellbook();
        setIntent('');
        return;
      }
      if (await command('action', { action: proposal.action })) setIntent('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function command(type: string, data: object = {}) {
    if (!world) return;
    setBusy(true);
    setError('');
    try {
      const w = await api('/command', {
        id: crypto.randomUUID(),
        version: world.version,
        type,
        data,
      });
      setWorld(w);
      return w as World;
    } catch (e) {
      setError((e as Error).message);
      await refresh();
    } finally {
      setBusy(false);
    }
  }
  async function join() {
    setBusy(true);
    setError('');
    try {
      const w = await api('/join', { name, code });
      setWorld(w);
      setDraft(w.me.draft);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function next() {
    if (step === 0) {
      setStep(1);
      return;
    }
    if (await command('draft', draft!)) setStep(step + 1);
  }
  const cls = world?.classes.find((c) => c.id === world.me.class_id),
    Icon = icons[cls?.id || 'warden'],
    character = world?.me.character,
    selectedGear = cls?.gear.find((g) => g.id === draft?.gear);
  const preparedSpells=(cls?.spells || []).filter((spell) => (character?.spells || []).includes(spell.id)),
    selectedSpell=preparedSpells.find((spell) => spell.id===selectedSpellId);
  function openSpellbook() {
    const first=preparedSpells[0];
    if (!first) return;
    setSelectedSpellId(first.id);
    setSpellTarget(first.target==='enemy' ? 'enemy' : world?.me.id || '');
    setSpellOpen(true);
  }
  function chooseCombatSpell(id:string) {
    const spell=preparedSpells.find((entry) => entry.id===id);
    setSelectedSpellId(id);
    setSpellTarget(spell?.target==='enemy' ? 'enemy' : world?.me.id || '');
  }
  const arcana = character?.skills.Arcana ?? 0,
    athletics = character?.skills.Athletics ?? 0,
    actionOptions = [
      {
        id: 'explore',
        label: 'Explore',
        icon: Compass,
        roll: 'Automatic',
        bonus: 'No check',
      },
      {
        id: 'search',
        label: 'Search',
        icon: Search,
        roll: `D20 ${Math.max(1, 9 - arcana)}+`,
        bonus: `Arcana +${arcana} to check`,
      },
      {
        id: 'attack',
        label: 'Attack',
        icon: Swords,
        roll: 'D20 6+',
        bonus: `Athletics +${athletics} damage`,
      },
      {
        id: 'spell',
        label: 'Open spellbook',
        icon: Sparkles,
        roll: 'Choose spell + target',
        bonus: `Arcana +${arcana} powers spells`,
      },
      {
        id: 'negotiate',
        label: 'Resolve',
        icon: Gem,
        roll: 'Automatic',
        bonus: 'Requires 3 clues + boss',
      },
      {
        id: 'rest',
        label: 'Rest',
        icon: Tent,
        roll: 'Automatic',
        bonus: 'Costs 2 threat',
      },
    ];
  return (
    <div className="shell">
      <header className="masthead">
        <Link className="brand" href="/">
          <Flame />
          <span>
            EMBERKEEP<small>A TABLETOP CHRONICLE</small>
          </span>
        </Link>
        <nav>
          <span className="edition">PROCEDURAL CHRONICLES</span>
          <Link href="/admin/ai">
            <Settings size={19} />
            <span>Keeper’s settings</span>
          </Link>
        </nav>
      </header>
      <main>
        {error && (
          <div className="notice" role="alert">
            {error}
            <Button variant="ghost" onClick={() => setError('')}>
              Dismiss
            </Button>
          </div>
        )}
        {loading ? (
          <div className="empty">
            <Flame />
            <h1>Opening the chronicle…</h1>
          </div>
        ) : !world ? (
          <div className="arrival">
            <section className="arrival-copy">
              <p className="eyebrow">YOUR NEXT ADVENTURE AWAITS</p>
              <h1>
                Every legend
                <br />
                begins with
                <br />
                <em>a choice.</em>
              </h1>
              <div className="rule" />
              <p>
                A new realm, danger, and mystery with every table.
                <br />
                Gather your party and write what happens next.
              </p>
              <div className="feature-line">
                <Users size={18} />
                1–4 adventurers <span>·</span>An AI-guided chronicle
              </div>
            </section>
            <section className="folio join">
              <Shield size={32} />
              <p className="eyebrow">TAKE YOUR PLACE AT THE TABLE</p>
              <h2>Begin your chronicle</h2>
              <p className="muted">
                Create a table, or enter a friend’s invitation code.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void join();
                }}
              >
                <label>
                  Character name
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    maxLength={32}
                    placeholder="What shall we call you?"
                  />
                </label>
                <label>
                  Invitation code <span className="muted">(optional)</span>
                  <Input
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    maxLength={10}
                    placeholder="Leave empty to create a table"
                  />
                </label>
                <Button
                  type="submit"
                  disabled={busy || !name.trim()}
                  className="primary wide"
                >
                  {busy
                    ? 'Preparing your table…'
                    : code
                      ? 'Join the table'
                      : 'Create a table'}
                  <ArrowRight />
                </Button>
              </form>
              <p className="footnote">
                Choose your calling, gather your gear, and shape your character
                before entering the world.
              </p>
            </section>
          </div>
        ) : (
          <>
            <div className="session-line">
              <span>
                <span className="live-dot" />
                TABLE {world.id}
              </span>
              <Button
                variant="ghost"
                onClick={() =>
                  navigator.clipboard
                    .writeText(world.id)
                    .then(() => setError('Invitation code copied.'))
                    .catch(() => setError(`Invitation code: ${world.id}`))
                }
              >
                Copy invitation
              </Button>
              {world.status !== 'active' && (
                <LeaveTable finished={world.status !== 'lobby'} />
              )}
              <span className="right">
                {world.members.length}/4 adventurers ·{' '}
                {world.status === 'lobby'
                  ? 'Gathering the party'
                  : world.status}
              </span>
            </div>
            <div className="party-strip">
              {[0, 1, 2, 3].map((i) => {
                const m = world.members[i],
                  MI = icons[m?.class_id || 'warden'];
                return (
                  <div
                    className={
                      'party-seat ' + (m?.id === world.me.id ? 'self' : '')
                    }
                    key={i}
                  >
                    <div className="medallion">
                      {m ? <MI size={24} /> : <Plus size={20} />}
                    </div>
                    <div>
                      <strong>{m?.name || 'An empty seat'}</strong>
                      <small>
                        {m
                          ? world.classes.find((c) => c.id === m.class_id)
                              ?.name || 'Choosing a calling'
                          : 'Invite an adventurer'}
                      </small>
                    </div>
                    {m && (
                      <span className="seat-state">
                        {m.ready
                          ? m.hp != null
                            ? `${m.hp}/${m.max_hp} HP`
                            : 'Ready'
                          : 'Building'}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            {world.status === 'lobby' && !world.me.ready && draft ? (
              <div className="builder-layout">
                <section className="builder">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">THE CHARACTER FOLIO</p>
                      <h1>Choose who you become.</h1>
                    </div>
                    <span className="chapter-number">
                      0{step + 1}
                      <small>/ 05</small>
                    </span>
                  </div>
                  <ol className="stepper">
                    {steps.map((s, i) => (
                      <li
                        key={s}
                        className={
                          i === step ? 'current' : i < step ? 'done' : ''
                        }
                      >
                        <button disabled={i > step} onClick={() => setStep(i)}>
                          {i < step ? <Check size={14} /> : i + 1}
                          <span>{s}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                  {step === 0 ? (
                    <>
                      <div className="subheading">
                        <h2>Four callings. One is yours.</h2>
                        <p>
                          Drawn for your table. Each class may be claimed by
                          only one adventurer.
                        </p>
                      </div>
                      <RadioGroup
                        value={world.me.class_id || ''}
                        onValueChange={async (value) => {
                          const w = await command('reserve', {
                            class_id: value,
                          });
                          if (w) setDraft(w.me.draft);
                        }}
                        className="class-grid"
                        aria-label="Choose your class"
                      >
                        {world.classes.map((c) => {
                          const C = icons[c.id],
                            owner = world.members.find(
                              (m) => m.class_id === c.id,
                            ),
                            taken = !!owner && owner.id !== world.me.id;
                          return (
                            <label
                              className={
                                'class-card ' +
                                (cls?.id === c.id ? 'selected ' : '') +
                                (taken ? 'taken' : '')
                              }
                              key={c.id}
                            >
                              <div className="card-top">
                                <span className="eyebrow">{c.role}</span>
                                <RadioGroupItem
                                  value={c.id}
                                  disabled={busy || taken}
                                  aria-label={c.name}
                                />
                              </div>
                              <C className="class-emblem" strokeWidth={1} />
                              <h3>{c.name}</h3>
                              <p>{c.description}</p>
                              <div className="class-stats">
                                <span>
                                  <Heart size={13} />
                                  {c.hp}
                                </span>
                                <span>
                                  <Droplets size={13} />
                                  {c.mana}
                                </span>
                                <span>
                                  <Zap size={13} />
                                  {c.stamina}
                                </span>
                              </div>
                              <div className="class-footer">
                                {taken
                                  ? `Reserved · ${owner.name}`
                                  : cls?.id === c.id
                                    ? 'Your calling'
                                    : 'Primary · ' + c.primary}
                              </div>
                            </label>
                          );
                        })}
                      </RadioGroup>
                    </>
                  ) : step === 1 ? (
                    <>
                      <div className="subheading">
                        <h2>Pack for the unknown.</h2>
                        <p>
                          Choose one starting weapon. Two healing draughts and
                          an adventurer’s pack are included.
                        </p>
                      </div>
                      <RadioGroup
                        value={draft.gear}
                        onValueChange={(v) =>
                          setDraft({ ...draft, gear: String(v) })
                        }
                        aria-label="Starter weapon"
                      >
                        {cls?.gear.map((g) => (
                          <label className="gear-option" key={g.id}>
                            <Swords />
                            <span>
                              {g.name}
                              <small>
                                Starting weapon · {g.effect || 'equipment bonus'}
                              </small>
                            </span>
                            <RadioGroupItem value={g.id} />
                          </label>
                        ))}
                      </RadioGroup>
                      <div className="included">
                        <Backpack />
                        <p>2 × Healing draught · 1 × Adventurer’s pack</p>
                      </div>
                    </>
                  ) : step === 2 ? (
                    <>
                      <div className="subheading">
                        <h2>Prepare two spells.</h2>
                        <p>
                          Fill both spell slots from your calling’s spellbook.
                          You cannot change prepared spells after marking ready.
                        </p>
                      </div>
                      <div className="spell-slots" aria-live="polite">
                        <span>Spell slot I</span>
                        <strong>
                          {cls?.spells?.find((spell) => spell.id === (draft.spells || [])[0])?.name || 'Empty'}
                        </strong>
                        <span>Spell slot II</span>
                        <strong>
                          {cls?.spells?.find((spell) => spell.id === (draft.spells || [])[1])?.name || 'Empty'}
                        </strong>
                      </div>
                      <div className="spell-grid">
                        {cls?.spells?.map((spell) => {
                          const selected=(draft.spells || []).includes(spell.id),
                            full=(draft.spells || []).length>=2;
                          return (
                            <label className={'spell-card '+(selected ? 'selected' : '')} key={spell.id}>
                              <div>
                                <span className="eyebrow">{spell.kind} · {spell.cost} mana</span>
                                <Checkbox
                                  checked={selected}
                                  disabled={!selected && full}
                                  onCheckedChange={() => {
                                    const spells=draft.spells || [];
                                    setDraft({...draft,spells:selected ? spells.filter((id) => id!==spell.id) : [...spells,spell.id]});
                                  }}
                                  aria-label={`Prepare ${spell.name}`}
                                />
                              </div>
                              <h3>{spell.name}</h3>
                              <p>{spell.description}</p>
                              <small>{spell.target==='enemy' ? 'Targets the active enemy' : 'Targets self or an ally'} · Power {spell.power}</small>
                            </label>
                          );
                        })}
                      </div>
                    </>
                  ) : step === 3 || step === 4 ? (
                    <PointEditor
                      draft={draft}
                      setDraft={setDraft}
                      skills={step === 4}
                    />
                  ) : (
                    <div className="review">
                      <div className="subheading">
                        <h2>Your story is ready to begin.</h2>
                        <p>
                          Your starting build locks when you mark yourself
                          ready.
                        </p>
                      </div>
                      <h3>
                        {world.me.name} · {cls?.name}
                      </h3>
                      <div className="review-columns">
                        <div>
                          <p className="eyebrow">ATTRIBUTES</p>
                          {Object.entries(draft.attributes).map(([k, v]) => (
                            <p className="stat-line" key={k}>
                              {k}
                              <strong>{v}</strong>
                            </p>
                          ))}
                        </div>
                        <div>
                          <p className="eyebrow">SKILLS</p>
                          {Object.entries(draft.skills).map(([k, v]) => (
                            <p className="stat-line" key={k}>
                              {k}
                              <strong>{v}</strong>
                            </p>
                          ))}
                        </div>
                      </div>
                      <p>
                        Starter weapon:{' '}
                        <strong>
                          {cls?.gear.find((g) => g.id === draft.gear)?.name}
                          {selectedGear ? ` · ${selectedGear.effect}` : ''}
                        </strong>
                      </p>
                      <p>
                        Prepared spells:{' '}
                        <strong>
                          {(draft.spells || []).map((id) => cls?.spells?.find((spell) => spell.id===id)?.name).filter(Boolean).join(' · ')}
                        </strong>
                      </p>
                    </div>
                  )}
                  <div className="builder-actions">
                    <Button
                      variant="ghost"
                      disabled={step === 0 || busy}
                      onClick={() => setStep(step - 1)}
                    >
                      Back
                    </Button>
                    <span>Saved when you continue</span>
                    {step < 5 ? (
                      <Button
                        className="primary"
                        disabled={busy || !cls || (step === 1 && !draft.gear) || (step === 2 && (draft.spells || []).length !== 2)}
                        onClick={next}
                      >
                        Continue
                        <ArrowRight />
                      </Button>
                    ) : (
                      <Button
                        className="primary"
                        disabled={busy}
                        onClick={() => command('finalize')}
                      >
                        Ready for adventure
                        <Check />
                      </Button>
                    )}
                  </div>
                </section>
                <aside className="folio preview">
                  <p className="eyebrow">YOUR ADVENTURER</p>
                  <div className="portrait">
                    <Icon size={62} strokeWidth={1} />
                  </div>
                  <h2>{world.me.name}</h2>
                  <p>{cls?.name || 'A story yet unwritten'}</p>
                  <div className="rule" />
                  {cls ? (
                    <>
                      <Meter
                        label="HP"
                        value={cls.hp + draft.attributes.Might - 8 + (selectedGear?.resource === 'hp' ? selectedGear.resource_bonus : 0)}
                        max={cls.hp + draft.attributes.Might - 8 + (selectedGear?.resource === 'hp' ? selectedGear.resource_bonus : 0)}
                        color="hp"
                      />
                      <Meter
                        label="Mana"
                        value={cls.mana + draft.attributes.Intellect - 8 + (selectedGear?.resource === 'mana' ? selectedGear.resource_bonus : 0)}
                        max={cls.mana + draft.attributes.Intellect - 8 + (selectedGear?.resource === 'mana' ? selectedGear.resource_bonus : 0)}
                        color="mana"
                      />
                      <Meter
                        label="Stamina"
                        value={cls.stamina + draft.attributes.Agility - 8 + (selectedGear?.resource === 'stamina' ? selectedGear.resource_bonus : 0)}
                        max={cls.stamina + draft.attributes.Agility - 8 + (selectedGear?.resource === 'stamina' ? selectedGear.resource_bonus : 0)}
                        color="stamina"
                      />
                    </>
                  ) : (
                    <p className="muted">
                      Choose a class to reveal your starting resources.
                    </p>
                  )}
                  <div className="preview-note">
                    <ScrollText />
                    <p>
                      Custom adventure rules
                      <br />
                      <small>8 attribute points · 4 skill points</small>
                    </p>
                  </div>
                </aside>
              </div>
            ) : world.status === 'lobby' ? (
              <section className="folio waiting">
                <Shield size={48} />
                <p className="eyebrow">YOUR CHARACTER IS READY</p>
                <h1>The party gathers.</h1>
                <p>
                  Share table code <strong>{world.id}</strong> with friends, or
                  begin a solo adventure.
                </p>
                <Button
                  className="primary"
                  disabled={
                    busy ||
                    !world.me.host ||
                    !world.members.every((m) => m.ready)
                  }
                  onClick={() => command('start')}
                >
                  {busy
                    ? 'Generating adventure…'
                    : world.me.host
                      ? 'Generate and begin adventure'
                      : 'Waiting for the host'}
                  <ArrowRight />
                </Button>
                <p className="muted">
                  {world.members.filter((m) => m.ready).length} of{' '}
                  {world.members.length} adventurers ready
                </p>
              </section>
            ) : world.status === 'generating' ? (
              <section className="folio waiting chapter-generating" aria-live="polite">
                <Sparkles size={48} />
                <p className="eyebrow">THE NEXT CHAPTER IS BEING WRITTEN</p>
                <h1>Turning the page…</h1>
                <p>
                  The dungeon master is shaping Chapter {world.pending_chapter ?? world.chapter + 1}.
                  Your completed outcome is safe, and the table will resume as
                  soon as the new chapter is ready.
                </p>
                {world.me.host && (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError('');
                      try { setWorld(await api('/generation/fallback', {})); }
                      catch (e) { setError((e as Error).message); }
                      finally { setBusy(false); }
                    }}
                  >
                    Continue with built-in chapter
                  </Button>
                )}
                <div className="chapter-loader" aria-label="Generating next chapter">
                  <span />
                  <span />
                  <span />
                </div>
              </section>
            ) : (
              <div className="play-layout">
                <section className="adventure">
                  <div className="scene-banner">
                    <p className="eyebrow">
                      {(world.title || 'Adventure').toUpperCase()}
                    </p>
                    <p className="chapter-kicker">
                      Chapter {world.chapter} of {world.chapter_count} ·{' '}
                      {world.chapter_title}
                    </p>
                    {world.generation_source === 'fallback' && (
                      <output>AI generation did not complete for this chapter. You are playing the built-in story.</output>
                    )}
                    <h1>{world.location}</h1>
                    <p>{world.objective}</p>
                    <div className="scene-meta">
                      {character && (
                        <span className="mobile-vitals" aria-label="Your current resources">
                          <Heart size={16} /> {character.hp} HP
                          <Droplets size={16} /> {character.mana} mana
                          <Zap size={16} /> {character.stamina} stamina
                        </span>
                      )}
                      <span>
                        <Gem size={16} />
                        {world.clues}/3 clues
                      </span>
                      <span>
                        <Flame size={16} />
                        {world.threat}/8 threat
                      </span>
                      {world.enemy_hp > 0 && (
                        <span>
                          <Swords size={16} />
                          {world.enemy_name || 'Enemy'} · {world.enemy_hp}/
                          {world.enemy_max_hp || world.enemy_hp} HP · scaled for{' '}
                          {world.encounter_party_size || world.members.length}
                        </span>
                      )}
                      {!!world.enemy_effects?.weaken && (
                        <span><Sparkles size={16} />Weakened · −{world.enemy_effects.weaken} next retaliation</span>
                      )}
                    </div>
                  </div>
                  <section className="folio journal">
                    <div className="journal-head">
                      <div>
                        <h2>
                          <BookOpen size={22} />
                          The chronicle
                        </h2>
                        <p>Newest events appear first.</p>
                      </div>
                      <div className="journal-head-actions">
                        <Voice world={world} />
                      </div>
                    </div>
                    <div
                      className="entries"
                      role="log"
                      aria-live="polite"
                      aria-relevant="additions text"
                    >
                      {world.journal
                        .filter((e) => !isSafetyMessage(e.text) && !isSafetyMessage(e.prose))
                        .slice()
                        .reverse()
                        .map((e, index) => {
                          const latest = index === 0;
                          return (
                            <article
                              key={e.id}
                              className={latest ? 'latest-entry' : undefined}
                            >
                              <div className="entry-meta">
                                <p className="eyebrow">{e.speaker}</p>
                                <div>
                                  {latest && (
                                    <span className="latest-marker">
                                      Latest event
                                    </span>
                                  )}
                                  {e.roll && (
                                    <span className="roll">D20 · {e.roll}</span>
                                  )}
                                </div>
                              </div>
                              <p>{e.prose || e.text}</p>
                              {!world.ai_enabled &&
                                e.prose &&
                                e.prose !== e.text && (
                                  <details>
                                    <summary>Confirmed outcome</summary>
                                    {e.text}
                                  </details>
                                )}
                            </article>
                          );
                        })}
                    </div>
                    {world.side_quests.length > 0 && (
                      <Collapsible
                        className="side-quests"
                        open={sideQuestsOpen}
                        onOpenChange={setSideQuestsOpen}
                      >
                        <div className="side-quests-head">
                          <p className="eyebrow" id="side-quests-title">
                            OPTIONAL QUESTS
                          </p>
                          <CollapsibleTrigger
                            type="button"
                            className="side-quests-toggle"
                            aria-label={
                              sideQuestsOpen
                                ? 'Hide side quests'
                                : 'Show side quests'
                            }
                          >
                            {sideQuestsOpen ? 'Hide' : 'Show'}
                            <ChevronDown
                              size={16}
                              aria-hidden="true"
                              className={sideQuestsOpen ? 'is-open' : undefined}
                            />
                          </CollapsibleTrigger>
                        </div>
                        <CollapsibleContent
                          className="side-quests-content"
                          aria-labelledby="side-quests-title"
                        >
                          {world.side_quests.map((quest) => {
                            const encounterReady =
                              !quest.encounter ||
                              quest.encounter_status === 'defeated';
                            const ready =
                              world.clues >= quest.requires_clues &&
                              encounterReady;
                            return (
                              <article key={quest.id}>
                                <div>
                                  <strong>{quest.title}</strong>
                                  <small>
                                    {quest.giver} · {quest.status}
                                  </small>
                                  <p>
                                    {quest.status === 'available'
                                      ? quest.hook
                                      : quest.objective}
                                  </p>
                                  {quest.encounter && (
                                    <small>
                                      Encounter: {quest.encounter.name} ·{' '}
                                      {quest.encounter_status || 'pending'}
                                    </small>
                                  )}
                                  <small>Reward: {quest.reward.name}</small>
                                </div>
                                <Button
                                  variant="outline"
                                  disabled={
                                    busy ||
                                    quest.status === 'completed' ||
                                    (quest.status === 'active' &&
                                      encounterReady &&
                                      world.clues < quest.requires_clues) ||
                                    world.enemy_hp > 0
                                  }
                                  onClick={() =>
                                    command('side_quest', {
                                      quest_id: quest.id,
                                    })
                                  }
                                >
                                  {quest.status === 'available'
                                    ? 'Accept'
                                    : quest.status === 'completed'
                                      ? 'Completed'
                                      : !encounterReady
                                        ? quest.encounter_status === 'active'
                                          ? `Defeat ${quest.encounter?.name || 'the enemy'}`
                                          : 'Begin encounter'
                                        : ready
                                          ? 'Claim reward'
                                          : `${quest.requires_clues} clues needed`}
                                </Button>
                              </article>
                            );
                          })}
                        </CollapsibleContent>
                      </Collapsible>
                    )}
                    {world.status === 'active' ? (
                      <div className="action-panel">
                        <p className="eyebrow">
                          {world.enemy_hp
                            ? 'IN COMBAT · ' +
                              world.members[world.turn % world.members.length]
                                ?.name +
                              '’S TURN'
                            : 'WHAT WILL YOU DO?'}
                        </p>
                        <div className="actions">
                          {actionOptions.map((action) => {
                            const ActionIcon = action.icon;
                            return (
                              <Button
                                variant="outline"
                                key={action.id}
                                disabled={busy || (action.id==='spell' && preparedSpells.length===0)}
                                onClick={() => action.id==='spell' ? openSpellbook() : command('action', { action: action.id })}
                              >
                                <ActionIcon size={17} />
                                <span className="action-copy">
                                  <strong>{action.label}</strong>
                                  <small>{action.roll}</small>
                                  <small>{action.bonus}</small>
                                </span>
                              </Button>
                            );
                          })}
                        </div>
                        {spellOpen && selectedSpell && (
                          <section className="spell-caster" aria-label="Cast a prepared spell">
                            <div className="spell-caster-head">
                              <div>
                                <p className="eyebrow">PREPARED SPELL</p>
                                <strong>{selectedSpell.description}</strong>
                              </div>
                              <Button variant="ghost" onClick={() => setSpellOpen(false)}>Close</Button>
                            </div>
                            <div className="spell-caster-fields">
                              <label>
                                Spell
                                <Select value={selectedSpellId} onValueChange={(value) => chooseCombatSpell(String(value))}>
                                  <SelectTrigger><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    {preparedSpells.map((spell) => (
                                      <SelectItem key={spell.id} value={spell.id}>{spell.name} · {spell.cost} mana</SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </label>
                              {selectedSpell.target==='enemy' ? (
                                <div className="spell-target-summary">
                                  <span>Target</span>
                                  <strong>{world.enemy_name || 'No active enemy'}</strong>
                                </div>
                              ) : (
                                <label>
                                  Target
                                  <Select value={spellTarget} onValueChange={(value) => setSpellTarget(String(value))}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                      {world.members.filter((member) => member.ready).map((member) => (
                                        <SelectItem key={member.id} value={member.id}>
                                          {member.id===world.me.id ? `${member.name} · self` : member.name}
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </label>
                              )}
                            </div>
                            <div className="spell-caster-footer">
                              <span>{selectedSpell.kind} · power {selectedSpell.power} · {selectedSpell.cost} mana</span>
                              <Button
                                className="primary"
                                disabled={busy || character!.mana<selectedSpell.cost || (selectedSpell.target==='enemy' && !world.enemy_hp) || (selectedSpell.target!=='enemy' && !spellTarget)}
                                onClick={async () => {
                                  const result=await command('action',{action:'spell',spell_id:selectedSpell.id,target_id:spellTarget});
                                  if (result) setSpellOpen(false);
                                }}
                              >
                                <Sparkles size={16} /> Cast {selectedSpell.name}
                              </Button>
                            </div>
                          </section>
                        )}
                        <form
                          className="intent-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                             void describe();
                          }}
                        >
                          <Input
                            aria-label="Describe your action"
                            maxLength={500}
                            placeholder="I search the area for clues…"
                            value={intent}
                            onChange={(e) => setIntent(e.target.value)}
                          />
                          <Button
                            className="primary"
                            type="submit"
                            disabled={busy || !intent.trim()}
                          >
                            Act
                            <ArrowRight size={16} />
                          </Button>
                        </form>
                        <small className="action-costs">
                          Attack: 2 stamina · Spells: listed mana cost · Combat consumable:
                          1 turn · Rest: 2 threat
                        </small>
                        {character && (
                          <small className="stat-bonuses">
                            Attribute bonuses: Might +
                            {character.attributes.Might - 8} HP · Agility +
                            {character.attributes.Agility - 8} stamina ·
                            Intellect +{character.attributes.Intellect - 8}{' '}
                            mana. Attributes do not modify d20 checks in the
                            current rules.
                            {' '}Equipped gear adds +
                            {character.inventory
                              .filter((item) => item.equipped)
                              .reduce((total, item) => total + (item.damage_bonus || 0), 0)}{' '}
                            damage.
                          </small>
                        )}
                      </div>
                    ) : (
                      <div className="ending">
                        <h2>
                          {world.status === 'complete'
                            ? 'Adventure complete.'
                            : 'The threat has prevailed.'}
                        </h2>
                        <p>
                          Your session is complete. The chronicle and your
                          character are saved.
                        </p>
                      </div>
                    )}
                  </section>
                </section>
                <aside className="folio character-panel">
                  <div className="character-title">
                    <Icon size={30} />
                    <div>
                      <h2>{world.me.name}</h2>
                      <small>{cls?.name}</small>
                    </div>
                  </div>
                  {character && (
                    <>
                      <Meter
                        label="HP"
                        value={character.hp}
                        max={character.max_hp}
                        color="hp"
                      />
                      <Meter
                        label="Mana"
                        value={character.mana}
                        max={character.max_mana}
                        color="mana"
                      />
                      <Meter
                        label="Stamina"
                        value={character.stamina}
                        max={character.max_stamina}
                        color="stamina"
                      />
                      <Tabs defaultValue="inventory">
                        <TabsList className="inventory-tabs">
                          <TabsTrigger value="inventory">
                            <Backpack />
                            Inventory
                          </TabsTrigger>
                          <TabsTrigger value="sheet">Character</TabsTrigger>
                        </TabsList>
                        <TabsContent value="inventory">
                          <Input
                            aria-label="Search inventory"
                            placeholder="Search your satchel…"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                          />
                          <div className="items">
                            {character.inventory
                              .filter(
                                (i) =>
                                  i.quantity > 0 &&
                                  i.name
                                    .toLowerCase()
                                    .includes(query.toLowerCase()),
                              )
                              .map((i) => (
                                <div className="item" key={i.id}>
                                  <div className="item-icon">
                                    {i.kind === 'weapon' ? (
                                      <Swords />
                                    ) : i.kind === 'potion' ? (
                                      <Droplets />
                                    ) : (
                                      <Backpack />
                                    )}
                                  </div>
                                  <div>
                                    <strong>{i.name}</strong>
                                    <small>
                                      {i.equipped ? 'Equipped' : i.kind} · ×
                                      {i.quantity}
                                    </small>
                                    {i.kind === 'weapon' && (
                                      <small className="item-effect">
                                        +{i.damage_bonus || 0} damage
                                        {i.resource_bonus
                                          ? ` · +${i.resource_bonus} max ${i.resource}`
                                          : ''}
                                      </small>
                                    )}
                                    {i.kind === 'potion' ||
                                    i.kind === 'weapon' ? (
                                      <Button
                                        variant="ghost"
                                        disabled={
                                          busy || world.status !== 'active'
                                        }
                                        onClick={() =>
                                          command(
                                            i.kind === 'potion'
                                              ? 'use'
                                              : 'equip',
                                            { item_id: i.id },
                                          )
                                        }
                                      >
                                        {i.kind === 'potion'
                                          ? `Use · restore ${i.restore_amount || 8} ${(i.restores || 'hp').toUpperCase()}${world.enemy_hp ? ' · costs turn' : ''}`
                                          : i.equipped
                                            ? 'Unequip'
                                            : 'Equip'}
                                      </Button>
                                    ) : null}
                                  </div>
                                </div>
                              ))}
                          </div>
                          {world.loot.length > 0 && (
                            <>
                              <p className="eyebrow">NEARBY LOOT</p>
                              {world.loot.map((i) => (
                                <Button
                                  key={i.id}
                                  variant="outline"
                                  className="wide"
                                  disabled={busy || world.status !== 'active'}
                                  onClick={() =>
                                    command('collect', { item_id: i.id })
                                  }
                                >
                                  <Gem />
                                  Collect {i.name}
                                </Button>
                              ))}
                            </>
                          )}
                        </TabsContent>
                        <TabsContent value="sheet">
                          {Object.entries(character.attributes).map(
                            ([k, v]) => (
                              <p className="stat-line" key={k}>
                                {k}
                                <strong>{v}</strong>
                              </p>
                            ),
                          )}
                          <div className="rule" />
                          {Object.entries(character.skills).map(([k, v]) => (
                            <p className="stat-line" key={k}>
                              {k}
                              <strong>{v}</strong>
                            </p>
                          ))}
                          <div className="rule" />
                          <p className="eyebrow">PREPARED SPELLS</p>
                          {preparedSpells.map((spell) => (
                            <p className="spell-sheet-entry" key={spell.id}>
                              <strong>{spell.name}</strong>
                              <span>{spell.kind} · {spell.cost} mana · {spell.description}</span>
                            </p>
                          ))}
                          {!!character.effects?.damage && (
                            <p className="active-effect">Empowered · +{character.effects.damage} next damage</p>
                          )}
                          {!!character.effects?.ward && (
                            <p className="active-effect">Warded · prevent {character.effects.ward} from the next hit</p>
                          )}
                          <div className="rule" />
                          <p className="eyebrow">EQUIPPED BONUSES</p>
                          {character.inventory.filter((item) => item.equipped).map((item) => (
                            <p className="stat-line" key={item.id}>
                              {item.name}
                              <strong>
                                +{item.damage_bonus || 0} damage
                                {item.resource_bonus ? ` · +${item.resource_bonus} ${item.resource}` : ''}
                              </strong>
                            </p>
                          ))}
                        </TabsContent>
                      </Tabs>
                    </>
                  )}
                </aside>
              </div>
            )}
          </>
        )}
      </main>
      <footer>
        EMBERKEEP<span>Fortune favors the curious.</span>
        <span>Procedural adventures · Homebrew rules v0.2</span>
      </footer>
    </div>
  );
}
function PointEditor({
  draft,
  setDraft,
  skills,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  skills: boolean;
}) {
  const key = skills ? 'skills' : 'attributes',
    min = skills ? 0 : 8,
    max = skills ? 3 : 14,
    budget = skills ? 4 : 8,
    values = draft[key],
    left = budget - Object.values(values).reduce((s, n) => s + n - min, 0);
  return (
    <>
      <div className="subheading">
        <h2>
          {skills
            ? 'Make your talents your own.'
            : 'Give your hero their strengths.'}
        </h2>
        <p>
          {skills
            ? 'Spend four skill points. Maximum three per skill.'
            : 'Spend eight points. Attributes begin at eight; each increase costs one point.'}
        </p>
      </div>
      <div className="budget">
        <span>POINTS REMAINING</span>
        <strong>{left}</strong>
      </div>
      {Object.entries(values).map(([k, v]) => (
        <div className="point-row" key={k}>
          <div>
            <h3>{k}</h3>
            <small>
              {skills
                ? 'Bonus to related checks'
                : k === 'Might'
                  ? 'Physical power and maximum HP'
                  : k === 'Agility'
                    ? 'Quickness and maximum stamina'
                    : k === 'Intellect'
                      ? 'Knowledge and maximum mana'
                      : 'Willpower and presence'}
            </small>
          </div>
          <Button
            variant="outline"
            aria-label={`Decrease ${k}`}
            disabled={v <= min}
            onClick={() =>
              setDraft({ ...draft, [key]: { ...values, [k]: v - 1 } })
            }
          >
            <Minus size={15} />
          </Button>
          <strong>{v}</strong>
          <Button
            variant="outline"
            aria-label={`Increase ${k}`}
            disabled={v >= max || left <= 0}
            onClick={() =>
              setDraft({ ...draft, [key]: { ...values, [k]: v + 1 } })
            }
          >
            <Plus size={15} />
          </Button>
        </div>
      ))}
    </>
  );
}
function Meter({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  return (
    <div className={'meter ' + color}>
      <div>
        <span>{label}</span>
        <strong>
          {value}
          <small> / {max}</small>
        </strong>
      </div>
      <Progress
        value={(100 * value) / max}
        aria-label={`${label}: ${value} of ${max}`}
      />
    </div>
  );
}
