const API_BASE = `${window.location.origin}/api`;
const PREF_KEY = "trend-radar-source-prefs-v1";
const MOCK_STORE_KEY = "trend-radar-mock-store-v1";

const DEFAULT_SOURCES = [
  { id: "kr36", name: "36氪", enabled: true, mode: "both", weight: 4, is_mock: false },
  { id: "huxiu", name: "虎嗅", enabled: true, mode: "both", weight: 3, is_mock: false },
  { id: "sspai", name: "少数派", enabled: true, mode: "both", weight: 3, is_mock: false },
  { id: "zhihu_hot", name: "知乎热榜", enabled: true, mode: "hot", weight: 4, is_mock: false },
  { id: "weibo_hot", name: "微博热榜", enabled: true, mode: "hot", weight: 5, is_mock: false },
  { id: "github_trending", name: "GitHub Trending", enabled: true, mode: "both", weight: 4, is_mock: false },
  { id: "x_trending", name: "X Trending", enabled: true, mode: "hot", weight: 4, is_mock: false },
  { id: "jike_mock", name: "即刻(MOCK)", enabled: true, mode: "new", weight: 3, is_mock: true },
  { id: "bilibili_mock", name: "B站科技(MOCK)", enabled: true, mode: "new", weight: 3, is_mock: true },
  { id: "mock_burst", name: "种子爆发信号(MOCK)", enabled: true, mode: "both", weight: 5, is_mock: true }
];

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
  } catch {
    return {};
  }
}

function savePrefs(data) {
  localStorage.setItem(PREF_KEY, JSON.stringify(data));
}

function fmtPct(v) { return `${(v * 100).toFixed(1)}%`; }
function fmtScore(v) { return Number(v || 0).toFixed(1); }
function fmtGrowth(v) { return `${(Number(v || 0) * 100).toFixed(1)}%`; }

function sanitizeText(value, maxLen = 0) {
  const raw = String(value ?? "");
  const noTags = raw.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  const decoded = noTags
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
  if (maxLen > 0 && decoded.length > maxLen) return `${decoded.slice(0, maxLen)}...`;
  return decoded;
}

function normalizeExternalUrl(url, title = "") {
  const raw = String(url || "").trim();
  if (!raw || /:\/\/mock[.\-]/i.test(raw)) {
    const q = encodeURIComponent(sanitizeText(title) || "热点资讯");
    return `https://www.baidu.com/s?wd=${q}`;
  }
  return raw;
}

window.sanitizeText = sanitizeText;
window.normalizeExternalUrl = normalizeExternalUrl;

