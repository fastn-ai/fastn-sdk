import { describe, it, expect } from "vitest";
import { paginate } from "../../src/index.js";

describe("paginate", () => {
  it("walks offset pages until a short page", async () => {
    const seen: any[] = []; const rows = Array.from({ length: 7 }, (_, i) => ({ i }));
    const fn = async (input: any) => { seen.push(input); return { data: rows.slice(input.offset, input.offset + input.limit) }; };
    const out: any[] = []; for await (const r of paginate(fn, { status: "x" }, { pageSize: 3 })) out.push(r);
    expect(out.map((r) => r.i)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(seen).toEqual([{ status: "x", limit: 3, offset: 0 }, { status: "x", limit: 3, offset: 3 }, { status: "x", limit: 3, offset: 6 }]);
  });
  it("follows cursors", async () => {
    const pages: Record<string, any> = { start: { data: { records: [1, 2], nextCursor: "c2" } }, c2: { data: { records: [3], nextCursor: null } } };
    const fn = async (input: any) => pages[input.cursor ?? "start"];
    const out: any[] = []; for await (const r of paginate(fn, {}, { offsetKey: null })) out.push(r);
    expect(out).toEqual([1, 2, 3]);
  });
});
