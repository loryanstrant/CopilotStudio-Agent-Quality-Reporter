import { describe, expect, it } from "vitest";
import { applyFilters, applySelection, type Column } from "./DataTable";

/**
 * The two rules a table narrows by, and why they are not the same rule.
 *
 * Typing into a filter box is a substring search, because that is what anybody
 * expects from a filter box. Clicking a row is an exact selection, because a
 * substring cannot express "this person and not the other one" — and the
 * overlap that breaks it is ordinary rather than contrived, since short local
 * parts are ordinary. These tests exist because selecting by substring shipped
 * once and could not distinguish Amy from Tamy.
 */

interface Creator {
  upn: string;
  display_name: string;
  agents: string[];
}

const AMY: Creator = {
  upn: "amy@contoso.com",
  display_name: "Amy Rose",
  agents: ["Amy's bot"],
};
const TAMY: Creator = {
  upn: "tamy@contoso.com",
  display_name: "Tamy Okafor",
  agents: ["Tamy's bot", "Tamy's other bot"],
};
const ZARA: Creator = {
  upn: "zara@contoso.com",
  display_name: "Zara Quinn",
  agents: [],
};

const ROWS = [AMY, TAMY, ZARA];

/** The real page's Creator column: one cell carrying both the name and the
 *  sign-in address, so typing either finds the person. */
const COLUMNS: Column<Creator>[] = [
  { key: "name", header: "Creator", accessor: (r) => `${r.display_name} ${r.upn}` },
];

const rowKey = (r: Creator) => r.upn;

describe("applySelection — what a click does", () => {
  it("selects exactly the clicked row when another UPN contains it", () => {
    // The bug this file exists for. "amy@contoso.com" is a substring of
    // "tamy@contoso.com", so a substring filter cannot pick Amy alone.
    expect(applySelection(ROWS, rowKey, AMY.upn)).toEqual([AMY]);
  });

  it("gives the clicked creator's agents, not both creators'", () => {
    const [selected] = applySelection(ROWS, rowKey, AMY.upn);
    expect(selected.agents).toEqual(["Amy's bot"]);
  });

  it("selects the longer UPN cleanly too", () => {
    expect(applySelection(ROWS, rowKey, TAMY.upn)).toEqual([TAMY]);
  });

  it("passes every row through when nothing is selected", () => {
    expect(applySelection(ROWS, rowKey, null)).toHaveLength(3);
    expect(applySelection(ROWS, rowKey, undefined)).toHaveLength(3);
  });

  it("shows nobody rather than everybody when the key is gone", () => {
    // A creator who has left the data between load and click must not silently
    // widen the page back out to the whole tenant.
    expect(applySelection(ROWS, rowKey, "ghost@contoso.com")).toEqual([]);
  });
});

describe("applyFilters — what typing does", () => {
  it("stays a substring match, which is what a filter box is for", () => {
    // Deliberately the behaviour the click must NOT use: typing "amy" finds
    // Tamy too, and that is correct for someone searching.
    expect(applyFilters(ROWS, COLUMNS, { name: "amy" })).toEqual([AMY, TAMY]);
  });

  it("is case-insensitive and matches the display name as well", () => {
    expect(applyFilters(ROWS, COLUMNS, { name: "ZARA QUINN" })).toEqual([ZARA]);
  });

  it("ignores whitespace-only terms", () => {
    expect(applyFilters(ROWS, COLUMNS, { name: "   " })).toHaveLength(3);
  });

  it("ANDs across columns", () => {
    const columns: Column<Creator>[] = [
      ...COLUMNS,
      { key: "upn", header: "Sign-in", accessor: (r) => r.upn },
    ];
    expect(applyFilters(ROWS, columns, { name: "amy", upn: "tamy" })).toEqual([TAMY]);
  });
});

describe("the two together, in the order the table applies them", () => {
  it("a selection wins over a filter that would have left two rows", () => {
    const shown = applySelection(
      applyFilters(ROWS, COLUMNS, { name: "amy" }),
      rowKey,
      AMY.upn,
    );
    expect(shown).toEqual([AMY]);
  });
});
