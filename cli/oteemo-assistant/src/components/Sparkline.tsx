import React from "react";
import { Text } from "ink";

export function Sparkline({ values }: { values: number[] }) {
  if (!values || values.length === 0) return <Text>·</Text>;
  const mn = Math.min(...values);
  const mx = Math.max(...values);
  if (mx === mn) return <Text>{"·".repeat(values.length)}</Text>;
  const bars = "▁▂▃▄▅▆▇█";
  const s = values.map(v => {
    const idx = Math.floor(((v - mn) / (mx - mn)) * (bars.length - 1));
    return bars[Math.max(0, Math.min(bars.length - 1, idx))];
  }).join("");
  return <Text>{s}</Text>;
}
