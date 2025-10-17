import { create } from 'zustand'

export const useAppStore = create((set) => ({
  // Session state
  sessionId: null,
  phaseNumber: 0,
  totalPhases: 0,

  // Settings
  keyPresent: false,
  llmEnabled: true,

  // Actions
  setSession: (sessionId, phaseNumber, totalPhases) =>
    set({ sessionId, phaseNumber, totalPhases }),

  clearSession: () =>
    set({ sessionId: null, phaseNumber: 0, totalPhases: 0 }),

  setKeyPresent: (keyPresent) => set({ keyPresent }),
  setLlmEnabled: (llmEnabled) => set({ llmEnabled }),
}))