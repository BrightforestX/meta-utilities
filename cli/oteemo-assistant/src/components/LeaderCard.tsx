import React from "react";
import { Text, Box } from "ink";

export type LeaderRec = {
  name: string;
  role: string;
  rec: string;
  metric?: string;
  reasoning?: string;
  executionRisk?: "low" | "medium" | "high";
  executionPath?: string;
};

export function LeaderCard({ rec }: { rec: LeaderRec }) {
  return (
    <Box borderStyle="round" borderColor="cyan" paddingX={1} marginBottom={0} flexDirection="column">
      <Text bold color="cyan">▶ {rec.name} — {rec.role}</Text>
      <Text>{rec.rec}</Text>
      {rec.metric ? <Text dimColor>metric: {rec.metric}</Text> : null}
      {rec.executionRisk ? <Text dimColor>execution risk: {rec.executionRisk}</Text> : null}
      {rec.reasoning ? <Text dimColor>why now: {rec.reasoning}</Text> : null}
      {rec.executionPath ? <Text dimColor>execution path: {rec.executionPath}</Text> : null}
    </Box>
  );
}
