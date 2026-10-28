// Typed domain methods on top of the unified API: `customer.calendar.*` and `customer.crm.*`. Each method names its
// fields (the catalog's own names, e.g. start_time, first_name), fills category/entity, and picks the provider from
// what the customer has connected unless `opts.provider` says otherwise. Everything here is the unified record
// routes underneath, so `customer.records({...})` does the same with untyped input.
import type { FastnApis } from "./generated/api.js";
import type { RequestOptions } from "./transport.js";
import type { UnifiedOperation } from "./catalog.js";
import { FastnApiError } from "./errors.js";

/** Options on every typed method: the request options plus which provider and connection to run against. */
export interface DomainCallOptions extends RequestOptions {
  /** Connector slug (e.g. "hubspot"). Default: the one provider the customer has connected for the entity. */
  provider?: string;
  /** One of the customer's connections on that provider, when they hold several. Ids come from customer.connections(). */
  connectionId?: string;
}

/** An ISO 8601 timestamp, or a Date (sent as its ISO string). */
export type DateInput = string | Date;

/** One record as the unified API returns it: the provider's id, the provider, and the canonical fields. */
export interface UnifiedRecord<D> {
  id: string;
  provider: string;
  data: D;
  /** Fields the provider does not map were dropped, and said so here. Empty or absent when nothing was dropped. */
  warnings?: string[];
  [key: string]: unknown;
}

/** One page of records. Pass `nextCursor` as `cursor` to read the next page while `hasMore` is true. */
export interface UnifiedPage<D> {
  records: UnifiedRecord<D>[];
  nextCursor?: string | null;
  hasMore?: boolean | null;
  provider: string;
  warnings?: string[];
  [key: string]: unknown;
}

/** The answer of a delete. */
export interface UnifiedDeleted {
  id: string;
  provider: string;
  deleted?: boolean;
  warnings?: string[];
  [key: string]: unknown;
}

export interface PageInput { page_size?: number; cursor?: string }
/** `find` takes a page size only: the search route has no cursor. */
export interface FindInput { page_size?: number }

/** Who answers provider questions for one customer (the Customer object). */
export interface ProviderResolver {
  readonly api: FastnApis;
  /** The slug of the one provider this customer has connected for the entity that supports `op`. */
  providerFor(category: string, entity: string, op: UnifiedOperation): Promise<string>;
  /** Forgets the cached provider answer for an entity (after a reconnect or a provider error). */
  forgetProvider(category: string, entity: string): void;
}

/** Date values become ISO strings; everything else is sent as given. */
export function wireRecord<T extends object>(record: T): Record<string, any> {
  const out: Record<string, any> = {};
  for (const [k, v] of Object.entries(record)) out[k] = v instanceof Date ? v.toISOString() : v;
  return out;
}

const PROVIDER_ERROR = /PROVIDER|CONNECTION/i;
/** An empty id would call the collection route instead of one record: refuse it before the request. */
const idOf = (id: string): string => { if (typeof id !== "string" || !id) throw new TypeError("a record id is required"); return id; };

/**
 * One entity with typed input and output. `C` = create input, `R` = the record's canonical fields as read,
 * `F` = search filters. Wraps `Records` with provider resolution and Date handling.
 */
export class Entity<C extends object, R, F extends object = Record<string, never>> {
  constructor(protected readonly cust: ProviderResolver, readonly category: string, readonly entity: string) {}

  /** category/entity/provider/connection_id for one call, with the provider resolved (or taken from opts). */
  protected async scope(op: UnifiedOperation, opts?: DomainCallOptions): Promise<{ category: string; entity: string; provider: string; connection_id?: string }> {
    const provider = opts?.provider ?? (await this.cust.providerFor(this.category, this.entity, op));
    return { category: this.category, entity: this.entity, provider, ...(opts?.connectionId ? { connection_id: opts.connectionId } : {}) };
  }
  /** Runs one call; a provider or connection error forgets the cached provider so the next call resolves again. */
  protected async run<T>(op: UnifiedOperation, opts: DomainCallOptions | undefined, f: (s: Awaited<ReturnType<Entity<C, R, F>["scope"]>>, o: RequestOptions | undefined) => Promise<unknown>): Promise<T> {
    const { provider: _p, connectionId: _c, ...rest } = opts ?? {};
    const reqOpts = Object.keys(rest).length ? rest : undefined;
    try {
      return (await f(await this.scope(op, opts), reqOpts)) as T;
    } catch (err) {
      if (err instanceof FastnApiError && PROVIDER_ERROR.test(err.code ?? "")) this.cust.forgetProvider(this.category, this.entity);
      throw err;
    }
  }
  private get u() { return this.cust.api.unified; }

