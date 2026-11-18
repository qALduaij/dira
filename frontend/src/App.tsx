import { useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Bell,
  Check,
  ChevronRight,
  Clock,
  Compass,
  Database,
  FileText,
  Globe2,
  Layers,
  LayoutGrid,
  Maximize2,
  Network,
  Pause,
  Play,
  Plus,
  Radio,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { api, download } from "./api";
import { useDira } from "./useDira";
import { Player, Spark } from "./Visuals";
import type { Event, Channel, Brief, Snapshot, Rule } from "./types";

type Page = "overview" | "signals" | "search" | "briefs" | "system";
const time = (value: string) =>
  new Date(value).toLocaleTimeString("en-GB", {
    timeZone: "Asia/Kuwait",
    hour12: false,
  });
function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
function Badge({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [ar, setAr] = useState(false);
  const [revision, setRevision] = useState(0);
  const { state, connection, error, jobs } = useDira(revision);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Event | null>(null);
  const [expanded, setExpanded] = useState<Channel | null>(null);
  const [notice, setNotice] = useState("");
  const [settings, setSettings] = useState(false);
  const [token, setToken] = useState(
    sessionStorage.getItem("dira-token") || "",
  );
  const [clock, setClock] = useState(new Date());
  const [source, setSource] = useState("all");
  const [language, setLanguage] = useState("both");
  const [searchResult, setSearchResult] = useState<{
    results: {
      event: Event;
      score: number;
      cosine_similarity?: number;
      lexical_match?: boolean;
    }[];
    elapsed_ms: number;
    encoder: string;
    warm_available: boolean;
  } | null>(null);
  const [modality, setModality] = useState("auto");
  const [searchChannel, setSearchChannel] = useState("");
  const [searching, setSearching] = useState(false);
  const [windowHours, setWindowHours] = useState("24");
  const [jobId, setJobId] = useState("");
  const tr = (en: string, arabic: string) => (ar ? arabic : en);
  useEffect(() => {
    document.documentElement.lang = ar ? "ar" : "en";
    document.documentElement.dir = ar ? "rtl" : "ltr";
  }, [ar]);
  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 7000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (jobs[jobId]?.status === "done") {
      setNotice(tr("Brief is ready", "الملخص جاهز"));
      setJobId("");
    } else if (jobs[jobId]?.status === "failed") {
      setNotice("Brief failed: " + jobs[jobId].error);
      setJobId("");
    }
  }, [jobs, jobId]);
  async function action(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch (e) {
      setNotice(String(e));
    }
  }
  async function search(e?: FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;
    setPage("search");
    setSearching(true);
    try {
      setSearchResult(
        await api("/search", {
          query,
          modality,
          channel_id: searchChannel || null,
          since: windowHours
            ? new Date(Date.now() - Number(windowHours) * 3600000).toISOString()
            : null,
        }),
      );
    } catch (e) {
      setNotice(String(e));
    } finally {
      setSearching(false);
    }
  }
  async function evidence(id: string | null) {
    if (!id) return; // health alerts cite no observation
    await action(async () => setSelected(await api<Event>("/evidence/" + id)));
  }
  async function generate(kind = "morning") {
    await action(async () => {
      const job = await api<{ id: string }>("/briefs", { kind });
      setJobId(job.id);
      setPage("briefs");
    });
  }
  const m = state?.metrics;
  const channels = state?.channels || [];
  const events = state?.events || [];
  const alerts = (state?.alerts || []).filter((x) => !x.acknowledged);
  const nav: [Page, typeof Activity, string, string][] = [
    ["overview", LayoutGrid, "Command center", "مركز القيادة"],
    ["signals", Activity, "Signals & alerts", "الإشارات والتنبيهات"],
    ["search", Search, "Intelligence archive", "أرشيف الرصد"],
    ["briefs", FileText, "Executive briefs", "الملخصات التنفيذية"],
    ["system", Settings, "System health", "حالة النظام"],
  ];
  const heading = nav.find((n) => n[0] === page)!;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <div className="brand-mark">
            <Compass size={32} />
          </div>
          <div>
            <strong>
              ديرة <span>DIRA</span>
            </strong>
            <small>THE INTELLIGENCE COMPASS</small>
          </div>
        </a>
        <div className="workspace-label">
          {tr("SOVEREIGN WORKSPACE", "مساحة العمل السيادية")}
        </div>
        <nav>
          {nav.map(([id, Icon, en, arabic]) => (
            <button
              key={id}
              aria-label={tr(en, arabic)}
              className={page === id ? "nav-item active" : "nav-item"}
              onClick={() => setPage(id)}
            >
              <Icon size={18} />
              <span>{tr(en, arabic)}</span>
              {id === "signals" && alerts.length > 0 && <b>{alerts.length}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sovereign">
            <ShieldCheck size={19} />
            <div>
              <strong>
                {tr("Your intelligence. Your control.", "بياناتك تحت سيطرتك.")}
              </strong>
              <p>
                {m?.llm === "cloud"
                  ? tr(
                      "Local perception · Cloud briefs",
                      "رصد محلي · ملخصات سحابية",
                    )
                  : tr("Local processing", "معالجة محلية")}
              </p>
            </div>
          </div>
          <div className="operator">
            <div className="avatar">QA</div>
            <div>
              <strong>{tr("Command operator", "مشغّل مركز القيادة")}</strong>
              <small>{tr("Local workspace", "مساحة عمل محلية")}</small>
            </div>
            <button
              className="icon-button"
              title="Connection settings"
              onClick={() => setSettings(true)}
            >
              <Settings size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            DIRA <ChevronRight size={13} />
            <span>{tr(heading[2], heading[3])}</span>
          </div>
          <form className="global-search" onSubmit={search}>
            <Search size={16} />
            <input
              aria-label="Search intelligence"
              placeholder={tr(
                "Search across every signal…",
                "ابحث في جميع الإشارات…",
              )}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <kbd>↵</kbd>
          </form>
          <div className="top-actions">
            <button className="language-button" onClick={() => setAr(!ar)}>
              <Globe2 size={15} />
              {ar ? "English" : "العربية"}
            </button>
            <span
              className={
                "connection " + (connection === "connected" ? "good" : "bad")
              }
            >
              <i />
              {tr(
                connection === "connected" ? "Connected" : "Reconnecting",
                connection === "connected" ? "متصل" : "إعادة الاتصال",
              )}
            </span>
            <button
              className="icon-button notifications"
              aria-label="Open alerts"
              onClick={() => setPage("signals")}
            >
              <Bell size={19} />
              {alerts.length > 0 && <i />}
            </button>
          </div>
        </header>
        <main>
          <section className="page-heading">
            <div>
              <div className="eyebrow">
                <span />
                {tr(
                  "BROADCAST INTELLIGENCE OPERATIONS",
                  "عمليات الرصد الإعلامي",
                )}
              </div>
              <h1>
                {tr(heading[2], heading[3])}
                <span className="title-dot">.</span>
              </h1>
              <p>
                {tr(
                  "Clarity across channels. Context behind every signal.",
                  "وضوح عبر القنوات. وسياق وراء كل إشارة.",
                )}
              </p>
            </div>
            <div className="heading-actions">
              <div className="local-time">
                <strong>
                  {clock.toLocaleTimeString("en-GB", {
                    timeZone: "Asia/Kuwait",
                    hour12: false,
                  })}
                </strong>
                <small>KUWAIT · UTC+03:00</small>
              </div>
              <button
                className="primary"
                onClick={() => generate()}
                disabled={!!jobId}
              >
                <FileText size={16} />
                {jobId
                  ? tr("Preparing…", "جارٍ الإعداد…")
                  : tr("Generate brief", "إنشاء ملخص")}
              </button>
            </div>
          </section>
          {(error || connection !== "connected") && (
            <div className="error-banner">
              {error ||
                tr(
                  "Reconnecting to the local backend. Displayed observations may be stale.",
                  "جارٍ الاتصال بالخادم المحلي. قد تكون البيانات المعروضة قديمة.",
                )}
              <button onClick={() => setSettings(true)}>
                {tr("Connection settings", "إعدادات الاتصال")}
              </button>
            </div>
          )}
          {m?.mode === "simulation" && (
            <div className="simulation-bar">
              <div>
                <Radio size={15} />
                <strong>{tr("SIMULATION ENVIRONMENT", "بيئة محاكاة")}</strong>
                <span>
                  {tr(
                    "Fictional broadcasts · Real intelligence pipeline",
                    "بث تجريبي · مسار معالجة فعلي",
                  )}
                </span>
              </div>
              <button
                aria-pressed={!m.paused}
                onClick={() =>
                  action(() => api("/simulation", { paused: !m.paused }))
                }
              >
                {m.paused ? <Play size={13} /> : <Pause size={13} />}{" "}
                {m.paused
                  ? tr("Resume simulation", "استئناف المحاكاة")
                  : tr("Pause simulation", "إيقاف المحاكاة مؤقتًا")}
              </button>
            </div>
          )}
          {!state ? (
            <Empty>{tr("Connecting to Dira…", "جارٍ الاتصال بديرة…")}</Empty>
          ) : (
            <>
              {m?.llm === "cloud" && (
                <div className="error-banner" role="status">
                  {tr(
                    "Cloud briefs enabled: evidence text leaves this Mac when a brief is generated.",
                    "الملخصات السحابية مفعلة: تغادر نصوص الأدلة هذا الجهاز عند توليد ملخص.",
                  )}{" "}
                  {m.cloud_auto_briefs
                    ? tr("Automatic scheduling is on.", "الجدولة الآلية مفعلة.")
                    : tr("Manual generation only.", "التوليد اليدوي فقط.")}
                </div>
              )}
              {m?.disk_guard_active && (
                <div className="error-banner" role="alert">
                  {tr(
                    "Ingestion paused: disk reserve reached.",
                    "توقف إدخال الأدلة مؤقتًا: مساحة القرص وصلت إلى الحد الاحتياطي.",
                  )}
                </div>
              )}
              {page === "overview" && (
                <>
                  <section className="stat-grid">
                    <Stat
                      label={tr("MONITORED CHANNELS", "القنوات المرصودة")}
                      value={String(channels.length).padStart(2, "0")}
                      icon={<Radio />}
                      sub={tr(
                        m!.mode === "simulation"
                          ? "Simulated broadcast sources"
                          : "Configured broadcast sources",
                        m!.mode === "simulation"
                          ? "مصادر بث تجريبية"
                          : "مصادر البث المعدّة",
                      )}
                    />
                    <Stat
                      label={tr("OBSERVATIONS INDEXED", "المشاهدات المفهرسة")}
                      value={m!.evidence.toLocaleString()}
                      icon={<Layers />}
                      sub={tr(
                        "Time-aligned across modalities",
                        "متزامنة عبر أنماط البيانات",
                      )}
                    />
                    <Stat
                      label={tr("ACTIVE ALERTS", "التنبيهات النشطة")}
                      value={String(m?.active_alerts ?? alerts.length).padStart(
                        2,
                        "0",
                      )}
                      icon={<Target />}
                      sub={tr(
                        `${alerts.filter((a) => a.severity === "critical").length} critical in latest 100`,
                        `${alerts.filter((a) => a.severity === "critical").length} حرجة ضمن أحدث ١٠٠`,
                      )}
                      accent
                    />
                    {m!.mode === "live" ? (
                      <Stat
                        label={tr(
                          "SPEECH LAG · WORST CHANNEL",
                          "تأخر التفريغ · الأسوأ",
                        )}
                        value={
                          m!.asr_lag_max_seconds == null
                            ? "—"
                            : m!.asr_lag_max_seconds.toFixed(0)
                        }
                        suffix={
                          m!.asr_lag_max_seconds == null ? undefined : "s"
                        }
                        icon={<Zap />}
                        accent={
                          m!.asr_lag_max_seconds != null &&
                          m!.asr_lag_max_seconds > LAG_WARN_SECONDS
                        }
                        sub={tr(
                          `Ceiling ${m!.asr_max_lag == null ? "—" : m!.asr_max_lag ? m!.asr_max_lag + " s" : "off"} · ingest p95 ${m!.latency_p95_ms.toFixed(0)} ms`,
                          `الحد ${m!.asr_max_lag == null ? "—" : m!.asr_max_lag ? m!.asr_max_lag + " ث" : "معطّل"} · معالجة p95 ${m!.latency_p95_ms.toFixed(0)} مللي ث`,
                        )}
                      />
                    ) : (
                      <Stat
                        label={tr(
                          "PIPELINE LATENCY · P95",
                          "زمن المعالجة · P95",
                        )}
                        value={m!.latency_p95_ms.toFixed(1)}
                        suffix="ms"
                        icon={<Zap />}
                        sub={tr(
                          "Measured ingest processing",
                          "قياس معالجة المشاهدات",
                        )}
                      />
                    )}
                  </section>
                  <div className="overview-grid">
                    <div className="primary-column">
                      <section className="panel multiview">
                        <PanelTitle
                          icon={<LayoutGrid size={16} />}
                          title={tr("Broadcast multiview", "شاشات البث")}
                          right={
                            <span className="muted small">
                              {channels.length} {tr("sources", "مصادر")}{" "}
                              <span className="tiny-dot" />
                            </span>
                          }
                        />
                        <div className="video-grid">
                          {channels.map((channel, i) => {
                            const event = events.find(
                              (e) => e.channel_id === channel.id,
                            );
                            return (
                              <button
                                key={channel.id}
                                className="monitor"
                                onClick={() => setExpanded(channel)}
                                aria-label={"Expand " + channel.name}
                              >
                                <Player channel={channel} index={i % 4} />
                                <div className="monitor-top">
                                  <span
                                    className="channel-bug"
                                    style={{ borderColor: channel.color }}
                                  >
                                    {channel.short}
                                  </span>
                                  <span className="monitor-badges">
                                    {m!.mode === "live" && (
                                      <LagBadge channel={channel} ar={ar} />
                                    )}
                                    <span className="feed-status">
                                      <i />
                                      {m!.mode === "simulation"
                                        ? "SIM"
                                        : channel.status.toUpperCase()}
                                    </span>
                                  </span>
                                </div>
                                <span className="expand-icon">
                                  <Maximize2 size={14} />
                                </span>
                                <div className="monitor-bottom">
                                  <span className="lower-third" dir="rtl">
                                    {event?.ocr || "بانتظار الإشارة"}
                                  </span>
                                  <div>
                                    <strong>
                                      {ar ? channel.name_ar : channel.name}
                                    </strong>
                                    <span>
                                      {event ? time(event.end) : "—"}{" "}
                                      <AudioLines size={14} />
                                    </span>
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                        <div className="panel-foot">
                          <span>
                            <i className="tiny-dot" />{" "}
                            {tr(
                              "Synchronized observation timeline",
                              "خط زمني متزامن للمشاهدات",
                            )}
                          </span>
                          <span>
                            {tr(
                              "Click a source to focus",
                              "اضغط على مصدر للعرض",
                            )}
                          </span>
                        </div>
                      </section>
                      <section className="panel transcript-panel">
                        <PanelTitle
                          icon={<AudioLines size={17} />}
                          title={tr("Live transcript", "النص المباشر")}
                          right={
                            <div className="segmented">
                              <button
                                className={language === "both" ? "chosen" : ""}
                                onClick={() => setLanguage("both")}
                              >
                                AR / EN
                              </button>
                              <button
                                className={language === "ar" ? "chosen" : ""}
                                onClick={() => setLanguage("ar")}
                              >
                                AR
                              </button>
                              <button
                                className={language === "en" ? "chosen" : ""}
                                onClick={() => setLanguage("en")}
                              >
                                EN
                              </button>
                            </div>
                          }
                        />
                        <div className="source-tabs">
                          <button
                            className={source === "all" ? "selected" : ""}
                            onClick={() => setSource("all")}
                          >
                            {tr("All sources", "جميع المصادر")}
                          </button>
                          {channels.map((c) => (
                            <button
                              key={c.id}
                              className={source === c.id ? "selected" : ""}
                              onClick={() => setSource(c.id)}
                            >
                              {c.short}
                            </button>
                          ))}
                        </div>
                        <div className="transcript-list">
                          {events
                            .filter(
                              (e) =>
                                source === "all" || e.channel_id === source,
                            )
                            .slice(0, 30)
                            .map((e) => (
                              <button
                                className="transcript-row"
                                key={e.id}
                                onClick={() => setSelected(e)}
                              >
                                <div className="transcript-meta">
                                  <time>{time(e.start)}</time>
                                  <span>
                                    {channels.find((c) => c.id === e.channel_id)
                                      ?.short || e.channel_id}
                                  </span>
                                </div>
                                <div>
                                  {language !== "en" && (
                                    <p dir="auto" className="arabic-line">
                                      {e.transcript || e.ocr || e.visual}
                                    </p>
                                  )}
                                  {language !== "ar" && e.translation && (
                                    <p className="translation">
                                      {e.translation}
                                    </p>
                                  )}
                                  <small>
                                    <span className="speaker-dot" />
                                    {e.speaker || e.source} <span>·</span>{" "}
                                    {e.confidence == null ||
                                    (!e.simulated &&
                                      [
                                        "whisperlivekit",
                                        "local-perception",
                                      ].includes(e.source))
                                      ? tr("Uncalibrated", "الدقة غير معايرة")
                                      : `${Math.round(e.confidence * 100)}% ${tr("confidence", "ثقة")}`}
                                  </small>
                                </div>
                                <ChevronRight size={14} />
                              </button>
                            ))}
                        </div>
                      </section>
                    </div>
                    <div className="secondary-column">
                      <section className="panel radar-panel">
                        <PanelTitle
                          icon={<Activity size={16} />}
                          title={tr("Signal radar", "رادار الإشارات")}
                          right={
                            <Badge tone="gold">
                              {tr("ZERO LLM", "دون LLM")}
                            </Badge>
                          }
                        />
                        <div className="radar-metric">
                          <strong>
                            {alerts.filter((a) => a.kind === "spike").length}
                            <small>
                              {tr("volume spikes", "قفزات في حجم التغطية")}
                            </small>
                          </strong>
                          <span>{tr("Rolling baseline", "خط أساس متحرك")}</span>
                        </div>
                        <Spark
                          values={m!.history.map((p, i, a) =>
                            i ? p.events - a[i - 1].events : 0,
                          )}
                          height={90}
                        />
                        <div className="chart-axis">
                          <span>
                            {tr("Recent observations", "المشاهدات الأخيرة")}
                          </span>
                          <span>{tr("NOW", "الآن")}</span>
                        </div>
                        <div className="topic-bars">
                          {topicCounts(events)
                            .slice(0, 4)
                            .map(([name, count], i) => (
                              <div key={name}>
                                <div>
                                  <span>{name}</span>
                                  <b>{count}</b>
                                </div>
                                <div className="bar-track">
                                  <i
                                    style={{
                                      width: `${(count / Math.max(...topicCounts(events).map((x) => x[1]), 1)) * 100}%`,
                                      background: [
                                        "var(--gold)",
                                        "var(--success)",
                                        "#A5B4FC",
                                        "#F69C8C",
                                      ][i],
                                    }}
                                  />
                                </div>
                              </div>
                            ))}
                        </div>
                      </section>
                      <section className="panel alerts-panel">
                        <PanelTitle
                          icon={<Bell size={16} />}
                          title={tr("Priority signals", "إشارات الأولوية")}
                          right={
                            <span className="count-pill">{alerts.length}</span>
                          }
                        />
                        <div className="alert-list">
                          {alerts.slice(0, 4).map((a) => (
                            <button
                              key={a.id}
                              className="alert-item"
                              onClick={() => evidence(a.tdo_id)}
                            >
                              <div className="alert-top">
                                <Badge tone={a.severity}>
                                  {a.severity.toUpperCase()}
                                </Badge>
                                <time>{time(a.timestamp)}</time>
                              </div>
                              <strong>{a.rule_name}</strong>
                              <p dir="auto">{a.detail.slice(0, 110)}</p>
                              <small>
                                {a.channel_id.toUpperCase()} <span>·</span>{" "}
                                {a.kind}
                              </small>
                            </button>
                          ))}
                          {!alerts.length && (
                            <Empty>
                              {tr(
                                "No unreviewed signals",
                                "لا توجد إشارات بانتظار المراجعة",
                              )}
                            </Empty>
                          )}
                        </div>
                        <button
                          className="text-action"
                          onClick={() => setPage("signals")}
                        >
                          {tr("View all signals", "عرض جميع الإشارات")}
                          <ArrowRight size={14} />
                        </button>
                      </section>
                      <Graph
                        events={events}
                        onSelect={(name) => {
                          setQuery(name);
                          setPage("search");
                        }}
                        ar={ar}
                      />
                    </div>
                  </div>
                </>
              )}
              {page === "signals" && (
                <Signals
                  state={state}
                  ar={ar}
                  onEvidence={evidence}
                  onError={setNotice}
                />
              )}
              {page === "search" && (
                <section className="panel archive">
                  <PanelTitle
                    icon={<Search size={17} />}
                    title={tr(
                      "Multimodal intelligence search",
                      "البحث متعدد الأنماط",
                    )}
                    right={<Badge tone="gold">RRF · HYBRID</Badge>}
                  />
                  <form onSubmit={search} className="archive-form">
                    <div className="search-field">
                      <Search size={21} />
                      <input
                        autoFocus
                        aria-label="Archive query"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder={tr(
                          "Search speech, on-screen text, or visual descriptions",
                          "ابحث في الكلام أو نص الشاشة أو وصف المشاهد",
                        )}
                      />
                      <button className="primary" disabled={searching}>
                        {searching
                          ? tr("Searching…", "جارٍ البحث…")
                          : tr("Search", "بحث")}
                      </button>
                    </div>
                    <div className="search-filters">
                      <SlidersHorizontal size={16} />
                      <select
                        aria-label="Search channel"
                        value={searchChannel}
                        onChange={(e) => setSearchChannel(e.target.value)}
                      >
                        <option value="">
                          {tr("All channels", "جميع القنوات")}
                        </option>
                        {channels.map((c) => (
                          <option value={c.id} key={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label="Search modality"
                        value={modality}
                        onChange={(e) => setModality(e.target.value)}
                      >
                        <option value="auto">
                          {tr("All modalities", "جميع الأنماط")}
                        </option>
                        <option value="transcript">
                          {tr("Speech", "الكلام")}
                        </option>
                        <option value="ocr">
                          {tr("On-screen text", "نص الشاشة")}
                        </option>
                        <option value="visual">
                          {tr("Visual descriptions", "وصف المشاهد")}
                        </option>
                      </select>
                      <select
                        aria-label="Search time window"
                        value={windowHours}
                        onChange={(e) => setWindowHours(e.target.value)}
                      >
                        <option value="1">{tr("Last hour", "آخر ساعة")}</option>
                        <option value="24">
                          {tr("Last 24 hours", "آخر ٢٤ ساعة")}
                        </option>
                        <option value="">{tr("All time", "كل الأوقات")}</option>
                      </select>
                    </div>
                  </form>
                  {searchResult ? (
                    <>
                      <div className="results-summary">
                        {searchResult.results.length}{" "}
                        {tr("observations", "مشاهدة")}{" "}
                        <span>
                          · {searchResult.elapsed_ms} ms ·{" "}
                          {searchResult.encoder} ·{" "}
                          {searchResult.warm_available
                            ? "hot + warm"
                            : "hot only"}
                        </span>
                      </div>
                      {searchResult.results.map(
                        ({ event: e, score, cosine_similarity }) => (
                          <button
                            className="result-row"
                            key={e.id}
                            onClick={() => setSelected(e)}
                          >
                            <div className="result-icon">
                              <FileText size={22} />
                            </div>
                            <div>
                              <div className="result-meta">
                                <Badge>{e.channel_id}</Badge>
                                <time>
                                  {new Date(e.start).toLocaleString(
                                    ar ? "ar-KW" : "en-GB",
                                    { timeZone: "Asia/Kuwait" },
                                  )}
                                </time>
                                {e.simulated && <Badge tone="gold">SIM</Badge>}
                              </div>
                              <h3 dir="auto">
                                {e.transcript || e.ocr || e.visual}
                              </h3>
                              <p>{e.translation}</p>
                              <div className="chips">
                                {e.entities.map((x) => (
                                  <span key={x.name}>{x.name}</span>
                                ))}
                              </div>
                            </div>
                            <div className="result-score">
                              RRF<strong>{score.toFixed(4)}</strong>
                              <small>
                                {cosine_similarity == null
                                  ? ""
                                  : `cos ${cosine_similarity.toFixed(2)}`}
                              </small>
                              <ArrowRight size={16} />
                            </div>
                          </button>
                        ),
                      )}
                      {!searchResult.results.length && (
                        <Empty>
                          {tr(
                            "No matching observations in this time window.",
                            "لا توجد مشاهدات مطابقة ضمن الفترة المحددة.",
                          )}
                        </Empty>
                      )}
                    </>
                  ) : (
                    <Empty>
                      <Search size={30} />
                      <h3>
                        {tr(
                          "Every signal has a source. Find yours.",
                          "لكل إشارة مصدر. اعثر عليه.",
                        )}
                      </h3>
                      <p>
                        {tr(
                          "Search time-aligned transcripts, chyrons and visual descriptions.",
                          "ابحث في النصوص والعناوين ووصف المشاهد المتزامنة.",
                        )}
                      </p>
                    </Empty>
                  )}
                </section>
              )}
              {page === "briefs" && (
                <section className="briefs-layout">
                  <div className="brief-intro">
                    <div className="brief-seal">
                      <Compass size={54} />
                    </div>
                    <div className="eyebrow">DIRA INTELLIGENCE</div>
                    <h2>{tr("The bigger picture.", "الصورة الأوسع.")}</h2>
                    <p>
                      {tr(
                        "Cross-channel context from sampled, timestamped evidence. See provider and coverage on each brief.",
                        "سياق يجمع القنوات من عينة أدلة مؤرخة. يظهر مزود المعالجة ونطاق العينة في كل ملخص.",
                      )}
                    </p>
                    <button
                      className="primary"
                      disabled={!!jobId}
                      onClick={() => generate("morning")}
                    >
                      <Plus size={16} />
                      {tr("Morning brief", "الملخص الصباحي")}
                    </button>
                    <button
                      className="secondary"
                      disabled={!!jobId}
                      onClick={() => generate("narrative")}
                    >
                      <Network size={16} />
                      {tr("Synthesize narratives", "تحليل السرديات")}
                    </button>
                    <small>
                      {m?.llm === "cloud" && !m.cloud_auto_briefs
                        ? tr(
                            "Cloud generation is manual. Evidence text is sent to the configured provider.",
                            "التوليد السحابي يدوي. تُرسل نصوص الأدلة إلى المزود المحدد.",
                          )
                        : tr(
                            "Scheduled daily at 06:00 Kuwait time by default.",
                            "مجدول يوميًا الساعة ٦ صباحًا بتوقيت الكويت افتراضيًا.",
                          )}
                    </small>
                  </div>
                  <div className="brief-list">
                    {jobId && (
                      <div className="panel job-progress">
                        <span className="loading-ring" />
                        {tr(
                          "Preparing your evidence brief…",
                          "جارٍ إعداد الملخص المستند إلى الأدلة…",
                        )}
                        <Badge>{jobs[jobId]?.status || "queued"}</Badge>
                      </div>
                    )}
                    {state.briefs.map((b) => (
                      <BriefCard
                        key={b.id}
                        brief={b}
                        ar={ar}
                        onEvidence={evidence}
                      />
                    ))}
                    {!state.briefs.length && !jobId && (
                      <div className="panel">
                        <Empty>
                          {tr(
                            "Your first brief starts with the observations already captured.",
                            "أنشئ ملخصك الأول من المشاهدات التي جُمعت بالفعل.",
                          )}
                        </Empty>
                      </div>
                    )}
                  </div>
                </section>
              )}
              {page === "system" && (
                <System
                  state={state}
                  connection={connection}
                  ar={ar}
                  onSettings={() => setSettings(true)}
                />
              )}
            </>
          )}
          <footer>
            <span>
              <ShieldCheck size={13} />
              {tr(
                "Sovereign by design. Evidence at the center.",
                "سيادة في التصميم. وأدلة في صميم العمل.",
              )}
            </span>
            <span>
              DIRA v0.1 <b>·</b>{" "}
              {m?.mode === "simulation"
                ? "DEMONSTRATION"
                : m?.llm === "cloud"
                  ? "CLOUD REASONING ENABLED"
                  : "LOCAL OPERATIONS"}
            </span>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          {notice}
          <button
            className="icon-button"
            onClick={() => setNotice("")}
            aria-label="Dismiss notification"
          >
            <X size={16} />
          </button>
        </div>
      )}
      {settings && (
        <Modal
          title={tr("Connection settings", "إعدادات الاتصال")}
          onClose={() => setSettings(false)}
        >
          <p>
            {tr(
              "Enter the bearer token configured on your local Dira server. It is kept only in this browser session.",
              "أدخل رمز الوصول المعدّ في خادم ديرة المحلي. يُحفظ في جلسة المتصفح الحالية فقط.",
            )}
          </p>
          <label>
            {tr("API token", "رمز الوصول")}
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          <button
            className="primary"
            onClick={() => {
              sessionStorage.setItem("dira-token", token);
              setRevision((x) => x + 1);
              setSettings(false);
            }}
          >
            {tr("Reconnect", "إعادة الاتصال")}
          </button>
        </Modal>
      )}
      {expanded && (
        <Modal
          wide
          title={ar ? expanded.name_ar : expanded.name}
          onClose={() => setExpanded(null)}
        >
          <div className="expanded-player">
            <Player
              channel={expanded}
              index={
                Math.max(
                  channels.findIndex((c) => c.id === expanded.id),
                  0,
                ) % 4
              }
            />
            <Badge tone="gold">
              {m?.mode === "simulation"
                ? tr("ILLUSTRATED SIMULATION", "محاكاة مرئية")
                : expanded.status}
            </Badge>
          </div>
          <div className="focused-transcripts">
            {events
              .filter((e) => e.channel_id === expanded.id)
              .slice(0, 5)
              .map((e) => (
                <button
                  key={e.id}
                  onClick={() => {
                    setSelected(e);
                    setExpanded(null);
                  }}
                >
                  <time>{time(e.start)}</time>
                  <p dir="auto">{e.transcript || e.ocr}</p>
                  <small>{e.translation}</small>
                </button>
              ))}
          </div>
        </Modal>
      )}
      {selected && (
        <Modal
          wide
          title={tr("Observation evidence", "أدلة المشاهدة")}
          onClose={() => setSelected(null)}
        >
          <div className="evidence-meta">
            <Badge>{selected.channel_id}</Badge>
            <Badge tone="gold">
              {selected.simulated ? "SIMULATION" : "LIVE SOURCE"}
            </Badge>
            <time>
              {time(selected.start)} — {time(selected.end)}
            </time>
          </div>
          <h3 dir="auto">
            {selected.transcript || selected.ocr || selected.visual}
          </h3>
          <p>{selected.translation}</p>
          <div className="evidence-grid">
            <div>
              <label>{tr("ON-SCREEN TEXT", "نص الشاشة")}</label>
              <p dir="auto">{selected.ocr || "—"}</p>
            </div>
            <div>
              <label>{tr("VISUAL DESCRIPTION", "وصف المشهد")}</label>
              <p>{selected.visual || "—"}</p>
            </div>
          </div>
          <div className="chips">
            {selected.entities.map((e) => (
              <span key={e.name}>{e.name}</span>
            ))}
          </div>
          <dl className="evidence-facts">
            <dt>{tr("Source", "المصدر")}</dt>
            <dd>{selected.source}</dd>
            <dt>{tr("Speaker", "المتحدث")}</dt>
            <dd>{selected.speaker || "—"}</dd>
            <dt>{tr("Confidence", "الثقة")}</dt>
            <dd>
              {selected.confidence == null ||
              (!selected.simulated &&
                ["whisperlivekit", "local-perception"].includes(
                  selected.source,
                ))
                ? tr("Uncalibrated", "الدقة غير معايرة")
                : `${Math.round(selected.confidence * 100)}%`}
            </dd>
            <dt>{tr("Evidence ID", "معرّف الدليل")}</dt>
            <dd className="mono">{selected.id}</dd>
          </dl>
        </Modal>
      )}
    </div>
  );
}

const LAG_WARN_SECONDS = 30;
function LagBadge({ channel, ar }: { channel: Channel; ar: boolean }) {
  const lag = channel.asr_lag_seconds;
  const resets = channel.asr_resets || 0;
  const degraded = Boolean(channel.asr_degraded);
  const tone = degraded
    ? "late"
    : lag == null
      ? "unknown"
      : lag > LAG_WARN_SECONDS
        ? "late"
        : "ok";
  const label =
    (degraded ? "⚠ " : "") +
    (lag == null
      ? ar
        ? "تفريغ —"
        : "ASR —"
      : `${ar ? "تفريغ" : "ASR"} ${lag.toFixed(0)}s`);
  const cause = channel.asr_last_reset_cause;
  const detail =
    (degraded
      ? ar
        ? "التفريغ الصوتي متدهور: إعادات ضبط متكررة، والنصوص ناقصة. "
        : "Speech recognition degraded: repeated resets, transcripts are incomplete. "
      : "") +
    (ar
      ? `تأخر التفريغ الصوتي. أعيد الضبط ${resets} مرة، الفقد التقديري ${Math.round(channel.asr_skipped_seconds || 0)} ث؛ ليس قياسًا دقيقًا للصوت المفقود.`
      : `Speech transcription lag. Reset to live ${resets}× · ${Math.round(channel.asr_skipped_seconds || 0)} s estimated coverage loss (not measured skipped speech).`) +
    (cause ? (ar ? ` آخر سبب: ${cause}.` : ` Last cause: ${cause}.`) : "");
  return (
    <span className={"lag-badge " + tone} title={detail} aria-label={detail}>
      {label}
      {resets > 0 && <b>↻{resets}</b>}
    </span>
  );
}
function Stat({
  label,
  value,
  suffix,
  icon,
  sub,
  accent = false,
}: {
  label: string;
  value: string;
  suffix?: string;
  icon: React.ReactNode;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div className={"stat-card " + (accent ? "accent" : "")}>
      <div className="stat-label">
        {label}
        <span>{icon}</span>
      </div>
      <div className="stat-value">
        {value}
        <small>{suffix}</small>
      </div>
      <p>
        <span />
        {sub}
      </p>
    </div>
  );
}
function PanelTitle({
  icon,
  title,
  right,
}: {
  icon: React.ReactNode;
  title: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="panel-title">
      <h2>
        {icon}
        {title}
      </h2>
      {right}
    </div>
  );
}
function topicCounts(events: Event[]): [string, number][] {
  const counts: Record<string, number> = {};
  for (const e of events)
    for (const n of e.entities) counts[n.name] = (counts[n.name] || 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}
function Graph({
  events,
  onSelect,
  ar,
}: {
  events: Event[];
  onSelect: (x: string) => void;
  ar: boolean;
}) {
  const names = topicCounts(events).slice(0, 6);
  const points = names.map((_, i) => ({
    x: 150 + Math.cos((i * Math.PI) / 3 - 0.4) * 97,
    y: 110 + Math.sin((i * Math.PI) / 3 - 0.4) * 70,
  }));
  return (
    <section className="panel graph-panel">
      <PanelTitle
        icon={<Network size={16} />}
        title={ar ? "روابط الكيانات" : "Entity connections"}
        right={<Badge>{names.length}</Badge>}
      />
      <svg viewBox="0 0 300 220" aria-label="Entity co-occurrence graph">
        {names.flatMap(([a], i) =>
          names.slice(i + 1).map(([b], j) => {
            const connected = events.some(
              (e) =>
                e.entities.some((n) => n.name === a) &&
                e.entities.some((n) => n.name === b),
            );
            const k = i + j + 1;
            return connected ? (
              <line
                key={a + b}
                x1={points[i].x}
                y1={points[i].y}
                x2={points[k].x}
                y2={points[k].y}
                stroke="var(--accent-line)"
                strokeWidth="1.2"
              />
            ) : null;
          }),
        )}
        {names.map(([name, count], i) => (
          <g
            key={name}
            tabIndex={0}
            role="button"
            aria-label={"Search " + name}
            onClick={() => onSelect(name)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSelect(name);
            }}
            className="graph-node"
          >
            <circle
              cx={points[i].x}
              cy={points[i].y}
              r={10 + Math.min(count / 8, 8)}
              fill={i === 0 ? "var(--gold)" : "var(--amber)"}
              stroke="var(--surface)"
              strokeWidth="3"
            />
            <text
              x={points[i].x}
              y={points[i].y + 31}
              textAnchor="middle"
              fontSize="9"
              fill="var(--muted)"
            >
              {name}
            </text>
          </g>
        ))}
      </svg>
      <div className="panel-foot">
        {ar
          ? "ترابط في المشاهدات، وليس إثباتًا للعلاقة"
          : "Co-occurrence in observations, not proof of a relationship"}
      </div>
    </section>
  );
}
function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const [node, setNode] = useState<HTMLDialogElement | null>(null);
  useEffect(() => {
    node?.showModal();
    return () => {
      node?.close();
    };
  }, [node]);
  return (
    <dialog
      ref={setNode}
      onCancel={onClose}
      className={wide ? "modal wide" : "modal"}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-header">
        <h2>{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <div className="modal-content">{children}</div>
    </dialog>
  );
}
function BriefCard({
  brief: b,
  ar,
  onEvidence,
}: {
  brief: Brief;
  ar: boolean;
  onEvidence: (id: string | null) => void;
}) {
  return (
    <article className="panel brief-card">
      <div className="brief-card-top">
        <span className="eyebrow">
          {b.kind === "morning" ? "MORNING EDITION" : "NARRATIVE SYNTHESIS"}
        </span>
        <button
          className="icon-button"
          aria-label="Export brief"
          onClick={() =>
            download(
              `dira-${b.id}.md`,
              `# ${b.title}\n\n${b.created_at}\n\n${b.simulated ? "SIMULATION\n\n" : ""}${b.content}\n\nEvidence: ${b.evidence_ids.join(", ")}`,
            )
          }
        >
          <ArrowDownToLine size={18} />
        </button>
      </div>
      <h2>{b.title}</h2>
      <div className="brief-meta">
        <Clock size={13} />
        {new Date(b.created_at).toLocaleString(ar ? "ar-KW" : "en-GB", {
          timeZone: "Asia/Kuwait",
        })}
        <Badge tone="gold">{b.simulated ? "SIMULATION" : b.mode}</Badge>
        <Badge>{b.mode}</Badge>
      </div>
      {b.coverage && (
        <p className="brief-coverage" dir="auto">
          {ar ? "عينة" : "Sample"}: {b.coverage.sampled_observations} /{" "}
          {b.coverage.total_observations} · {b.coverage.sampled_channels}{" "}
          {ar ? "قنوات" : "channels"}
          <br />
          {new Date(b.coverage.window_start).toLocaleString(
            ar ? "ar-KW" : "en-GB",
          )}{" "}
          →{" "}
          {new Date(b.coverage.window_end).toLocaleString(
            ar ? "ar-KW" : "en-GB",
          )}
        </p>
      )}
      {b.error && <div className="error-banner">{b.error}</div>}
      <div className="brief-content" dir="auto">
        {b.content.split(/(\[[0-9a-f-]{36}\])/g).map((part, i) =>
          /^\[[0-9a-f-]{36}\]$/.test(part) ? (
            <button
              className="citation"
              key={i}
              onClick={() => onEvidence(part.slice(1, -1))}
            >
              [{b.evidence_ids.indexOf(part.slice(1, -1)) + 1}]
            </button>
          ) : (
            part
          ),
        )}
      </div>
      <div className="evidence-links">
        <span>{ar ? "المصادر" : "SOURCE EVIDENCE"}</span>
        {b.evidence_ids.slice(0, 12).map((id, i) => (
          <button key={id} onClick={() => onEvidence(id)}>
            {String(i + 1).padStart(2, "0")}
            <ArrowRight size={10} />
          </button>
        ))}
        <small>
          {b.evidence_ids.length} {ar ? "مشاهدة" : "observations"}
        </small>
      </div>
    </article>
  );
}
function Signals({
  state,
  ar,
  onEvidence,
  onError,
}: {
  state: Snapshot;
  ar: boolean;
  onEvidence: (id: string | null) => void;
  onError: (s: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState("");
  const [kind, setKind] = useState("keyword");
  const [severity, setSeverity] = useState("warning");
  async function run(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch (e) {
      onError(String(e));
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    await run(async () => {
      await api("/rules", { name, pattern, kind, severity });
      setShowForm(false);
      setName("");
      setPattern("");
    });
  }
  return (
    <div className="signals-layout">
      <section className="panel">
        <PanelTitle
          icon={<Bell size={17} />}
          title={ar ? "سجل الإشارات" : "Signal inbox"}
          right={
            <button
              className="small-button"
              onClick={() => setShowAll(!showAll)}
            >
              {showAll
                ? ar
                  ? "غير المراجعة"
                  : "Unreviewed only"
                : ar
                  ? "عرض الكل"
                  : "Include reviewed"}
            </button>
          }
        />
        {state.alerts
          .filter((a) => showAll || !a.acknowledged)
          .map((a) => (
            <div className="signal-row" key={a.id}>
              <div className={"signal-marker " + a.severity} />
              <div className="signal-body">
                <div className="alert-top">
                  <Badge tone={a.severity}>{a.severity}</Badge>
                  <span>
                    {a.channel_id} · {time(a.timestamp)}
                  </span>
                  {a.acknowledged && <Badge tone="good">Reviewed</Badge>}
                </div>
                <button
                  className="signal-title"
                  onClick={() => onEvidence(a.tdo_id)}
                >
                  {a.rule_name}
                  <ArrowRight size={14} />
                </button>
                <p dir="auto">{a.detail}</p>
                <small>
                  {a.kind} gate · {a.simulated ? "simulation" : "live"}
                </small>
              </div>
              <button
                className="icon-button"
                disabled={a.acknowledged}
                aria-label="Acknowledge alert"
                onClick={() => run(() => api(`/alerts/${a.id}/ack`, {}))}
              >
                <Check size={19} />
              </button>
            </div>
          ))}
        {!state.alerts.filter((a) => showAll || !a.acknowledged).length && (
          <Empty>{ar ? "لا توجد تنبيهات" : "No alerts to review"}</Empty>
        )}
      </section>
      <section className="panel rules-panel">
        <PanelTitle
          icon={<SlidersHorizontal size={17} />}
          title={ar ? "قواعد الرصد" : "Monitoring rules"}
          right={
            <button
              className="icon-button"
              aria-label="Add rule"
              onClick={() => setShowForm(!showForm)}
            >
              <Plus size={18} />
            </button>
          }
        />
        {showForm && (
          <form className="rule-form" onSubmit={save}>
            <label>
              {ar ? "اسم القاعدة" : "Rule name"}
              <input
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              {ar ? "النمط" : "Pattern"}
              <input
                required
                maxLength={256}
                value={pattern}
                onChange={(e) => setPattern(e.target.value)}
              />
            </label>
            <select
              aria-label="Rule type"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="keyword">Keyword</option>
              <option value="regex">Regular expression</option>
            </select>
            <select
              aria-label="Severity"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
            <button className="primary">
              {ar ? "حفظ القاعدة" : "Save rule"}
            </button>
          </form>
        )}
        {state.rules.map((r: Rule) => (
          <div className="rule-row" key={r.id}>
            <div>
              <strong>{r.name}</strong>
              <code>{r.pattern}</code>
              <small>
                {r.kind} · {r.severity}
              </small>
            </div>
            <button
              className={"toggle " + (r.enabled ? "on" : "")}
              aria-label={"Toggle " + r.name}
              aria-pressed={r.enabled}
              onClick={() =>
                run(() => api("/rules", { ...r, enabled: !r.enabled }))
              }
            >
              <i />
            </button>
            <button
              className="icon-button"
              aria-label={"Delete " + r.name}
              onClick={() =>
                run(() => api("/rules/" + r.id, undefined, "DELETE"))
              }
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <div className="rule-note">
          <Zap size={16} />
          {ar
            ? "قواعد حتمية دون استدعاء نموذج لغوي."
            : "Deterministic gates. No language model calls."}
        </div>
      </section>
    </div>
  );
}
function System({
  state,
  connection,
  ar,
  onSettings,
}: {
  state: Snapshot;
  connection: string;
  ar: boolean;
  onSettings: () => void;
}) {
  const m = state.metrics;
  const rows = [
    ["Event stream", connection, "REST + WebSocket"],
    [
      "Hot vector tier",
      "connected",
      `${m.hot_vectors}/${m.hot_capacity ?? "—"} observations · ${Math.round((m.hot_horizon_seconds ?? 0) / 60)} min actual horizon · FAISS CPU`,
    ],
    ["Warm vector tier", m.warm_status, "Qdrant named vectors"],
    [
      "Evidence store",
      m.disk_guard_active ? "paused" : "connected",
      `${m.evidence} observations · ${m.disk_free_gb ?? "—"} GiB free · SQLite WAL`,
    ],
    [
      "Embedding engine",
      "configured",
      `${m.encoder} · ${m.device.toUpperCase()}`,
    ],
    ["Reasoning worker", m.llm, `${m.jobs_pending} queued jobs`],
  ];
  return (
    <>
      <section className="system-banner">
        <ShieldCheck size={36} />
        <div>
          <h2>
            {ar ? "حالة المعالجة والخدمات." : "Processing and service status."}
          </h2>
          <p>
            {ar
              ? "تعكس الحالة ما يبلّغ عنه النظام، ولا تمثل شهادة عزل شبكي."
              : "Service status reflects runtime observations. Network isolation requires deployment controls."}
          </p>
        </div>
        <button className="secondary" onClick={onSettings}>
          {ar ? "إعدادات الاتصال" : "Connection settings"}
        </button>
      </section>
      <section className="panel">
        <PanelTitle
          icon={<Database size={17} />}
          title={ar ? "خدمات المنصة" : "Platform services"}
        />
        {rows.map(([name, status, detail]) => (
          <div className="service-row" key={name}>
            <div className="service-icon">
              <Database size={19} />
            </div>
            <div>
              <h3>{name}</h3>
              <p>{detail}</p>
            </div>
            <Badge
              tone={
                status === "connected"
                  ? "good"
                  : status === "degraded"
                    ? "critical"
                    : "gold"
              }
            >
              {status}
            </Badge>
          </div>
        ))}
      </section>
      <section className="stat-grid system-stats">
        <Stat
          label="DURABLE OUTBOX"
          value={String(m.pending)}
          sub="Awaiting warm-tier acknowledgement"
          icon={<Layers />}
        />
        <Stat
          label="STREAM RESYNCS"
          value={String(m.ws_resyncs)}
          sub="Slow subscribers recovered"
          icon={<Radio />}
        />
        <Stat
          label="REGEX TIMEOUTS"
          value={String(m.regex_timeouts)}
          sub="Expensive patterns interrupted"
          icon={<Clock />}
        />
        <Stat
          label="UPTIME"
          value={String(Math.floor(m.uptime_seconds / 60))}
          suffix="min"
          sub="Current backend process"
          icon={<Activity />}
        />
      </section>
    </>
  );
}
