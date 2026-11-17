import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import type { Channel } from "./types";
export function BroadcastScene({ index = 0 }: { index?: number }) {
  return (
    <svg
      className={"broadcast-scene scene-" + index}
      viewBox="0 0 640 360"
      role="img"
      aria-label="Illustrated simulation feed"
    >
      <defs>
        <linearGradient id={"sky" + index} x2="0" y2="1">
          <stop
            stopColor={["#25465b", "#1b3e4c", "#24334f", "#394251"][index % 4]}
          />
          <stop offset="1" stopColor="#a99479" />
        </linearGradient>
        <linearGradient id={"sea" + index} x2="0" y2="1">
          <stop stopColor="#537f86" />
          <stop offset="1" stopColor="#162c41" />
        </linearGradient>
      </defs>
      <rect width="640" height="360" fill={`url(#sky${index})`} />
      <circle
        cx={index % 2 ? 490 : 145}
        cy="100"
        r="34"
        fill="#d6c6a6"
        opacity=".6"
      />
      <path
        d="M0 190 Q160 130 320 173 T640 155 V360 H0Z"
        fill="#294758"
        opacity=".4"
      />
      {index === 0 ? (
        <g fill="#172c3c">
          <path d="M90 260 L110 87 118 260Z M150 260 L166 55 175 260Z M210 260 L223 113 230 260Z" />
          <ellipse cx="114" cy="174" rx="19" ry="24" />
          <ellipse cx="169" cy="148" rx="29" ry="33" />
          <ellipse cx="169" cy="95" rx="16" ry="17" />
          {Array.from({ length: 15 }, (_, i) => (
            <rect
              key={i}
              x={280 + i * 25}
              y={185 - (i % 4) * 17}
              width="20"
              height="95"
              opacity={0.5 + (i % 3) * 0.15}
            />
          ))}
        </g>
      ) : index === 1 ? (
        <g fill="#203a47">
          <path d="M30 219H330L280 267H72Z" />
          <rect x="55" y="172" width="160" height="45" fill="#a48662" />
          <rect x="130" y="133" width="60" height="37" fill="#557e7d" />
          <path d="M400 260V80H555V91H415V260Z M480 260V120H610V131H495V260Z" />
          <path
            d="M415 90L550 170M495 130L605 200"
            stroke="#203a47"
            strokeWidth="5"
          />
        </g>
      ) : index === 2 ? (
        <g>
          <rect
            x="60"
            y="70"
            width="520"
            height="200"
            rx="5"
            fill="#15283c"
            opacity=".85"
          />
          {[100, 140, 180, 220].map((y) => (
            <path key={y} d={`M80 ${y}H560`} stroke="#45606c" opacity=".5" />
          ))}
          <polyline
            points="80,220 120,205 160,224 200,178 240,186 280,150 320,163 360,122 400,141 440,98 480,112 530,85"
            fill="none"
            stroke="#77b8a5"
            strokeWidth="4"
          />
          <text x="85" y="97" fill="#b5c9c8" fontSize="12" letterSpacing="3">
            ENERGY · REGIONAL OUTLOOK
          </text>
        </g>
      ) : (
        <g fill="#1c3344">
          {Array.from({ length: 17 }, (_, i) => (
            <g key={i}>
              <rect x={i * 40} y={150 - (i % 5) * 19} width="34" height="130" />
              {Array.from({ length: 5 }, (_, j) => (
                <path
                  key={j}
                  d={`M${i * 40 + 7} ${164 - (i % 5) * 19 + j * 18}h20`}
                  stroke="#b6b09b"
                  opacity=".35"
                />
              ))}
            </g>
          ))}
        </g>
      )}
      {index !== 2 && (
        <>
          <path
            d="M0 267Q160 249 320 268T640 258V360H0Z"
            fill={`url(#sea${index})`}
          />
          {Array.from({ length: 8 }, (_, i) => (
            <path
              className="waterline"
              key={i}
              d={`M${i * 83 - 20} ${283 + (i % 3) * 12}h65`}
              stroke="#c3c5b7"
              strokeWidth="1"
              opacity=".2"
            />
          ))}
        </>
      )}
      <rect width="640" height="360" fill="#081420" opacity=".13" />
    </svg>
  );
}
export function Player({
  channel,
  index,
}: {
  channel: Channel;
  index: number;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const video = ref.current;
    let hls: Hls | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    setError("");
    if (video && channel.playback_url) {
      if (Hls.isSupported()) {
        const connect = () => {
          // A restarted MediaMTX muxer may have a new timeline/init segment.
          // Rebuild the client instead of retrying a stale playlist/buffer forever.
          hls?.destroy();
          hls = new Hls({ lowLatencyMode: true });
          hls.loadSource(channel.playback_url);
          hls.attachMedia(video);
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            void video
              .play()
              .catch(() => setError("Press play to start video"));
          });
          hls.on(Hls.Events.ERROR, (_, data) => {
            if (!data.fatal || retry) return;
            setError("Reconnecting video…");
            const delay = Math.min(30000, 2000 * 2 ** Math.min(attempts++, 4));
            // One timer/client only; the retry rate is bounded even through long outages.
            retry = setTimeout(() => {
              retry = undefined;
              connect();
            }, delay);
          });
        };
        connect();
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = channel.playback_url;
      } else setError("HLS unavailable in this browser");
    }
    const healthy = () => {
      attempts = 0;
    };
    video?.addEventListener("playing", healthy);
    return () => {
      video?.removeEventListener("playing", healthy);
      clearTimeout(retry);
      hls?.destroy();
    };
  }, [channel.playback_url]);
  return channel.playback_url ? (
    <>
      <video
        ref={ref}
        autoPlay
        muted
        controls
        playsInline
        onError={() => setError("Playback unavailable")}
        onPlaying={() => setError("")}
        onStalled={() => setError("Video stalled · waiting for source")}
      />
      {error && <div className="video-error">{error}</div>}
    </>
  ) : (
    <BroadcastScene index={index} />
  );
}
export function Spark({
  values,
  color = "var(--gold)",
  height = 60,
}: {
  values: number[];
  color?: string;
  height?: number;
}) {
  const max = Math.max(...values, 1);
  const pts = values
    .map(
      (v, i) =>
        `${(i * 300) / Math.max(values.length - 1, 1)},${height - 5 - (v / max) * (height - 12)}`,
    )
    .join(" ");
  return (
    <svg
      viewBox={`0 0 300 ${height}`}
      preserveAspectRatio="none"
      className="spark"
      aria-label="Observed activity history"
    >
      <path
        d={`M0 ${height} ${pts
          .split(" ")
          .map((p) => "L" + p)
          .join(" ")} L300 ${height}Z`}
        fill={color}
        opacity=".08"
      />
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
