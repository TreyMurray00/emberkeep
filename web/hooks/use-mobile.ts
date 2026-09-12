import * as React from 'react';

const MOBILE_BREAKPOINT = 768;

const mobileQuery = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`;

function subscribe(onStoreChange: () => void) {
  const query = window.matchMedia(mobileQuery);
  query.addEventListener('change', onStoreChange);
  return () => query.removeEventListener('change', onStoreChange);
}

function getSnapshot() {
  return window.matchMedia(mobileQuery).matches;
}

export function useIsMobile() {
  return React.useSyncExternalStore(subscribe, getSnapshot, () => false);
}
