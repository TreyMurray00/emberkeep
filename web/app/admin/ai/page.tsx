'use client';
import { useEffect, useState } from 'react';
import {
  Flame,
  ArrowLeft,
  KeyRound,
  ShieldCheck,
  Save,
  Plug,
  LogOut,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { api } from '@/lib/game';
type Config = {
  mode: string;
  model: string;
  temperature: number;
  max_tokens: number;
  version: number;
  has_key: boolean;
  local_url?: string;
};
export default function Admin() {
  const [cfg, setCfg] = useState<Config | null>(null),
    [password, setPassword] = useState(''),
    [key, setKey] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  async function load() {
    try {
      setCfg(await api<Config>('/admin/ai'));
    } catch {
      setCfg(null);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function login() {
    setBusy(true);
    setMessage('');
    try {
      await api('/admin/login', { password });
      setPassword('');
      await load();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(test = false) {
    setBusy(true);
    setMessage('');
    try {
      const result = await api<{ message: string; version: number }>(
        test ? '/admin/ai/test' : '/admin/ai',
        { ...cfg, api_key: key },
      );
      setMessage(
        test
          ? result.message
          : `Configuration v${result.version} activated for new sessions.`,
      );
      if (!test) {
        setKey('');
        await load();
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="shell">
      <header className="masthead">
        <a className="brand" href="/">
          <Flame />
          <span>
            EMBERKEEP<small>THE KEEPER’S STUDY</small>
          </span>
        </a>
        <a href="/" className="feature-line">
          <ArrowLeft size={17} />
          Return to the table
        </a>
      </header>
      <main className="admin-layout">
        <p className="eyebrow">ADMINISTRATION</p>
        <h1>The keeper’s study.</h1>
        <p className="muted">
          Choose the mind behind the story. Narration uses each player’s
          built-in browser voice when enabled.
        </p>
        {message && (
          <div className="notice" role="status">
            {message}
          </div>
        )}
        {loading ? (
          <p>Opening settings…</p>
        ) : !cfg ? (
          <section className="folio">
            <KeyRound />
            <h2>Administrator sign-in</h2>
            <p>
              Use the administrator password generated in your local .env file.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                login();
              }}
            >
              <label>
                Administrator password
                <Input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <Button className="primary" type="submit" disabled={busy}>
                Unlock settings
                <ShieldCheck />
              </Button>
            </form>
          </section>
        ) : (
          <section className="folio">
            <div className="journal-head">
              <h2>AI configuration</h2>
              <span>Version {cfg.version}</span>
            </div>
            <div className="admin-grid">
              <label>
                Dungeon master provider
                <Select
                  value={cfg.mode}
                  onValueChange={(v) => setCfg({ ...cfg, mode: String(v) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="template">
                      Template DM · no API needed
                    </SelectItem>
                    <SelectItem value="local">Local SLM · llama.cpp</SelectItem>
                    <SelectItem value="openrouter">
                      OpenRouter · hosted API
                    </SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <label>
                Model identifier
                <Input
                  value={cfg.model}
                  onChange={(e) => setCfg({ ...cfg, model: e.target.value })}
                  disabled={cfg.mode === 'template'}
                  placeholder="Provider’s exact model identifier"
                />
              </label>
              <label>
                Local inference endpoint
                <Input
                  value={cfg.local_url || 'http://127.0.0.1:8080/v1'}
                  onChange={(e) =>
                    setCfg({ ...cfg, local_url: e.target.value })
                  }
                  disabled={cfg.mode !== 'local'}
                />
              </label>
              <label>
                API key {cfg.has_key ? '· saved securely' : ''}
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder={
                    cfg.has_key
                      ? 'Leave blank to keep saved key'
                      : 'Enter provider API key'
                  }
                  disabled={cfg.mode !== 'openrouter'}
                />
              </label>
              <label>
                Creativity · temperature
                <Input
                  type="number"
                  min="0"
                  max="1.5"
                  step="0.1"
                  value={cfg.temperature}
                  onChange={(e) =>
                    setCfg({ ...cfg, temperature: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Maximum response tokens
                <Input
                  type="number"
                  min="64"
                  max="1000"
                  step="1"
                  value={cfg.max_tokens}
                  onChange={(e) =>
                    setCfg({ ...cfg, max_tokens: Number(e.target.value) })
                  }
                />
              </label>
            </div>
            <p className="footnote">
              {cfg.mode === 'local'
                ? 'Connects from the game server to the local endpoint above. No cloud fallback.'
                : cfg.mode === 'openrouter'
                  ? 'API keys are encrypted on the server. New sessions use the model to generate an original adventure; tests and generation may incur a charge.'
                  : 'Template mode runs the starter adventure without a model or API key.'}{' '}
              Browser speech runs independently on each player’s device.
            </p>
            <div className="admin-actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => save(true)}
              >
                <Plug />
                Test connection
              </Button>
              <Button
                className="primary"
                disabled={busy}
                onClick={() => save()}
              >
                <Save />
                Save and activate
              </Button>
              <Button
                variant="ghost"
                onClick={async () => {
                  await api('/admin/logout', {});
                  setCfg(null);
                }}
              >
                <LogOut />
                Sign out
              </Button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
