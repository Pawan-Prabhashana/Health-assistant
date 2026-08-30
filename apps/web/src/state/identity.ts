// Client identity state: the phone the user identified with, persisted across
// reloads. Only the phone (which the user entered themselves) is stored — never
// the resolved patient record, MRN, name, or clinical status. On boot the app
// re-resolves the full patient from the backend using this phone, so the durable
// footprint stays minimal and never goes stale.

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface IdentityState {
  phone: string | null;
  setPhone: (phone: string) => void;
  clear: () => void;
}

export const STORAGE_KEY = 'sahana.identity';

export const useIdentity = create<IdentityState>()(
  persist(
    (set) => ({
      phone: null,
      setPhone: (phone) => {
        set({ phone });
      },
      clear: () => {
        set({ phone: null });
      },
    }),
    {
      name: STORAGE_KEY,
      // Persist only the phone; nothing sensitive beyond what the user typed.
      partialize: (state) => ({ phone: state.phone }),
    },
  ),
);
