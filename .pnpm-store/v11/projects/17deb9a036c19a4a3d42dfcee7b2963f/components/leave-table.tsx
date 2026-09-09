'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog';
import { api } from '@/lib/game';
export function LeaveTable({ finished }: { finished: boolean }) {
  const [open, setOpen] = useState(false),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger render={<Button variant="ghost" />}>
        {finished ? 'New adventure' : 'Leave table'}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogTitle>
          {finished ? 'Begin a new adventure?' : 'Leave this table?'}
        </AlertDialogTitle>
        <AlertDialogDescription>
          {finished
            ? 'Your completed chronicle stays in the local database. This browser will start with a new character.'
            : 'Your draft and class reservation will be released. You can return with the invitation code and build a new character.'}
        </AlertDialogDescription>
        {error && <p role="alert">{error}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel>Stay here</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api('/leave', {});
                location.assign('/');
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Continue
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
