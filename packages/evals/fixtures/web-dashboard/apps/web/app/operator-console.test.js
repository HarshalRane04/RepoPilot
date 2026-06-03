function modeLabel(readiness) {
  if (readiness.local_record_mode) return "Local record mode";
  return readiness.github_mode === "write_enabled_verified" ? "Real GitHub write mode" : "GitHub write mode pending verification";
}

if (modeLabel({ local_record_mode: true, github_mode: "missing_credentials" }) !== "Local record mode") {
  throw new Error("Expected local record mode label");
}

