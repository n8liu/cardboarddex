"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { StoredBinder, StoredBinderPage } from "@/types/binder";

const BINDER_STORAGE_KEY = "cardboarddex_binder";
const BINDER_EVENT_KEY = "cardboarddex_binder_updated";
export const SLOTS_PER_PAGE = 9; // 3x3 standard 9-pocket collector's sleeve

function createEmptyPage(index: number): StoredBinderPage {
  return {
    id: `page-${Date.now()}-${index}`,
    name: `Page ${index + 1}`,
    slots: {},
  };
}

function getDefaultBinder(): StoredBinder {
  return {
    version: 1,
    name: "My Collection Binder",
    pages: [createEmptyPage(0), createEmptyPage(1)],
  };
}

interface BinderContextType {
  binder: StoredBinder;
  activePageIndex: number;
  setActivePageIndex: (index: number) => void;
  addCardToSlot: (pageIndex: number, slotIndex: number, cardId: string) => void;
  removeCardFromSlot: (pageIndex: number, slotIndex: number) => void;
  moveCard: (fromPage: number, fromSlot: number, toPage: number, toSlot: number) => void;
  addPage: () => void;
  removePage: (pageIndex: number) => void;
  setBinderName: (name: string) => void;
  clearBinder: () => void;
  totalCardCount: number;
  allCardIds: string[];
  quickAddCard: (cardId: string) => { pageIndex: number; slotIndex: number } | null;
  isCardInBinder: (cardId: string) => boolean;
  findCardSlot: (cardId: string) => { pageIndex: number; slotIndex: number } | null;
  isHydrated: boolean;
}

const BinderContext = createContext<BinderContextType | null>(null);

