// The active-session and view state. Kept in memory (not persisted): the active
// session is re-chosen after a reload, which avoids pointing at a session that
// was deleted in another tab. Holds only opaque identifiers, no content.

import { create } from 'zustand';

export type View = 'chat' | 'health';

interface SessionState {
  activeSessionId: string | null;
  view: View;
  /** Whether the sidebar drawer is open on mobile (ignored at desktop widths). */
  sidebarOpen: boolean;
  setActiveSession: (sessionId: string | null) => void;
  setView: (view: View) => void;
  setSidebarOpen: (open: boolean) => void;
}

export const useSessionState = create<SessionState>((set) => ({
  activeSessionId: null,
  view: 'chat',
  sidebarOpen: false,
  setActiveSession: (activeSessionId) => {
    set({ activeSessionId });
  },
  setView: (view) => {
    set({ view });
  },
  setSidebarOpen: (sidebarOpen) => {
    set({ sidebarOpen });
  },
}));
