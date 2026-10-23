export interface FastnApiErrorInfo {
  /** HTTP status (0 when the request never reached the API). */
  status: number;
  /** API error code, e.g. NOT_FOUND, VALIDATION_ERROR, RATE_LIMITED, CONFLICT. */
  code?: string;
  /** Extra details the API sent with the error, when any. */
  details?: unknown;
  method: string;
  path: string;
  /** x-request-id of the failed call; quote it when reporting a problem to fastn. */
  requestId?: string;
  /** The raw response body. */
  body?: unknown;
}

/** Thrown for every non-2xx answer. `status`, `code` and `message` are what the API returned. */
export class FastnApiError extends Error {
  readonly name = "FastnApiError";
  readonly status: number;
  readonly code: string | undefined;
  readonly details: unknown;
  readonly method: string;
  readonly path: string;
  readonly requestId: string | undefined;
  readonly body: unknown;
  constructor(message: string, info: FastnApiErrorInfo) {
    super(message);
    this.status = info.status; this.code = info.code; this.details = info.details; this.method = info.method; this.path = info.path; this.requestId = info.requestId; this.body = info.body;
  }
  get isNotFound() { return this.status === 404; }
  get isConflict() { return this.status === 409; }
  get isRateLimited() { return this.status === 429; }
  get isAuth() { return this.status === 401 || this.status === 403; }
  get isValidation() { return this.status === 400 || this.status === 422; }
}

/** Thrown when the request could not be sent or timed out. */
export class FastnNetworkError extends Error {
  readonly name = "FastnNetworkError";
  constructor(message: string, readonly method: string, readonly path: string, readonly cause?: unknown) {
    super(message);
  }
}