  /** Creates one record. Pass `opts.idempotencyKey` so a retry cannot create it twice. */
  create(record: C, opts?: DomainCallOptions): Promise<UnifiedRecord<R>> { return this.run("create", opts, (s, o) => this.u.createUnifiedRecord({ ...s, record: wireRecord(record) }, o)); }
  /** One record by its provider id. */
  get(id: string, opts?: DomainCallOptions): Promise<UnifiedRecord<R>> { return this.run("get", opts, (s, o) => this.u.getUnifiedRecord({ ...s, id: idOf(id) }, o)); }
  /** A page of records. */
  list(input: PageInput = {}, opts?: DomainCallOptions): Promise<UnifiedPage<R>> { return this.run("list", opts, (s, o) => this.u.listUnifiedRecords({ ...s, ...input }, o)); }
  /** Records matching the filters (the provider's own search). One page only: the search route has no cursor, so
   *  narrow the filters or raise `page_size` to see more; `list` pages with a cursor. */
  find(filters: F, input: FindInput = {}, opts?: DomainCallOptions): Promise<UnifiedPage<R>> {
    if ("cursor" in input) return Promise.reject(new TypeError("find() has no cursor: the search route answers one page; narrow the filters, raise page_size, or page with list()"));
    return this.run("search", opts, (s, o) => this.u.searchUnifiedRecords({ ...s, ...input, filters: wireRecord(filters) as any }, o));
  }
  /** Changes the given fields and leaves the rest. */
  update(id: string, patch: Partial<C>, opts?: DomainCallOptions): Promise<UnifiedRecord<R>> { return this.run("update", opts, (s, o) => this.u.updateUnifiedRecord({ ...s, id: idOf(id), record: wireRecord(patch) }, o)); }
  /** Deletes (or archives, where the provider only archives) one record. */
  delete(id: string, opts?: DomainCallOptions): Promise<UnifiedDeleted> { return this.run("delete", opts, (s, o) => this.u.deleteUnifiedRecord({ ...s, id: idOf(id) }, o)); }
}

// ---------------------------------------------------------------------------------------------------------------
// Scheduling

/** A meeting to book (scheduling/meeting create fields). */
export interface MeetingCreate {
  title: string;
  start_time: DateInput;
  /** Either end_time or duration_minutes. */
  end_time?: DateInput;
  duration_minutes?: number;
  description?: string;
  location?: string;
  /** IANA name, e.g. "Europe/London". */
  timezone?: string;
  attendee_email?: string;
  attendee_name?: string;
  calendar_id?: string;
  event_type_id?: string;
  status?: string;
}

