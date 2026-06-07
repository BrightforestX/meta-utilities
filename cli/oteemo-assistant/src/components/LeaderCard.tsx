import React from "react";
import { Text, Box } from "ink";

export type LeaderRec = {
  name: string;
  role: string;
  rec: string;
  metric?: string;
};

export function LeaderCard({ rec }: { rec: LeaderRec }) {
  return (
    <Box borderStyle="round" paddingX={1} marginBottom={1} flexDirection="column">
      <Text bold color="cyan">{rec.name} — {rec.role}</Text>
      <Text>{rec.rec}</Text>
      {rec.metric ? <Text dimColor>metric: {rec.metric}</Text> : null}
    </Box>
  );
}
