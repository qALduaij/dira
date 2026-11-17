import { useEffect, useRef, useState } from "react";
import { applyMessage } from "./state.mjs";
import type { Snapshot } from "./types";
export function useDira(revision: number) {
  const [state, setState] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<
    Record<string, { status: string; error?: string }>
  >({});
  const socketRef = useRef<WebSocket | null>(null);
  useEffect(() => {
    let stopped = false,
      timer: ReturnType<typeof setTimeout>,
      attempts = 0;
    function connect() {
      if (stopped) return;
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`,
      );
      socketRef.current = ws;
      ws.onopen = () => {
        ws.send(
          JSON.stringify({ token: sessionStorage.getItem("dira-token") || "" }),
        );
      };
      ws.onmessage = (event) => {
        if (stopped || socketRef.current !== ws) return;
        try {
          const message = JSON.parse(event.data);
          if (message.type === "resync") {
            ws.close();
            return;
          }
          attempts = 0;
          setConnection("connected");
          setError("");
          if (message.type === "job") {
            setJobs((old) => ({ ...old, [message.data.id]: message.data }));
            return;
          }
          if (message.type === "snapshot") setJobs(message.data.jobs || {});
          // A new connection always starts with an atomic server snapshot, including after server restart.
          setState((old) =>
            message.type === "snapshot"
              ? message.data
              : old
                ? (applyMessage(old, message) as Snapshot)
                : old,
          );
        } catch {
          setError("Invalid stream message");
        }
      };
      ws.onclose = (event) => {
        if (stopped || socketRef.current !== ws) return;
        setConnection("disconnected");
        if (event.code === 1008) {
          setError("Access token required. Open Connection settings.");
          return;
        }
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 15000));
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socketRef.current?.close();
    };
  }, [revision]);
  return { state, connection, error, jobs };
}
