export function upsert(items, item, limit = 120) {
  return [item, ...items.filter((x) => x.id !== item.id)].slice(0, limit);
}
export function applyMessage(state, message) {
  const sequence = message.sequence ?? state.sequence ?? 0;
  if (sequence < (state.sequence ?? 0)) return state;
  if (message.type === "snapshot") return message.data;
  const next = { ...state, sequence };
  if (message.type === "tdo")
    return { ...next, events: upsert(state.events, message.data) };
  if (message.type === "alert") {
    const existing = state.alerts.some((item) => item.id === message.data.id);
    return {
      ...next,
      alerts: existing
        ? state.alerts.map((item) =>
            item.id === message.data.id ? message.data : item,
          )
        : upsert(state.alerts, message.data, 100),
    };
  }
  if (message.type === "brief")
    return { ...next, briefs: upsert(state.briefs, message.data, 20) };
  if (["metrics", "rules", "channels"].includes(message.type))
    return { ...next, [message.type]: message.data };
  return state;
}
