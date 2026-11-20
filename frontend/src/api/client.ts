/**
 * g10db-web REST クライアント。
 * エンドポイントは FastAPI `/api/*` に対応する。
 */

export type ShotRow = {
  shotNo: number | null;
  columns: Record<string, unknown>;
};

export type ShotListResponse = {
  mode: "latest" | "byNumber" | "byDate";
  count: number;
  items: ShotRow[];
  demoMode: boolean;
  matchedDate?: string | null;
  closestFallback?: boolean;
};

export type WaveformKind = "Ha" | "DM" | "NL" | "VCC";

export type WaveformPoint = {
  t: number;
  v: number;
};

export type WaveformSeries = {
  name: string;
  unit: string;
  points: WaveformPoint[];
};

export type WaveformResponse = {
  shotNo: number;
  kind: WaveformKind;
  startMs: number;
  endMs: number;
  series: WaveformSeries[];
  demoMode: boolean;
  note?: string | null;
};

/**
 * JSON API を呼び出す共通ヘルパー。
 * @param path `/api/...` で始まるパス
 */
async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

/** 最新ショットを取得する。 */
export function fetchLatestShots(limit: number): Promise<ShotListResponse> {
  return fetchJson(`/api/shots/latest?limit=${limit}`);
}

/** ショット番号以降を取得する。 */
export function fetchShotsByNumber(
  start: number,
  limit: number,
): Promise<ShotListResponse> {
  return fetchJson(`/api/shots/by-number?start=${start}&limit=${limit}`);
}

/** 日付でショットを取得する（一致無し時は最寄り日付）。 */
export function fetchShotsByDate(
  date: string,
  limit: number,
): Promise<ShotListResponse> {
  return fetchJson(`/api/shots/by-date?date=${encodeURIComponent(date)}&limit=${limit}`);
}

/** 波形を取得する。 */
export function fetchWaveform(
  shotNo: number,
  kind: WaveformKind,
  startMs = 0,
  endMs = 200,
): Promise<WaveformResponse> {
  return fetchJson(
    `/api/waveforms/${shotNo}/${kind}?startMs=${startMs}&endMs=${endMs}`,
  );
}

/** 設定サマリを取得する。 */
export function fetchConfigMeta(): Promise<Record<string, unknown>> {
  return fetchJson("/api/waveforms/meta/config");
}