function relTime(iso) {
  const d = new Date(iso).getTime();
  const now = Date.now();
  const m = Math.floor((now - d) / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

function loadMockStore() {
  try {
    const parsed = JSON.parse(localStorage.getItem(MOCK_STORE_KEY) || "{}");
    if (parsed && parsed.sources && parsed.home) return parsed;
  } catch {}

  const now = new Date();
  const ts = (mins) => new Date(now.getTime() - mins * 60000).toISOString();
  const burstTitles = [
    "开源AI助手集体爆发",
    "国产AI视频模型发布",
    "设计系统自动化成为团队标配"
  ];

  const topEvents = Array.from({ length: 24 }, (_, i) => ({
    id: `evt-${i + 1}`,
    title: i < 3 ? burstTitles[i] : `趋势事件 ${i + 1}`,
    summary: i < 3 ? `多平台同步出现“${burstTitles[i]}”相关信号，讨论密度显著提升。` : `这是趋势事件 ${i + 1} 的聚类摘要，来自多个来源信号。`,
    category: ["AI", "科技", "创业", "设计"][i % 4],
    heat_score: Number((98 - i * 2.3).toFixed(1)),
    growth_rate: i < 3 ? 0.62 - i * 0.08 : 0.12 + (i % 5) * 0.03,
    source_count: i < 3 ? 4 + i : 2 + (i % 3),
    signals_count: 18 - (i % 8),
    top_keywords: ["趋势", "热点", "信号", "聚类"],
    is_breaking: i < 3,
    last_updated_time: ts(3 + i),
  }));

  const mkItems = (sid, mode) => Array.from({ length: mode === "both" ? 20 : 10 }, (_, i) => ({
    id: `${sid}-${mode}-${i + 1}`,
    title: `${sid} ${mode === "both" ? (i < 10 ? "hot" : "new") : mode} 内容 ${i + 1}`,
    summary: "平台条目摘要，用于页面可视化演示。",
    url: `https://www.baidu.com/s?wd=${encodeURIComponent(`${sid} 热点`)}`,
    publish_time: ts(i * 4 + 1),
    mode: mode === "both" ? (i < 10 ? "hot" : "new") : mode,
  }));

  const sections = DEFAULT_SOURCES.filter((s) => s.enabled).map((s) => ({
    source_id: s.id,
    source_name: s.name,
    mode: s.mode,
    items: mkItems(s.id, s.mode),
  }));

  const store = {
    sources: DEFAULT_SOURCES.map((s) => ({ ...s, last_fetch: now.toISOString() })),
    home: {
      breaking: topEvents.slice(0, 3),
      top_events: topEvents.slice(0, 10),
      sections,
      all_events: topEvents,
    },
  };

  localStorage.setItem(MOCK_STORE_KEY, JSON.stringify(store));
  return store;
}

function persistMockStore(store) {
  localStorage.setItem(MOCK_STORE_KEY, JSON.stringify(store));
}

function applyPrefsToMockSources(sources) {
  const prefs = loadPrefs();
  return sources.map((s) => {
    const p = prefs[s.id] || {};
    return {
      ...s,
      enabled: p.enabled ?? s.enabled,
      mode: p.mode ?? s.mode,
      weight: p.weight ?? s.weight,
    };
  });
}

function rebuildMockHome(store) {
  const ts = (mins) => new Date(Date.now() - mins * 60000).toISOString();
  const mkItems = (sid, mode) => Array.from({ length: mode === "both" ? 20 : 10 }, (_, i) => ({
    id: `${sid}-${mode}-${i + 1}`,
    title: `${sid} ${mode === "both" ? (i < 10 ? "hot" : "new") : mode} 内容 ${i + 1}`,
    summary: "平台条目摘要，用于页面可视化演示。",
    url: `https://www.baidu.com/s?wd=${encodeURIComponent(`${sid} 热点`)}`,
    publish_time: ts(i * 3 + 1),
    mode: mode === "both" ? (i < 10 ? "hot" : "new") : mode,
  }));

  const enabledSources = store.sources.filter((s) => s.enabled);
  const sections = enabledSources.map((s) => ({
    source_id: s.id,
    source_name: s.name,
    mode: s.mode,
    items: mkItems(s.id, s.mode),
  }));

  const weighted = store.home.all_events.map((e) => {
    const activeCount = enabledSources.length || 1;
    const boost = activeCount / 10;
    return { ...e, heat_score: Number((e.heat_score * (0.8 + boost)).toFixed(1)) };
  }).sort((a, b) => b.heat_score - a.heat_score);

  store.home.top_events = weighted.slice(0, 10);
  store.home.breaking = weighted.filter((x) => x.is_breaking).slice(0, 3);
  store.home.sections = sections;
  return store;
}

async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  } catch {
    const store = loadMockStore();
    store.sources = applyPrefsToMockSources(store.sources);
    rebuildMockHome(store);
    persistMockStore(store);

    if (path === "/home") return store.home;
    if (path === "/sources") return { items: store.sources };
    if (path === "/sources/contribution") {
      return {
        items: store.sources.map((s) => ({
          source_id: s.id,
          source_name: s.name,
          enabled: s.enabled,
          mode: s.mode,
          weight: s.weight,
          today_signals: s.enabled ? 18 : 0,
          covered_events: s.enabled ? 6 : 0,
          last_fetch: s.last_fetch,
        }))
      };
    }
    const platformMatch = path.match(/^\/platform\/([^/]+)$/);
    if (platformMatch) {
      const sourceId = decodeURIComponent(platformMatch[1]);
      const source = (store.sources || []).find((x) => x.id === sourceId);
      if (!source) throw new Error("source not found");
      const section = (store.home.sections || []).find((x) => x.source_id === sourceId);
      return {
        source_id: source.id,
        source_name: source.name,
        enabled: source.enabled,
        mode: source.mode,
        last_fetch: source.last_fetch,
        items: section ? section.items : [],
      };
    }
    const eventMatch = path.match(/^\/events\/([^/]+)$/);
    if (eventMatch) {
      const id = decodeURIComponent(eventMatch[1]);
      const event = (store.home.all_events || []).find((x) => x.id === id) || (store.home.top_events || [])[0];
      if (!event) return { event: null, signals_by_source: {}, related_events: [] };
      const signals = {};
      for (const src of store.sources.filter((s) => s.enabled).slice(0, 5)) {
        signals[src.id] = Array.from({ length: 3 }, (_, i) => ({
          id: `${id}-${src.id}-${i + 1}`,
          source_id: src.id,
          source_name: src.name,
          title: `${event.title} - ${src.name} 信号 ${i + 1}`,
          url: `https://www.baidu.com/s?wd=${encodeURIComponent(event.title)}`,
          publish_time: new Date(Date.now() - (i + 1) * 600000).toISOString()
        }));
      }
      const related = (store.home.all_events || []).filter((x) => x.id !== event.id).slice(0, 5);
      return { event, signals_by_source: signals, related_events: related };
    }
    return {};
  }
}

async function apiPost(path, body = {}) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  } catch {
    const store = loadMockStore();
    store.sources = applyPrefsToMockSources(store.sources);

    if (path === "/refresh") {
      const now = new Date().toISOString();
      store.sources = store.sources.map((s) => ({ ...s, last_fetch: now }));
      rebuildMockHome(store);
      persistMockStore(store);
      return { message: "mock refresh completed", events: store.home.top_events.length, breaking: store.home.breaking.length };
    }

    const toggleMatch = path.match(/^\/sources\/(.+)\/toggle$/);
    if (toggleMatch) {
      const id = toggleMatch[1];
      store.sources = store.sources.map((s) => s.id === id ? { ...s, enabled: !!body.enabled } : s);
      rebuildMockHome(store);
      persistMockStore(store);
      return { id, enabled: !!body.enabled };
    }

    const modeMatch = path.match(/^\/sources\/(.+)\/mode$/);
    if (modeMatch) {
      const id = modeMatch[1];
      store.sources = store.sources.map((s) => s.id === id ? { ...s, mode: body.mode || "both" } : s);
      rebuildMockHome(store);
      persistMockStore(store);
      return { id, mode: body.mode || "both" };
    }

    return { ok: true };
  }
}
