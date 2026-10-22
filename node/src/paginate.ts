/** Pages through a list operation that takes `limit` + `offset` (most fastn list calls) or `cursor`. */
export interface PaginateOptions {
  /** Rows per request (default 100). */
  pageSize?: number;
  /** Input key for the page size (default "limit"). */
  limitKey?: string;
  /** Input key for the offset (default "offset"); set to null for cursor-only lists. */
  offsetKey?: string | null;
  /** Input key for the cursor (default "cursor"). */
  cursorKey?: string;
  /** Picks the rows out of a response (default: `data` when it is an array, else `data.items`/`items`/`records`). */
  rows?: (res: any) => any[] | undefined;
  /** Picks the next cursor out of a response (default: `nextCursor` / `data.nextCursor` / `cursor`). */
  nextCursor?: (res: any) => string | undefined;
  /** Safety cap on pages (default 1000). */
  maxPages?: number;
}

const defaultRows = (res: any): any[] | undefined => {
  if (Array.isArray(res)) return res;
  if (Array.isArray(res?.data)) return res.data;
  for (const k of ["items", "records", "rows"]) { if (Array.isArray(res?.data?.[k])) return res.data[k]; if (Array.isArray(res?.[k])) return res[k]; }
  return undefined;
};
const defaultNext = (res: any): string | undefined => res?.nextCursor ?? res?.data?.nextCursor ?? res?.pagination?.nextCursor ?? res?.data?.pagination?.nextCursor ?? undefined;

/**
 * `for await (const org of paginate((i) => client.orgs.listOrgs(i), { type: "end_org" })) ...`
 * Stops when a page comes back shorter than `pageSize` (offset lists) or without a next cursor (cursor lists).
 */
export async function* paginate<I extends Record<string, any>, R>(fn: (input: I) => Promise<R>, input: I, opts: PaginateOptions = {}): AsyncGenerator<any, void, undefined> {
  const pageSize = opts.pageSize ?? 100, limitKey = opts.limitKey ?? "limit", offsetKey = opts.offsetKey === undefined ? "offset" : opts.offsetKey, cursorKey = opts.cursorKey ?? "cursor";
  const rowsOf = opts.rows ?? defaultRows, nextOf = opts.nextCursor ?? defaultNext;
  let offset = 0, cursor: string | undefined, pages = 0, lastPage: string | undefined;
  while (pages++ < (opts.maxPages ?? 1000)) {
    const page: Record<string, any> = { ...input, [limitKey]: pageSize };
    if (cursor) page[cursorKey] = cursor; else if (offsetKey) page[offsetKey] = offset;
    const res = await fn(page as I);
    const rows = rowsOf(res) ?? [];
    // A list that ignores limit/offset answers the same rows every time; stop instead of looping.
    const sig = JSON.stringify(rows.length ? [rows[0], rows.at(-1), rows.length] : null);
    if (sig === lastPage) return;
    lastPage = sig;
    for (const r of rows) yield r;
    const next = nextOf(res);
    if (next && next !== cursor) { cursor = next; continue; }
    if (!offsetKey || rows.length < pageSize) return;
    offset += rows.length;
  }
}
