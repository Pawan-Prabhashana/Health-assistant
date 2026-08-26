// Minimal typed fetch wrapper. Every request is rooted at `/api`, which nginx
// (in the container topology) and the Vite dev server both reverse-proxy to the
// FastAPI backend, stripping the prefix so the API receives `/health/ready`.

const API_BASE_PATH = '/api';

/** Error raised for a non-2xx response, carrying the HTTP status code. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Perform a typed GET request against the API.
 *
 * @param path Path relative to the API root, beginning with `/`.
 * @returns The parsed JSON body typed as `T`.
 * @throws {ApiError} When the response status is not in the 2xx range.
 */
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_PATH}${path}`, {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  });

  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}
