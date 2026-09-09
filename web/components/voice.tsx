'use client';
import { useEffect, useRef, useState } from 'react';
import { Volume2, VolumeX, SkipForward, RotateCcw, Pause, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { api, type World } from '@/lib/game';

/** Lightweight narration controls backed only by the browser speech engine. */
export function Voice({ world }: { world: World }) {
  const seen = useRef(new Set<string>());
  const current = useRef<SpeechSynthesisUtterance | null>(null);
  const volumeRef = useRef(0.8);
  const [enabled, setEnabled] = useState(false),
    [status, setStatus] = useState(''),
    [volume, setVolume] = useState(0.8),
    [paused, setPaused] = useState(false);
  const latest = world.journal.at(-1);

  function stop() {
    window.speechSynthesis?.cancel();
    current.current = null;
    setPaused(false);
  }

  function speak(text: string) {
    if (!('speechSynthesis' in window)) {
      setStatus('Browser speech is unavailable. Text remains available.');
      return;
    }
    stop();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.volume = volumeRef.current;
    utterance.rate = 0.95;
    utterance.onstart = () => setStatus('Reading aloud');
    utterance.onend = () => { current.current = null; setPaused(false); setStatus('Browser voice ready'); };
    utterance.onerror = () => { current.current = null; setPaused(false); setStatus('Browser voice could not play. Text remains available.'); };
    current.current = utterance;
    window.speechSynthesis.speak(utterance);
  }

  async function enqueue(entry: NonNullable<typeof latest>, force = false) {
    if (seen.current.has(entry.id)) return;
    seen.current.add(entry.id);
    let text = entry.prose || entry.text;
    try { text = (await api<{ text: string }>('/narrate/' + entry.id, {})).text; } catch { /* text is a safe fallback */ }
    if (enabled || force) speak(text);
  }

  function toggle() {
    if (enabled) {
      stop();
      setEnabled(false);
      setStatus('');
      return;
    }
    setEnabled(true);
    setStatus('Browser voice ready');
    if (latest) {
      seen.current = new Set(world.journal.slice(0, -1).map((entry) => entry.id));
      void enqueue(latest, true);
    }
  }

  useEffect(() => {
    if (enabled && latest) void enqueue(latest);
  }, [latest?.id, enabled]);
  useEffect(() => () => stop(), []);

  return (
    <div className="voice-controls">
      <Button variant="ghost" onClick={toggle} aria-label={enabled ? 'Disable browser voice' : 'Enable browser voice'}>
        {enabled ? <VolumeX size={16} /> : <Volume2 size={16} />} {enabled ? 'Mute' : 'Enable voice'}
      </Button>
      {enabled && <>
        <Button variant="ghost" aria-label={paused ? 'Resume narration' : 'Pause narration'} onClick={() => {
          if (!current.current) return;
          if (paused) { window.speechSynthesis.resume(); setPaused(false); }
          else { window.speechSynthesis.pause(); setPaused(true); }
        }}>{paused ? <Play size={15} /> : <Pause size={15} />}</Button>
        <Button variant="ghost" aria-label="Skip narration" onClick={() => { stop(); setStatus('Skipped'); }}><SkipForward size={15} /></Button>
        <Button variant="ghost" aria-label="Replay latest narration" onClick={() => { if (latest) speak(latest.prose || latest.text); }}><RotateCcw size={15} /></Button>
        <Slider aria-label="Voice volume" value={[volume]} min={0} max={1} step={0.05} onValueChange={(value) => {
          const next = Array.isArray(value) ? value[0] : value;
          setVolume(next); volumeRef.current = next;
        }} />
        <output>{status}</output>
      </>}
    </div>
  );
}
