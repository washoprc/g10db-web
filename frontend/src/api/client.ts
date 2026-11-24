/**
 * g10db-web REST クライアント。
 * エンドポイントは FastAPI `/api/*` に対応する。
 */

export type ShotRow = {
  shotNo: number | null;
  columns: Record<string, unknown>;
};

export type PanelCell = {
  text: string;
  isShotLink?: boolean;
  shotNo?: number | null;
};

export type PanelGroup = {
  cells: PanelCell[];
};

export type ShotListResponse = {
  mode: "latest" | "byNumber" | "byDate";
  count: number;
  items: ShotRow[];
  groupNames: string[];
  panels: PanelGroup[][];
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

export type WaveformFtpStatus = {
  host: string;
  user: string;
  passwordSet: boolean;
  basePath: string;
  port?: number;
  configured?: boolean;
};

export type WaveformFtpProbe = {
  ok: boolean;
  error?: string | null;
};

export type WaveformRuntimeStatus = {
  useDemo: boolean;
  ftp: WaveformFtpStatus;
  ftpProbe: WaveformFtpProbe;
  dataRoot?: string;
  configRoot?: string;
  ftpBasePath?: string;
};

export type WaveformDiagnose = {
  shotNo: number;
  kind: WaveformKind;
  useDemo: boolean;
  ftp: WaveformFtpStatus;
  ftpProbe: WaveformFtpProbe;
  shotDirExists?: boolean | null;
  ports: Record<string, string[]>;
  fetchResults: Record<string, Record<string, unknown>>;
  parseResults: Record<string, Record<string, unknown>>;
  seriesCount: number;
  wouldUseDemo: boolean;
  startMs?: number;
  endMs?: number;
  fallbackNote?: string | null;
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

/**
 * 波形を取得する。
 * start/end 省略時の表示窓は 50–250 ms。ロングパルスは 50–450 ms。
 */
export function fetchWaveform(
  shotNo: number,
  kind: WaveformKind,
  startMs?: number,
  endMs?: number,
): Promise<WaveformResponse> {
  const params = new URLSearchParams();
  if (startMs != null) params.set("startMs", String(startMs));
  if (endMs != null) params.set("endMs", String(endMs));
  const query = params.toString();
  return fetchJson(
    `/api/waveforms/${shotNo}/${kind}${query ? `?${query}` : ""}`,
  );
}

/** 設定サマリを取得する。 */
export function fetchConfigMeta(): Promise<Record<string, unknown>> {
  return fetchJson("/api/waveforms/meta/config");
}

/** 波形ランタイム状態（USE_DEMO / FTP）を取得する。 */
export function fetchWaveformStatus(): Promise<WaveformRuntimeStatus> {
  return fetchJson("/api/waveforms/meta/status");
}

/** ショット波形の取得・パース診断を取得する。 */
export function fetchWaveformDiagnose(
  shotNo: number,
  kind: WaveformKind,
): Promise<WaveformDiagnose> {
  return fetchJson(
    `/api/waveforms/${shotNo}/diagnose?kind=${encodeURIComponent(kind)}`,
  );
}