/** A meeting as read back. Fields beyond the create ones depend on the provider. */
export interface Meeting {
  title?: string;
  start_time?: string;
  end_time?: string;
  timezone?: string;
  description?: string;
  location?: string;
  status?: string;
  join_url?: string;
  web_url?: string;
  organizer_email?: string;
  attendees?: Array<{ email?: string; name?: string; responseStatus?: string; organizer?: boolean; self?: boolean; [key: string]: unknown }>;
  calendar_id?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

/** Search window for meetings, and words to match (title, description, attendee email). */
export interface MeetingFilters { start_time: DateInput; end_time: DateInput; query?: string }

export interface FreeSlotsInput {
  start_time: DateInput;
  end_time: DateInput;
  timezone?: string;
  calendar_id?: string;
  event_type_id?: string;
  participants?: string[];
  /** When set, `slots` lists every free slot of this length (minutes) inside the window, back to back. */
  slot_minutes?: number;
}

export interface Interval { start_time: string; end_time: string }

export interface FreeSlots {
  start_time: string;
  end_time: string;
  /** Busy intervals the provider reported inside the window. */
  busy: Interval[];
  /** The window minus the busy intervals, merged. */
  free: Interval[];
  /** Free slots of `slot_minutes`, when it was given. */
  slots?: Interval[];
  provider: string;
  warnings?: string[];
}

/** The window minus the busy intervals: busy ones are merged first, then cut out of [start, end]. */
export function freeIntervals(start: string, end: string, busy: Interval[]): Interval[] {
  const s0 = Date.parse(start), e0 = Date.parse(end);
  const sorted = busy.map((b) => ({ s: Date.parse(b.start_time), e: Date.parse(b.end_time) })).filter((b) => !isNaN(b.s) && !isNaN(b.e) && b.e > b.s).sort((a, b) => a.s - b.s);
  const free: Interval[] = [];
  let cursor = s0;
  for (const b of sorted) {
    if (b.e <= cursor) continue;
    if (b.s > cursor) free.push({ start_time: new Date(cursor).toISOString(), end_time: new Date(Math.min(b.s, e0)).toISOString() });
    cursor = Math.max(cursor, b.e);
    if (cursor >= e0) break;
  }
  if (cursor < e0) free.push({ start_time: new Date(cursor).toISOString(), end_time: new Date(e0).toISOString() });
  return free.filter((f) => Date.parse(f.end_time) > Date.parse(f.start_time));
}

/** Cuts every free interval into back-to-back slots of `minutes` (a positive number); a remainder shorter than a slot is dropped. */
export function slotsOf(free: Interval[], minutes: number): Interval[] {
  if (typeof minutes !== "number" || !Number.isFinite(minutes) || minutes <= 0) throw new TypeError(`slot minutes must be a positive number, got ${String(minutes)}`);
  const len = minutes * 60_000, out: Interval[] = [];
  for (const f of free) {
    for (let t = Date.parse(f.start_time); t + len <= Date.parse(f.end_time); t += len) out.push({ start_time: new Date(t).toISOString(), end_time: new Date(t + len).toISOString() });
  }
  return out;
}

export class Calendar extends Entity<MeetingCreate, Meeting, MeetingFilters> {
  constructor(cust: ProviderResolver) { super(cust, "scheduling", "meeting"); }

