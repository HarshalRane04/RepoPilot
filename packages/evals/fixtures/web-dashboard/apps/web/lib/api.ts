export type Readiness = {
  local_record_mode: boolean;
  github_mode: string;
};

export function modeLabel(readiness: Readiness): string {
  if (readiness.local_record_mode) {
    return "Local record mode";
  }
  return readiness.github_mode === "write_enabled_verified" ? "Real GitHub write mode" : "GitHub write mode pending verification";
}