export function BinderProvider({ children }: { children: React.ReactNode }) {
  const [binder, setBinder] = useState<StoredBinder>(getDefaultBinder);
  const [activePageIndex, setActivePageIndex] = useState<number>(0);
  const [isHydrated, setIsHydrated] = useState<boolean>(false);

  // Helper to persist only clean card ID mapping
  const persist = useCallback((nextBinder: StoredBinder) => {
    // Sanitize: ensure only card IDs and valid slot numbers are kept
    const sanitized: StoredBinder = {
      version: 1,
      name: nextBinder.name || "My Collection Binder",
      pages: nextBinder.pages.map((p, idx) => {
        const cleanSlots: Record<number, string> = {};
        for (const [sKey, cid] of Object.entries(p.slots)) {
          const sNum = parseInt(sKey, 10);
          if (!isNaN(sNum) && sNum >= 0 && sNum < SLOTS_PER_PAGE && typeof cid === "string" && cid.trim()) {
            cleanSlots[sNum] = cid.trim();
          }
        }
        return {
          id: p.id || `page-${idx}`,
          name: p.name || `Page ${idx + 1}`,
          slots: cleanSlots,
        };
      }),
    };

    setBinder(sanitized);
    try {
      localStorage.setItem(BINDER_STORAGE_KEY, JSON.stringify(sanitized));
      window.dispatchEvent(new Event(BINDER_EVENT_KEY));
    } catch (err) {
      console.error("[BinderContext] Failed persisting to localStorage:", err);
    }
  }, []);

  // Hydrate from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(BINDER_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && Array.isArray(parsed.pages) && parsed.pages.length > 0) {
          // Normalize slots to ensure strictly card IDs only
          const normalized: StoredBinder = {
            version: 1,
            name: typeof parsed.name === "string" ? parsed.name : "My Collection Binder",
            pages: parsed.pages.map((p: any, idx: number) => {
              const cleanSlots: Record<number, string> = {};
              if (p && typeof p.slots === "object") {
                for (const [k, v] of Object.entries(p.slots)) {
                  const sNum = parseInt(k, 10);
                  if (!isNaN(sNum) && sNum >= 0 && sNum < SLOTS_PER_PAGE && typeof v === "string" && v.trim()) {
                    cleanSlots[sNum] = v.trim();
                  }
                }
              }
              return {
                id: p?.id || `page-${idx}`,
                name: p?.name || `Page ${idx + 1}`,
                slots: cleanSlots,
              };
            }),
          };
          setBinder(normalized);
        }
      }
    } catch (err) {
      console.error("[BinderContext] Error reading binder from localStorage:", err);
    } finally {
      setIsHydrated(true);
    }

    const handleSync = () => {
      try {
        const stored = localStorage.getItem(BINDER_STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed && Array.isArray(parsed.pages)) {
            setBinder(parsed);
          }
        }
      } catch {}
    };

    window.addEventListener("storage", handleSync);
    window.addEventListener(BINDER_EVENT_KEY, handleSync);
    return () => {
      window.removeEventListener("storage", handleSync);
      window.removeEventListener(BINDER_EVENT_KEY, handleSync);
    };
  }, []);

  // Compute all unique card IDs across all pages
  const allCardIds = useMemo(() => {
    const ids = new Set<string>();
    for (const page of binder.pages) {
      for (const cid of Object.values(page.slots)) {
        if (cid) ids.add(cid);
      }
    }
    return Array.from(ids);
  }, [binder]);

  // Compute total filled slots count
  const totalCardCount = useMemo(() => {
    let count = 0;
    for (const page of binder.pages) {
      count += Object.keys(page.slots).length;
    }
    return count;
  }, [binder]);

  const addCardToSlot = useCallback(
    (pageIndex: number, slotIndex: number, cardId: string) => {
      if (!cardId) return;
      setBinder((prev) => {
        const newPages = [...prev.pages];
        if (pageIndex < 0 || pageIndex >= newPages.length) return prev;
        const targetPage = { ...newPages[pageIndex], slots: { ...newPages[pageIndex].slots } };
        targetPage.slots[slotIndex] = cardId;
        newPages[pageIndex] = targetPage;
        const next = { ...prev, pages: newPages };
        persist(next);
        return next;
      });
    },
    [persist]
  );

  const removeCardFromSlot = useCallback(
    (pageIndex: number, slotIndex: number) => {
      setBinder((prev) => {
        const newPages = [...prev.pages];
        if (pageIndex < 0 || pageIndex >= newPages.length) return prev;
        const targetPage = { ...newPages[pageIndex], slots: { ...newPages[pageIndex].slots } };
        delete targetPage.slots[slotIndex];
        newPages[pageIndex] = targetPage;
        const next = { ...prev, pages: newPages };
        persist(next);
        return next;
      });
    },
    [persist]
  );

  const moveCard = useCallback(
    (fromPage: number, fromSlot: number, toPage: number, toSlot: number) => {
      setBinder((prev) => {
        const newPages = [...prev.pages];
        if (
          fromPage < 0 ||
          fromPage >= newPages.length ||
          toPage < 0 ||
          toPage >= newPages.length
        ) {
          return prev;
        }

        const sourcePage = { ...newPages[fromPage], slots: { ...newPages[fromPage].slots } };
        const destPage =
          fromPage === toPage
            ? sourcePage
            : { ...newPages[toPage], slots: { ...newPages[toPage].slots } };

        const movingCardId = sourcePage.slots[fromSlot];
        const existingCardId = destPage.slots[toSlot];

        if (!movingCardId) return prev;

        // Perform swap
        if (existingCardId) {
          sourcePage.slots[fromSlot] = existingCardId;
        } else {
          delete sourcePage.slots[fromSlot];
        }
        destPage.slots[toSlot] = movingCardId;

        newPages[fromPage] = sourcePage;
        newPages[toPage] = destPage;

        const next = { ...prev, pages: newPages };
        persist(next);
        return next;
      });
    },
    [persist]
  );

  const addPage = useCallback(() => {
    setBinder((prev) => {
      const next = {
        ...prev,
        pages: [...prev.pages, createEmptyPage(prev.pages.length)],
      };
      persist(next);
      setActivePageIndex(next.pages.length - 1);
      return next;
    });
  }, [persist]);

  const removePage = useCallback(
    (pageIndex: number) => {
      setBinder((prev) => {
        if (prev.pages.length <= 1) {
          // Reset to 1 empty page rather than 0
          const next = {
            ...prev,
            pages: [createEmptyPage(0)],
          };
          persist(next);
          setActivePageIndex(0);
          return next;
        }
        const newPages = prev.pages.filter((_, idx) => idx !== pageIndex);
        const next = { ...prev, pages: newPages };
        persist(next);
        setActivePageIndex((curr) => Math.min(curr, newPages.length - 1));
        return next;
      });
    },
    [persist]
  );

  const setBinderName = useCallback(
    (name: string) => {
      setBinder((prev) => {
        const next = { ...prev, name: name.trim() || "My Collection Binder" };
        persist(next);
        return next;
      });
    },
    [persist]
  );

  const clearBinder = useCallback(() => {
    const next = getDefaultBinder();
    persist(next);
    setActivePageIndex(0);
  }, [persist]);

  const quickAddCard = useCallback(
    (cardId: string): { pageIndex: number; slotIndex: number } | null => {
      if (!cardId) return null;

      // Find first empty slot
      for (let pIdx = 0; pIdx < binder.pages.length; pIdx++) {
        const page = binder.pages[pIdx];
        for (let sIdx = 0; sIdx < SLOTS_PER_PAGE; sIdx++) {
          if (!page.slots[sIdx]) {
            addCardToSlot(pIdx, sIdx, cardId);
            return { pageIndex: pIdx, slotIndex: sIdx };
          }
        }
      }

      // If all slots across all pages are full, create a new page and place in slot 0
      const newPageIdx = binder.pages.length;
      addPage();
      addCardToSlot(newPageIdx, 0, cardId);
      return { pageIndex: newPageIdx, slotIndex: 0 };
    },
    [binder.pages, addCardToSlot, addPage]
  );

  const isCardInBinder = useCallback(
    (cardId: string): boolean => {
      if (!cardId) return false;
      return allCardIds.includes(cardId);
    },
    [allCardIds]
  );

  const findCardSlot = useCallback(
    (cardId: string): { pageIndex: number; slotIndex: number } | null => {
      if (!cardId) return null;
      for (let pIdx = 0; pIdx < binder.pages.length; pIdx++) {
        const page = binder.pages[pIdx];
        for (const [sKey, cid] of Object.entries(page.slots)) {
          if (cid === cardId) {
            return { pageIndex: pIdx, slotIndex: parseInt(sKey, 10) };
          }
        }
      }
      return null;
    },
    [binder.pages]
  );

  return (
    <BinderContext.Provider
      value={{
        binder,
        activePageIndex,
        setActivePageIndex,
        addCardToSlot,
        removeCardFromSlot,
        moveCard,
        addPage,
        removePage,
        setBinderName,
        clearBinder,
        totalCardCount,
        allCardIds,
        quickAddCard,
        isCardInBinder,
        findCardSlot,
        isHydrated,
      }}
    >
      {children}
    </BinderContext.Provider>
  );
}

export function useBinder(): BinderContextType {
  const context = useContext(BinderContext);
  if (!context) {
    throw new Error("useBinder must be used within a BinderProvider");
  }
  return context;
}