  /** Busy and free time in a window (scheduling/availability), from the customer's connected calendar. */
  async freeSlots(input: FreeSlotsInput, opts?: DomainCallOptions): Promise<FreeSlots> {
    const { slot_minutes, ...record } = input;
    if (slot_minutes !== undefined && (typeof slot_minutes !== "number" || !Number.isFinite(slot_minutes) || slot_minutes <= 0)) throw new TypeError(`freeSlots: slot_minutes must be a positive number, got ${String(slot_minutes)}`);
    const availability = new Entity<Omit<FreeSlotsInput, "slot_minutes">, { start_time?: string; end_time?: string; busy?: Interval[] }>(this.cust, "scheduling", "availability");
    const r: any = await availability.create(record as any, opts);
    const data = r?.data ?? {};
    const start = data.start_time ?? wireRecord({ v: input.start_time }).v, end = data.end_time ?? wireRecord({ v: input.end_time }).v;
    const busy: Interval[] = Array.isArray(data.busy) ? data.busy.map((b: any) => ({ start_time: b.start_time ?? b.start, end_time: b.end_time ?? b.end })) : [];
    const free = freeIntervals(start, end, busy);
    return { start_time: start, end_time: end, busy, free, ...(slot_minutes !== undefined ? { slots: slotsOf(free, slot_minutes) } : {}), provider: r?.provider, ...(r?.warnings ? { warnings: r.warnings } : {}) };
  }
  /** Books a meeting. Pass `opts.idempotencyKey` (e.g. your call id) so a retry cannot book it twice. */
  book(meeting: MeetingCreate, opts?: DomainCallOptions): Promise<UnifiedRecord<Meeting>> { return this.create(meeting, opts); }
  /** Moves a meeting: new start, and new end or length. */
  reschedule(id: string, to: { start_time: DateInput; end_time?: DateInput; duration_minutes?: number }, opts?: DomainCallOptions): Promise<UnifiedRecord<Meeting>> { return this.update(id, to, opts); }
  /** Cancels (deletes) a meeting. */
  cancel(id: string, opts?: DomainCallOptions): Promise<UnifiedDeleted> { return this.delete(id, opts); }
}

// ---------------------------------------------------------------------------------------------------------------
// CRM

export interface ContactCreate {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  title?: string;
  /** The company (crm/account) this contact belongs to. */
  account_id?: string;
  owner_id?: string;
  last_activity_at?: DateInput;
  created_at?: DateInput;
}
export interface Contact {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  title?: string;
  account_id?: string;
  owner_id?: string;
  last_activity_at?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}
/** Contact search: the provider matches on the fields given. */
export interface ContactFilters { email?: string; phone?: string; first_name?: string; last_name?: string }

export interface NoteCreate {
  body: string;
  /** When the note was made. Default: now (some CRMs, HubSpot among them, require it). */
  created_at?: DateInput;
  /** The record the note is attached to (a contact id, deal id, ...). */
  parent_id: string;
  /** What `parent_id` is: "contact", "opportunity" (deal), "account" (company), "task". */
  parent_type?: "contact" | "opportunity" | "account" | "task" | (string & {});
  title?: string;
}
export interface Note { body?: string; parent_id?: string; parent_type?: string; title?: string; created_at?: string; [key: string]: unknown }

export interface TaskCreate {
  subject?: string;
  content?: string;
  /** Provider status value; HubSpot: NOT_STARTED, IN_PROGRESS, WAITING, COMPLETED, DEFERRED. */
  status?: string;
  due_date?: DateInput;
  completed_date?: DateInput;
  contact_id?: string;
  account_id?: string;
  opportunity_id?: string;
  owner_id?: string;
}
export interface Task { subject?: string; content?: string; status?: string; due_date?: string; completed_date?: string; contact_id?: string; account_id?: string; opportunity_id?: string; owner_id?: string; [key: string]: unknown }

export interface DealCreate {
  name: string;
  amount?: number;
  /** A stage id from deals.stages(). */
  stage?: string;
  status?: string;
  description?: string;
  close_date?: DateInput;
  account_id?: string;
  owner_id?: string;
  last_activity_at?: DateInput;
  created_at?: DateInput;
}
export interface Deal { name?: string; amount?: number; stage?: string; status?: string; description?: string; close_date?: string; account_id?: string; owner_id?: string; last_activity_at?: string; created_at?: string; [key: string]: unknown }

export interface Stage { name?: string; pipeline_id?: string; [key: string]: unknown }

export class Notes extends Entity<NoteCreate, Note> {
  constructor(cust: ProviderResolver) { super(cust, "crm", "note"); }
  /** Adds a note to a contact or deal; `created_at` defaults to now. */
  add(note: NoteCreate, opts?: DomainCallOptions): Promise<UnifiedRecord<Note>> { return this.create(note, opts); }
  override create(note: NoteCreate, opts?: DomainCallOptions): Promise<UnifiedRecord<Note>> { return super.create({ ...note, created_at: note.created_at ?? new Date() }, opts); }
}

export class Tasks extends Entity<TaskCreate, Task> {
  constructor(cust: ProviderResolver) { super(cust, "crm", "task"); }
  /** Adds a task. Same as create(). */
  add(task: TaskCreate, opts?: DomainCallOptions): Promise<UnifiedRecord<Task>> { return this.create(task, opts); }
}

export class Deals extends Entity<DealCreate, Deal> {
  private readonly stageEntity: Entity<Record<string, never>, Stage>;
  constructor(cust: ProviderResolver) { super(cust, "crm", "opportunity"); this.stageEntity = new Entity(cust, "crm", "stage"); }
  /** Moves a deal to a stage (an id from stages()). */
  moveStage(id: string, stage: string, opts?: DomainCallOptions): Promise<UnifiedRecord<Deal>> { return this.update(id, { stage }, opts); }
  /** The pipeline stages the customer's CRM has; `records[].id` is what moveStage takes. */
  stages(input: PageInput = {}, opts?: DomainCallOptions): Promise<UnifiedPage<Stage>> { return this.stageEntity.list(input, opts); }
}

export class Crm {
  readonly contacts: Entity<ContactCreate, Contact, ContactFilters>;
  readonly notes: Notes;
  readonly tasks: Tasks;
  readonly deals: Deals;
  constructor(cust: ProviderResolver) {
    this.contacts = new Entity(cust, "crm", "contact");
    this.notes = new Notes(cust);
    this.tasks = new Tasks(cust);
    this.deals = new Deals(cust);
  }
}
