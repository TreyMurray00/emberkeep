export async function api<T = World>(path: string, data?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {
    method: data === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  let result: unknown;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      'The game server is unavailable. Check that the local server is running.',
    );
  }
  if (!response.ok) {
    const detail = (result as { detail?: unknown })?.detail;
    throw new Error(
      typeof detail === 'string' ? detail : 'Please check your entries.',
    );
  }
  return result as T;
}
export type Draft = {
  class_id: string | null;
  gear: string;
  spells?: string[];
  attributes: Record<string, number>;
  skills: Record<string, number>;
};
export type Spell = {
  id: string;
  name: string;
  kind: 'damage' | 'heal' | 'buff' | 'ward' | 'debuff';
  target: 'enemy' | 'self_or_ally';
  cost: number;
  power: number;
  description: string;
};
export type Item = {
  id: string;
  name: string;
  kind: string;
  quantity: number;
  equipped: boolean;
  restores?: 'hp' | 'mana' | 'stamina';
  restore_amount?: number;
  damage_bonus?: number;
  resource?: 'hp' | 'mana' | 'stamina';
  resource_bonus?: number;
};
export type SideQuest = {
  id: string;
  title: string;
  giver: string;
  hook: string;
  objective: string;
  requires_clues: number;
  encounter?: {
    name: string;
    location: string;
    intro: string;
  } | null;
  encounter_status?: 'pending' | 'active' | 'defeated' | null;
  status: 'available' | 'active' | 'completed';
  reward: { name: string; kind: Item['kind'] };
};
export type Character = Draft & {
  hp: number;
  max_hp: number;
  mana: number;
  max_mana: number;
  stamina: number;
  max_stamina: number;
  inventory: Item[];
  effects?: { damage?: number; ward?: number };
};
export type Member = {
  id: string;
  name: string;
  host: boolean;
  ready: boolean;
  class_id: string | null;
  hp?: number;
  max_hp?: number;
  draft: Draft;
  character?: Character;
};
export type World = {
  id: string;
  version: number;
  status: string;
  title?: string;
  chapter: number;
  chapter_count: number;
  chapter_title: string;
  ai_enabled?: boolean;
  generation_source?: 'ai' | 'template' | 'fallback';
  pending_chapter?: number;
  location: string;
  objective: string;
  clues: number;
  threat: number;
  enemy_hp: number;
  enemy_max_hp?: number;
  encounter_party_size?: number;
  enemy_name?: string | null;
  enemy_effects?: { weaken?: number };
  turn: number;
  me: Member;
  members: Member[];
  loot: Item[];
  side_quests: SideQuest[];
  journal: {
    id: string;
    speaker: string;
    text: string;
    prose?: string;
    roll?: number | null;
  }[];
  classes: {
    id: string;
    name: string;
    role: string;
    description: string;
    primary: string;
    hp: number;
    mana: number;
    stamina: number;
    gear: {
      id: string;
      name: string;
      damage_bonus: number;
      resource: 'hp' | 'mana' | 'stamina';
      resource_bonus: number;
      effect: string;
    }[];
    spells: Spell[];
  }[];
};

export function isSafetyMessage(text?: string) {
  return /^\s*user\s+safety\s*:/i.test(text || '');
}
