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
 * The key names are options because the spec does not say how each list pages yet (limit+offset, limit only,
 * cursor, page+pageSize all exist); once it does, the generator can fill them in per operation.
 */
export async function* paginate<I extends Record<string, any>>(fn: (input: I) => Promise<any>, input: I, opts: PaginateOptions = {}): AsyncGenerator<any, void, undefined> {
  const { pageSize = 100, limitKey = "limit", offsetKey = "offset", cursorKey = "cursor", rows: rowsOf = defaultRows, nextCursor: nextOf = defaultNext, maxPages = 1000 } = opts;
  let offset = 0, cursor: string | undefined, pages = 0, lastPage: string | undefined;
  while (pages++ < maxPages) {
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
