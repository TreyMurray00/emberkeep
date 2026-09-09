'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Volume2,
  VolumeX,
  SkipForward,
  RotateCcw,
  Pause,
  Play,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { api, type World } from '@/lib/game';
// oxlint-disable-next-line import/default -- Vite supplies the worker constructor.
import SpeechWorker from '@/lib/speech.worker?worker';
export function Voice({ world }: { world: World }) {
  const worker = useRef<Worker | null>(null),
    audio = useRef<HTMLAudioElement | null>(null),
    url = useRef(''),
    seen = useRef(new Set<string>()),
    queue = useRef<{ id: string; text: string }[]>([]),
    audioQueue = useRef<Blob[]>([]),
    active = useRef(false),
    generating = useRef(false),
    generatingId = useRef(''),
    generation = useRef(0),
    volumeRef = useRef(0.8),
    ready = useRef(false),
    browserFallback = useRef(false),
    pendingText = useRef<Promise<void>>(Promise.resolve());
  const [enabled, setEnabled] = useState(false),
    [status, setStatus] = useState(''),
    [volume, setVolume] = useState(0.8),
    [paused, setPaused] = useState(false),
    [engine, setEngine] = useState<'kokoro' | 'browser' | null>(null);
  const latest = world.journal.at(-1);
  const latestRef = useRef(latest);
  latestRef.current = latest;
  const voiceRef = useRef(world.speech?.voice || 'af_heart');
  voiceRef.current = world.speech?.voice || voiceRef.current;
  function pump() {
    if (generating.current || !ready.current) return;
    const next = queue.current.shift();
    if (!next) return;
    generating.current = true;
    generatingId.current = next.id;
    if (!active.current) setStatus('Preparing speech…');
    worker.current?.postMessage({
      type: 'speak',
      ...next,
      voice: voiceRef.current,
    });
  }
  function playNext() {
    if (active.current || browserFallback.current) return;
    const blob = audioQueue.current.shift();
    if (!blob) {
      if (!generating.current && queue.current.length === 0)
        setStatus('Voice ready');
      return;
    }
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = URL.createObjectURL(blob);
    const player = new Audio(url.current);
    audio.current = player;
    player.volume = volumeRef.current;
    active.current = true;
    player.onended = () => {
      active.current = false;
      setStatus(generating.current ? 'Preparing next passage…' : 'Voice ready');
      playNext();
    };
    void player
      .play()
      .then(() => setStatus('Reading aloud'))
      .catch(() => {
        setStatus('Playback blocked. Press Replay to try again.');
        active.current = false;
      });
  }
  function stop() {
    generation.current++;
    generatingId.current = '';
    queue.current = [];
    audioQueue.current = [];
    active.current = false;
    generating.current = false;
    setPaused(false);
    audio.current?.pause();
    audio.current = null;
    if (typeof window !== 'undefined') window.speechSynthesis?.cancel();
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = '';
  }
  function speakWithBrowser(text: string) {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      setStatus('No browser speech engine is available. Text play remains available.');
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    active.current = true;
    utterance.volume = volumeRef.current;
    utterance.rate = 0.95;
    utterance.onstart = () => setStatus('Reading aloud · browser voice');
    utterance.onend = () => { active.current = false; setStatus('Browser voice ready'); };
    utterance.onerror = () => { active.current = false; setStatus('Browser voice could not play. Text remains available.'); };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setEngine('browser');
  }
  function disable() {
    stop();
    worker.current?.terminate();
    worker.current = null;
    ready.current = false;
    browserFallback.current = false;
    setEnabled(false);
    setStatus('');
  }
  function enqueue(entry: NonNullable<typeof latest>) {
    if (seen.current.has(entry.id)) return;
    seen.current.add(entry.id);
    const gen = generation.current;
    const job = pendingText.current.then(async () => {
      let text = entry.prose || entry.text;
      try {
        text = (await api<{ text: string }>('/narrate/' + entry.id, {})).text;
      } catch {
        /* Confirmed text is always a usable fallback. */
      }
      if (gen !== generation.current) return;
      if (browserFallback.current) {
        speakWithBrowser(text);
        return;
      }
      const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [text];
      // Two-sentence chunks start faster than one long clip. As soon as a
      // chunk is ready it plays while the worker prepares the next one,
      // hiding most inference time without restoring sentence-sized gaps.
      const bounded = sentences.slice(0, 12);
      for (let i = 0; i < bounded.length; i += 2)
        queue.current.push({
          id: gen + '-' + entry.id + '-' + i / 2,
          text: bounded.slice(i, i + 2).join(' ').trim(),
        });
      // Bound backlog on slower devices; the complete text stays in the journal.
      if (queue.current.length > 24) queue.current = queue.current.slice(-24);
      pump();
    });
    pendingText.current = job.catch(() => {});
    return job;
  }
  function enable() {
    if (enabled) {
      disable();
      return;
    }
    setEnabled(true);
    browserFallback.current = false;
    setStatus('Downloading voice model…');
    seen.current = new Set(world.journal.slice(0, -1).map((e) => e.id));
    const w = new SpeechWorker();
    worker.current = w;
    w.onmessage = async ({ data }) => {
      if (data.type === 'progress')
        setStatus(`Loading voice · ${data.progress}%`);
      if (data.type === 'backend') setStatus(data.message);
      if (data.type === 'ready') {
        ready.current = true;
        setEngine('kokoro');
        setStatus(`Voice ready · ${data.backend === 'webgpu' ? 'WebGPU' : 'WASM'}`);
        if (latestRef.current) await enqueue(latestRef.current);
      }
      if (data.type === 'error') {
        browserFallback.current = true;
        ready.current = false;
        setStatus(`Kokoro unavailable; using browser voice${data.detail ? ` · ${data.detail}` : ''}`);
        active.current = false;
        const currentEntry = latestRef.current;
        if (currentEntry) void enqueue(currentEntry);
      }
      if (data.type === 'audio' && data.id === generatingId.current) {
        generating.current = false;
        generatingId.current = '';
        audioQueue.current.push(data.blob);
        playNext();
        pump();
      }
    };
    w.onerror = (event) => {
      console.error('Speech worker startup failed:', event.message);
      ready.current = false;
      browserFallback.current = true;
      setStatus('Kokoro is unavailable here; using the browser voice.');
      const currentEntry = latestRef.current;
      if (currentEntry) void enqueue(currentEntry);
    };
    w.postMessage({ type: 'load' });
  }
  useEffect(() => {
    const entry = latestRef.current;
    if (enabled && (ready.current || browserFallback.current) && entry)
      void enqueue(entry);
  }, [latest?.id, enabled]);
  useEffect(
    () => () => {
      generation.current++;
      worker.current?.terminate();
      audio.current?.pause();
      if (url.current) URL.revokeObjectURL(url.current);
    },
    [],
  );
  return (
    <div className="voice-controls">
      <Button
        variant="ghost"
        onClick={enable}
        aria-label={enabled ? 'Disable voice' : 'Enable browser voice'}
      >
        {enabled ? <VolumeX size={16} /> : <Volume2 size={16} />}{' '}
        {enabled ? 'Mute' : 'Enable voice'}
      </Button>
      {enabled && (
        <>
          <Button
            variant="ghost"
            aria-label={paused ? 'Resume narration' : 'Pause narration'}
            onClick={() => {
              if (engine === 'browser') {
                if (paused) { window.speechSynthesis.resume(); setPaused(false); }
                else { window.speechSynthesis.pause(); setPaused(true); }
                return;
              }
              if (!audio.current) return;
              if (paused) {
                void audio.current
                  .play()
                  .then(() => setPaused(false))
                  .catch(() => setStatus('Playback blocked. Try Replay.'));
              } else {
                audio.current.pause();
                setPaused(true);
              }
            }}
          >
            {paused ? <Play size={15} /> : <Pause size={15} />}
          </Button>
          <Button
            variant="ghost"
            aria-label="Skip narration"
            onClick={() => {
              stop();
              setStatus('Skipped');
            }}
          >
            <SkipForward size={15} />
          </Button>
          <Button
            variant="ghost"
            aria-label="Replay latest narration"
            onClick={() => {
              if (engine === 'browser' && latest) {
                speakWithBrowser(latest.prose || latest.text);
                return;
              }
              if (paused && audio.current) {
                audio.current.currentTime = 0;
                void audio.current
                  .play()
                  .then(() => {
                    setPaused(false);
                    setStatus('Reading aloud');
                  })
                  .catch(() =>
                    setStatus('Playback is blocked by your browser.'),
                  );
                return;
              }
              stop();
              if (latest) {
                seen.current.delete(latest.id);
                void enqueue(latest);
              }
            }}
          >
            <RotateCcw size={15} />
          </Button>
          <Slider
            aria-label="Voice volume"
            value={[volume]}
            min={0}
            max={1}
            step={0.05}
            onValueChange={(v) => {
              const n = Array.isArray(v) ? v[0] : v;
              setVolume(n);
              volumeRef.current = n;
              if (audio.current) audio.current.volume = n;
            }}
          />
          <output>{status}</output>
        </>
      )}
    </div>
  );
}
