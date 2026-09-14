import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { BinderProvider, useBinder, SLOTS_PER_PAGE } from "@/context/binder-context";

describe("BinderContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <BinderProvider>{children}</BinderProvider>
  );

  it("initializes with a default binder containing 2 empty pages", () => {
    const { result } = renderHook(() => useBinder(), { wrapper });
    expect(result.current.binder.pages.length).toBe(2);
    expect(result.current.totalCardCount).toBe(0);
    expect(result.current.activePageIndex).toBe(0);
  });

  it("adds and removes cards from binder slots", () => {
    const { result } = renderHook(() => useBinder(), { wrapper });

    act(() => {
      result.current.addCardToSlot(0, 0, "base1-4");
    });

    expect(result.current.totalCardCount).toBe(1);
    expect(result.current.isCardInBinder("base1-4")).toBe(true);
    expect(result.current.findCardSlot("base1-4")).toEqual({ pageIndex: 0, slotIndex: 0 });

    act(() => {
      result.current.removeCardFromSlot(0, 0);
    });

    expect(result.current.totalCardCount).toBe(0);
    expect(result.current.isCardInBinder("base1-4")).toBe(false);
  });

  it("quickAddCard finds the first available slot across pages", () => {
    const { result } = renderHook(() => useBinder(), { wrapper });

    let slot1: { pageIndex: number; slotIndex: number } | null = null;
    let slot2: { pageIndex: number; slotIndex: number } | null = null;

    act(() => {
      slot1 = result.current.quickAddCard("card-1");
    });
    act(() => {
      slot2 = result.current.quickAddCard("card-2");
    });

    expect(slot1).toEqual({ pageIndex: 0, slotIndex: 0 });
    expect(slot2).toEqual({ pageIndex: 0, slotIndex: 1 });
    expect(result.current.totalCardCount).toBe(2);
  });

  it("allows adding a new page to the binder", () => {
    const { result } = renderHook(() => useBinder(), { wrapper });

    act(() => {
      result.current.addPage();
    });

    expect(result.current.binder.pages.length).toBe(3);
  });

  it("moves a card from one slot to another", () => {
    const { result } = renderHook(() => useBinder(), { wrapper });

    act(() => {
      result.current.addCardToSlot(0, 2, "base1-4");
    });

    expect(result.current.findCardSlot("base1-4")).toEqual({ pageIndex: 0, slotIndex: 2 });

    act(() => {
      result.current.moveCard(0, 2, 1, 5);
    });

    expect(result.current.findCardSlot("base1-4")).toEqual({ pageIndex: 1, slotIndex: 5 });
    expect(result.current.binder.pages[0].slots[2]).toBeUndefined();
    expect(result.current.binder.pages[1].slots[5]).toBe("base1-4");
  });
});
