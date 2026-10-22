/** Thrown for every non-2xx answer. `status`, `code` and `message` are what the API returned. */
export class FastnApiError extends Error {
  readonly name = "FastnApiError";
  constructor(
    message: string,
    /** HTTP status (0 when the request never reached the API). */
    readonly status: number,
    /** API error code, e.g. NOT_FOUND, VALIDATION_ERROR, RATE_LIMITED, CONFLICT. */
    readonly code: string | undefined,
    /** Extra details the API sent with the error, when any. */
    readonly details: unknown,
    readonly method: string,
    readonly path: string,
    /** x-request-id of the failed call; quote it when reporting a problem to fastn. */
    readonly requestId: string | undefined,
    /** The raw response body. */
    readonly body: unknown,
  ) {
    super(message);
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
